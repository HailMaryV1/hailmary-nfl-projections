"""
compute_projections.py
-------------------------
The real projection engine, v1. Turns the raw rows Phase 2 ingested (real
Spreadex ladder/O-U odds, real lineup status) into a priced "Projected
Points" number per player for the current gameweek.

READ THIS BEFORE ASSUMING SOMETHING IS MISSING:

- Only horizon=1 is computed. Horizons 2/3/5 need real fixture data for
  future gameweeks (bye weeks, opponent matchups) that hasn't been
  scraped yet - this project only ever ingests the "editable" current
  gameweek (see scrape_fanteam.py's docstring). Extending to multi-week
  horizons is real future work, not a bug here.
- `rating` (the 1-10 absolute scale) is left NULL. The original design
  (see CLAUDE.md) calibrates that scale from a real measured distribution
  of a season's worth of ratings - with one gameweek of a brand-new season
  played, there is no real distribution yet to calibrate against. Writing
  a number here now would be inventing one, not measuring one. Revisit
  once real predictions_and_actuals history exists.
- Form and Fixture Quality layers are `populated: false` for every player
  right now, correctly, not by omission: Form needs real prior-gameweek
  player_stats (none exist yet - the season hasn't been played), and
  Fixture Quality needs a real measure of opponent defensive strength
  (also derived from played games). The four-content-layer renormalization
  already handles this - see layer_weights' own migration comment - so
  `total_points` this early is effectively 100% Live-Odds-driven, which is
  the honest state of a Week 1 projection, not a defect.
- rushing_td and receiving_td have NO live-odds signal at all: confirmed
  live (2026-09-07, see docs/data-and-weights.md) that Spreadex's Weekly
  Player Markets page has NO standalone rushing/receiving touchdown
  market on the pages this project scrapes (only Passing Touchdowns).
  Real anytime-TD markets likely exist elsewhere on Spreadex (e.g. "1st
  Touchdown Type") but haven't been found/scraped yet - a real, open gap,
  not something silently faked here. These two stats are always
  `populated: false`, contributing 0 expected count, until that gap is
  closed.
- defense_special has NO live-odds coverage at all right now (the one
  market that existed for it, Sacks, was deliberately excluded in Phase 2
  for pricing individual defenders this project's schema can't represent -
  see scrape_spreadex_nfl_props.py). Every defense_special projection is
  therefore 0 with data_confidence 0 until a real team-level defensive
  data source is found. Reported plainly in the run summary below, not
  hidden.

RUN:
    python scripts/compute_projections.py [gameweek]
    (defaults to the highest real gameweek currently in `fixtures`)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402
from stat_math import anytime_prob_to_expected_count, expected_value_from_points  # noqa: E402

HORIZON = 1

# market family -> (scoring stat, estimator)
LADDER_STAT_MAP = {
    "passing_yards": "passing_yards",
    "rushing_yards": "rushing_yards",
    "receiving_yards": "receiving_yards",
    "total_receptions": "reception",
}
ANYTIME_STAT_MAP = {
    "passing_touchdowns": "passing_td",
}

# Real statuses observed live from both sources (see migration 0004) ->
# probability-of-playing prior. A first-pass calibration (documented as
# such, see feedback_calibration_layer_discipline in project memory) - to
# be refined once real predictions_and_actuals history exists to check it
# against, not a measured ground truth today.
LINEUP_PROBABILITY = {
    "starter": 1.0, "expected": 1.0,
    "possible": 0.65,
    "questionable": 0.75,
    "doubtful": 0.25,
    "unexpected": 0.1,
    "injured": 0.1,
    "refuted": 0.0,
    "inactive": 0.0,
}

LADDER_RE = re.compile(r"^(.+)_(\d+(?:\.\d+)?)plus$")
# Only the "over" side is a real P(X >= threshold) point usable alongside
# the ladder rungs. "under" is its complement (P(X < threshold)), not
# another point on the same survival curve - mixing it in unconverted
# would silently corrupt the curve, so it's matched separately and never
# fed to expected_value_from_points.
OVER_RE = re.compile(r"^(.+)_over_(\d+(?:\.\d+)?)$")
UNDER_RE = re.compile(r"^(.+)_under_(\d+(?:\.\d+)?)$")


def load_scoring_rules(cur):
    cur.execute("select applies_to, stat, points from scoring_rules")
    return {(applies_to, stat): float(points) for applies_to, stat, points in cur.fetchall()}


def load_layer_weights(cur):
    cur.execute("select horizon, position, layer, weight from layer_weights")
    weights = {}
    for horizon, position, layer, weight in cur.fetchall():
        weights.setdefault((horizon, position), {})[layer] = float(weight)
    return weights


def get_or_create_algorithm_version(cur, scoring_rules, layer_weights):
    snapshot = {
        "scoring_rules": {f"{a}:{s}": p for (a, s), p in scoring_rules.items()},
        "layer_weights": {f"{h}:{pos}:{l}": w for (h, pos), layers in layer_weights.items() for l, w in layers.items()},
    }
    snapshot_json = json.dumps(snapshot, sort_keys=True)

    cur.execute("select id, weights from algorithm_versions order by revision desc limit 1")
    row = cur.fetchone()
    if row and json.dumps(row[1], sort_keys=True) == snapshot_json:
        return row[0]

    cur.execute("select coalesce(max(revision), 0) + 1 from algorithm_versions")
    next_revision = cur.fetchone()[0]
    cur.execute(
        "insert into algorithm_versions (revision, weights, note) values (%s, %s, %s) returning id",
        (next_revision, json.dumps(snapshot), "compute_projections.py auto-snapshot"),
    )
    return cur.fetchone()[0]


def current_gameweek(cur, requested):
    if requested is not None:
        return requested
    cur.execute("select max(gameweek) from fixtures")
    return cur.fetchone()[0]


def find_fixture_for_team(cur, team_id, gameweek):
    cur.execute(
        "select id from fixtures where (home_team_id = %s or away_team_id = %s) and gameweek = %s",
        (team_id, team_id, gameweek),
    )
    row = cur.fetchone()
    return row[0] if row else None


def lineup_probability(cur, player_id, fixture_id):
    cur.execute(
        """
        select status, source from player_lineup_status
        where player_id = %s and fixture_id = %s
        order by (source = 'rotowire') desc, captured_at desc
        limit 1
        """,
        (player_id, fixture_id),
    )
    row = cur.fetchone()
    if row is None:
        return 0.5, None, None  # no real signal at all - a real, honest fallback midpoint, not a confident guess
    status, source = row
    return LINEUP_PROBABILITY.get(status, 0.5), status, source


def market_odds_by_family(cur, player_id, fixture_id):
    cur.execute(
        """
        select distinct on (market) market, value
        from player_market_odds
        where player_id = %s and fixture_id = %s
        order by market, captured_at desc
        """,
        (player_id, fixture_id),
    )
    families = {}
    for market, value in cur.fetchall():
        m = LADDER_RE.match(market)
        if m:
            family, threshold = m.group(1), float(m.group(2))
            families.setdefault(family, []).append((threshold, float(value)))
            continue
        m = OVER_RE.match(market)
        if m:
            family, threshold = m.group(1), float(m.group(2))
            families.setdefault(family, []).append((threshold, float(value)))
            continue
        # UNDER_RE matches are deliberately not added - see the regexes'
        # own comment above.
    return families


def compute_offense_player_stats(families):
    per_stat = {}
    for family, stat in LADDER_STAT_MAP.items():
        points = families.get(family)
        if points:
            per_stat[stat] = {"expected_count": round(expected_value_from_points(points), 3), "populated": True}
        else:
            per_stat[stat] = {"expected_count": 0.0, "populated": False}
    for family, stat in ANYTIME_STAT_MAP.items():
        points = families.get(family)
        # only the "N plus" rungs (not O/U) are meaningful for a count ladder
        ladder_only = [(t, p) for t, p in (points or []) if t == int(t)]
        one_plus = next((p for t, p in ladder_only if t == 1), None)
        if one_plus is not None:
            per_stat[stat] = {"expected_count": round(anytime_prob_to_expected_count(one_plus), 3), "populated": True}
        else:
            per_stat[stat] = {"expected_count": 0.0, "populated": False}
    # Real, confirmed-live gap (2026-09-07) - see module docstring.
    for stat in ("rushing_td", "receiving_td", "return_td", "interception_thrown", "fumble_lost", "two_point_conversion"):
        per_stat.setdefault(stat, {"expected_count": 0.0, "populated": False})
    return per_stat


def price_stats(per_stat, applies_to, scoring_rules):
    total = 0.0
    for stat, info in per_stat.items():
        points_per_unit = scoring_rules.get((applies_to, stat))
        if points_per_unit is None:
            info["points"] = 0.0
            continue
        info["points"] = round(info["expected_count"] * points_per_unit, 3)
        total += info["points"]
    return round(total, 3)


def main():
    requested_gw = int(sys.argv[1]) if len(sys.argv) > 1 else None

    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        gameweek = current_gameweek(cur, requested_gw)
        if gameweek is None:
            raise SystemExit("No fixtures in the database yet - run scripts/refresh_nfl.py first.")

        scoring_rules = load_scoring_rules(cur)
        layer_weights = load_layer_weights(cur)
        algorithm_version_id = get_or_create_algorithm_version(cur, scoring_rules, layer_weights)

        cur.execute("select id, team_id, position from players where is_active = true and team_id is not null")
        players = cur.fetchall()

        written, no_fixture, defense_skipped = 0, 0, 0

        for player_id, team_id, position in players:
            fixture_id = find_fixture_for_team(cur, team_id, gameweek)
            if fixture_id is None:
                no_fixture += 1
                continue

            # Always 1.0 here - a bye week (no fixture this gameweek) is
            # already filtered out by the `continue` above. Meaningful once
            # future-gameweek fixtures (and real byes) are ingested.
            fixture_quantity = 1.0
            xmins, status, status_source = lineup_probability(cur, player_id, fixture_id)
            weights_for_position = layer_weights.get((HORIZON, position), {})

            if position == "defense_special":
                # No real live-odds coverage exists for this unit yet -
                # see module docstring. Written honestly as an unpriced
                # zero rather than skipped, so the gap is visible in the
                # data itself, not just in a script comment.
                per_stat = {}
                total_points = 0.0
                live_odds_populated = False
                defense_skipped += 1
            else:
                families = market_odds_by_family(cur, player_id, fixture_id)
                per_stat = compute_offense_player_stats(families)
                total_points = price_stats(per_stat, "offense", scoring_rules)
                live_odds_populated = any(v["populated"] for v in per_stat.values())

            total_points = round(total_points * xmins, 3)

            per_layer = {
                "lineup_status": {"probability": xmins, "status": status, "source": status_source},
                "form": {"populated": False, "weight": weights_for_position.get("form")},
                "fixture_quantity": {"populated": True, "value": fixture_quantity, "weight": weights_for_position.get("fixture_quantity")},
                "fixture_quality": {"populated": False, "weight": weights_for_position.get("fixture_quality")},
                "live_odds": {"populated": live_odds_populated, "weight": weights_for_position.get("live_odds")},
            }
            data_confidence = round(xmins * (1.0 if live_odds_populated else 0.0), 3)

            cur.execute(
                """
                insert into projections
                    (player_id, gameweek, horizon, algorithm_version_id, total_points, rating, per_stat, per_layer, data_confidence)
                values (%s, %s, %s, %s, %s, null, %s, %s, %s)
                on conflict (player_id, gameweek, horizon, algorithm_version_id) do update set
                    total_points = excluded.total_points,
                    per_stat = excluded.per_stat,
                    per_layer = excluded.per_layer,
                    data_confidence = excluded.data_confidence,
                    created_at = now()
                """,
                (player_id, gameweek, HORIZON, algorithm_version_id, total_points, json.dumps(per_stat), json.dumps(per_layer), data_confidence),
            )
            written += 1

        conn.commit()
        print(
            f"Gameweek {gameweek}, horizon {HORIZON}: {written} projections written "
            f"(algorithm_version {algorithm_version_id}), {no_fixture} skipped (no fixture this gameweek), "
            f"{defense_skipped} defense_special rows written with 0 live-odds coverage (known gap, see module docstring)."
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
