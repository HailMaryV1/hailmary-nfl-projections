"""
compute_projections.py
-------------------------
The real projection engine, v1. Turns the raw rows Phase 2 ingested (real
Spreadex ladder/O-U odds, real lineup status) into a priced "Projected
Points" number per player for the current gameweek.

READ THIS BEFORE ASSUMING SOMETHING IS MISSING:

- Horizons 2/3/5 are real, but built differently from horizon 1, and
  necessarily less precise - see `compute_multi_week_projection` below.
  Horizon 1 is the only one with real live odds (Spreadex/FIC) for every
  stat; gameweeks 2+ have no market posted yet (bookmakers don't price a
  game that's 2+ weeks out), so those weeks scale horizon 1's own real
  per-stat numbers by a real, market-derived opponent-strength multiplier
  (Sharp Football Analysis's Vegas-win-total-based model, via
  `team_schedule_difficulty`) rather than repricing from scratch. A real
  bye week within the horizon window contributes exactly 0, not a guess.
  This is a genuine, if simplified, estimate for future weeks - not as
  precise as horizon 1's live-odds pricing, and documented as such in
  `per_layer.live_odds`/`fixture_quality` for anyone reading a multi-week
  projection.
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
- rushing_td and receiving_td individually still have NO signal (a real,
  live "Score Any TD" market exists - see `anytime_td` below - but it
  doesn't distinguish which type of TD, so the two stay at 0 each).
  `anytime_td` (priced via PRICING_ALIAS, since rushing_td and
  receiving_td are confirmed identical at 6pts) carries the real combined
  signal instead - sourced from fantasyinfocentral.com's real, live
  Caesars sportsbook line (found 2026-09-07 after two other real
  anytime-TD sources, Oddschecker and Midnite, both actively blocked
  automated access - see docs/data-and-weights.md for the full trail).
  Spreadex itself still has no standalone rushing/receiving touchdown
  market at all - worth rechecking closer to kickoff.
- defense_special has NO player-level live-odds coverage (the one market
  that existed for it, Sacks, was deliberately excluded in Phase 2 for
  pricing individual defenders this project's schema can't represent - see
  scrape_spreadex_nfl_props.py). Its projection is instead built from real
  game-level odds already ingested for every fixture (RotoWire's spread +
  total): the opponent's expected points is derived from those, then
  turned into an expected points-allowed score via a Normal-distribution
  approximation across FanTeam's real tiers (see stat_math.
  points_allowed_distribution). This is genuinely a Fixture Quality signal,
  not Live Odds - `per_layer.fixture_quality.populated` reflects that.
  Individual defensive-play stats (sacks, turnovers, blocked kicks,
  defensive/return TDs) still have no real data source and stay at 0 -
  reported plainly in the run summary below, not hidden.

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
from stat_math import (  # noqa: E402
    POINTS_ALLOWED_TIERS,
    anytime_prob_to_expected_count,
    expected_value_from_points,
    fixture_quality_multiplier,
    points_allowed_distribution,
)

HORIZON = 1
MULTI_WEEK_HORIZONS = [2, 3, 5]
MAX_GAMEWEEK = 18

# market family -> (scoring stat, estimator)
LADDER_STAT_MAP = {
    "passing_yards": "passing_yards",
    "rushing_yards": "rushing_yards",
    "receiving_yards": "receiving_yards",
    "total_receptions": "reception",
}
ANYTIME_STAT_MAP = {
    "passing_touchdowns": "passing_td",
    # Real "Score Any TD" prop (rushing OR receiving, not split) - found
    # 2026-09-07 on fantasyinfocentral.com after two live bookmaker-odds
    # sources (Oddschecker, Midnite) both actively blocked automated
    # access. Priced via PRICING_ALIAS below since rushing_td and
    # receiving_td are confirmed identical (6pts each) in the real
    # scoring rules - which bucket's rate is borrowed doesn't matter.
    "anytime_td": "anytime_td",
}

# stat -> the scoring_rules stat whose rate actually prices it. Only
# needed for a stat with no scoring_rules row of its own (anytime_td
# genuinely doesn't distinguish rush vs. reception, so it has no single
# real row to look up - see ANYTIME_STAT_MAP above for why rushing_td's
# rate is a safe stand-in).
PRICING_ALIAS = {"anytime_td": "rushing_td"}

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
        "select id, home_team_id, away_team_id from fixtures where (home_team_id = %s or away_team_id = %s) and gameweek = %s",
        (team_id, team_id, gameweek),
    )
    return cur.fetchone()


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
    # rushing_td/receiving_td stay at 0 individually - the real signal
    # (anytime_td, above) doesn't distinguish which type of TD, only that
    # one happened. Still a real, confirmed gap for return_td and the
    # smaller offense stats below - no market found for any of them yet.
    for stat in ("rushing_td", "receiving_td", "return_td", "interception_thrown", "fumble_lost", "two_point_conversion"):
        per_stat.setdefault(stat, {"expected_count": 0.0, "populated": False})
    return per_stat


def opponent_expected_points(cur, fixture_id, team_id, home_team_id, away_team_id):
    """Real market-derived opponent scoring expectation, from the same
    game_odds rows RotoWire already gave us (spread + total). Standard
    team-total split: home_expected = (total - home_spread) / 2,
    away_expected = (total + home_spread) / 2 (our home_spread convention:
    negative = home favored - confirmed against real data in
    import_rotowire_lineups.py). Returns None if no real odds are posted
    yet for this fixture - never guessed."""
    cur.execute(
        """
        select home_spread, total_points_over_under from game_odds
        where fixture_id = %s and home_spread is not null and total_points_over_under is not null
        order by captured_at desc limit 1
        """,
        (fixture_id,),
    )
    row = cur.fetchone()
    if row is None:
        return None
    home_spread, total = float(row[0]), float(row[1])
    home_expected = (total - home_spread) / 2
    away_expected = (total + home_spread) / 2
    return away_expected if team_id == home_team_id else home_expected


def compute_defense_special_stats(cur, fixture_id, team_id, home_team_id, away_team_id):
    per_stat = {}
    opponent_points = opponent_expected_points(cur, fixture_id, team_id, home_team_id, away_team_id)
    if opponent_points is not None:
        for stat, prob in points_allowed_distribution(opponent_points).items():
            per_stat[stat] = {"expected_count": round(prob, 4), "populated": True}
    else:
        for stat, _low, _high in POINTS_ALLOWED_TIERS:
            per_stat[stat] = {"expected_count": 0.0, "populated": False}
    # Individual defensive-play stats (sacks, turnovers, blocked kicks,
    # defensive/return TDs) - no real team-level data source found yet
    # (the only market that existed, Sacks, prices individual defenders
    # this schema can't represent - see scrape_spreadex_nfl_props.py).
    for stat in ("sack", "interception", "fumble_recovery", "safety", "blocked_kick", "defensive_td", "return_td"):
        per_stat[stat] = {"expected_count": 0.0, "populated": False}
    return per_stat, opponent_points


def price_stats(per_stat, applies_to, scoring_rules, xmins=1.0):
    """Prices every stat and applies the real lineup-status probability
    directly to each one (not just the aggregate) - a player projected at
    75% likely to play should show 75%-scaled numbers in EVERY stat row,
    not just in the total. Confirmed live 2026-09-08 this was a real bug:
    total_points was being scaled by xmins after price_stats returned, but
    the stored per_stat rows never were, so a questionable player's own
    explainability page showed a per-stat breakdown that didn't sum to
    their displayed total (Christian McCaffrey: total 17.078 vs a real
    per_stat sum of 22.771 - exactly the un-discounted number, off by
    precisely his 0.75 xmins probability)."""
    total = 0.0
    for stat, info in per_stat.items():
        rate_stat = PRICING_ALIAS.get(stat, stat)
        points_per_unit = scoring_rules.get((applies_to, rate_stat))
        info["expected_count"] = round(info["expected_count"] * xmins, 3)
        if points_per_unit is None:
            info["points"] = 0.0
            continue
        info["points"] = round(info["expected_count"] * points_per_unit, 3)
        total += info["points"]
    return round(total, 3)


def load_league_win_total_stats(cur):
    """Real, self-calibrating (not hardcoded) mean/stdev of every team's
    own Vegas-projected win total, computed fresh from whatever real
    schedule-difficulty data is currently ingested - each of the 32 real
    teams' own win total is picked up once, from wherever it appears as
    someone else's opponent. A handful of real rows are missing this value
    (confirmed live 2026-09-08: every appearance of Green Bay as an
    opponent has a null win total - a rendering quirk on the source site
    for a 2-letter team code, not something worth guessing at) - excluded
    from the distribution rather than treated as 0."""
    cur.execute(
        """
        select distinct on (opponent_team_id) opponent_win_total
        from team_schedule_difficulty
        where opponent_team_id is not null and opponent_win_total is not null
        """
    )
    values = [float(row[0]) for row in cur.fetchall()]
    if len(values) < 2:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, variance ** 0.5


def load_schedule_difficulty(cur):
    """Every real team_schedule_difficulty row, once - only 32 teams x 18
    weeks (576 rows total), trivially small to hold in memory. Avoids a
    separate round-trip per player per horizon (603 players x 3 horizons
    would otherwise be ~1800 individual queries for data that never
    changes within a single run)."""
    cur.execute("select team_id, gameweek, opponent_team_id, is_bye, opponent_win_total from team_schedule_difficulty")
    by_team = {}
    for team_id, gameweek, opponent_team_id, is_bye, opponent_win_total in cur.fetchall():
        by_team.setdefault(team_id, {})[gameweek] = (gameweek, opponent_team_id, is_bye, opponent_win_total)
    return by_team


def get_schedule_window(schedule_by_team, team_id, start_gw, num_weeks):
    """Real (gameweek, opponent_team_id, is_bye, opponent_win_total) rows
    for [start_gw, start_gw+num_weeks-1], clipped to real gameweeks
    (1-18) - a horizon requested near the end of the season simply gets a
    shorter real window, not padded with invented future weeks."""
    end_gw = min(start_gw + num_weeks - 1, MAX_GAMEWEEK)
    team_schedule = schedule_by_team.get(team_id, {})
    return [team_schedule[gw] for gw in range(start_gw, end_gw + 1) if gw in team_schedule]


def compute_multi_week_projection(base, schedule_window, current_gw, league_mean, league_std):
    """Sums a player's real per-stat production across a multi-week
    window: the current gameweek's own contribution is `base`'s real
    (Live-Odds-priced) numbers, used exactly as computed for horizon 1 -
    every OTHER week in the window scales those same per-stat numbers by
    a real opponent-strength multiplier (or 1.0 if that week's real
    matchup data isn't in the window at all, e.g. beyond gameweek 18), and
    a real bye week contributes nothing. Returns (total_points, per_stat,
    real_games_used, weeks_in_window, multipliers_used)."""
    per_stat = {stat: {"expected_count": 0.0, "points": 0.0, "populated": info["populated"]} for stat, info in base["per_stat"].items()}
    real_games, multipliers_used = 0, []

    schedule_by_gw = {row[0]: row for row in schedule_window}
    weeks_in_window = len(schedule_window) or 1

    for gw, row in schedule_by_gw.items():
        _gw, _opponent_team_id, is_bye, opponent_win_total = row
        if is_bye:
            continue
        if gw == current_gw:
            multiplier = 1.0  # this week is base's own real, already-priced number - not re-scaled
        elif opponent_win_total is not None:
            multiplier = fixture_quality_multiplier(float(opponent_win_total), league_mean, league_std)
        else:
            multiplier = 1.0
        multipliers_used.append(multiplier)
        real_games += 1
        for stat, info in base["per_stat"].items():
            per_stat[stat]["expected_count"] += info["expected_count"] * multiplier
            per_stat[stat]["points"] += info["points"] * multiplier

    for stat in per_stat:
        per_stat[stat]["expected_count"] = round(per_stat[stat]["expected_count"], 3)
        per_stat[stat]["points"] = round(per_stat[stat]["points"], 3)

    total_points = round(sum(s["points"] for s in per_stat.values()), 3)
    return total_points, per_stat, real_games, weeks_in_window, multipliers_used


def upsert_projection(cur, player_id, gameweek, horizon, algorithm_version_id, total_points, per_stat, per_layer, data_confidence):
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
        (player_id, gameweek, horizon, algorithm_version_id, total_points, json.dumps(per_stat), json.dumps(per_layer), data_confidence),
    )


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
        base_results = {}  # player_id -> real horizon-1 result, reused below for multi-week horizons

        for player_id, team_id, position in players:
            fixture_row = find_fixture_for_team(cur, team_id, gameweek)
            if fixture_row is None:
                no_fixture += 1
                continue
            fixture_id, home_team_id, away_team_id = fixture_row

            # Always 1.0 here - a bye week (no fixture this gameweek) is
            # already filtered out by the `continue` above.
            fixture_quantity = 1.0
            xmins, status, status_source = lineup_probability(cur, player_id, fixture_id)
            weights_for_position = layer_weights.get((HORIZON, position), {})

            if position == "defense_special":
                # No player-level bookmaker odds exist for this unit (see
                # module docstring), but points-allowed - a real, large
                # share of D/ST scoring - can be derived from the same
                # real game_odds (spread + total) already ingested for
                # every fixture: a heavily-favored team's opponent is
                # priced to score fewer points, which this unit is
                # rewarded for conceding fewer of. This is a real
                # Fixture Quality signal, not a Live Odds one.
                per_stat, opponent_points = compute_defense_special_stats(cur, fixture_id, team_id, home_team_id, away_team_id)
                total_points = price_stats(per_stat, "defense_special", scoring_rules, xmins)
                live_odds_populated = False
                fixture_quality_populated = opponent_points is not None
                if opponent_points is None:
                    defense_skipped += 1
            else:
                fixture_quality_populated = False
                families = market_odds_by_family(cur, player_id, fixture_id)
                per_stat = compute_offense_player_stats(families)
                total_points = price_stats(per_stat, "offense", scoring_rules, xmins)
                live_odds_populated = any(v["populated"] for v in per_stat.values())

            per_layer = {
                "lineup_status": {"probability": xmins, "status": status, "source": status_source},
                "form": {"populated": False, "weight": weights_for_position.get("form")},
                "fixture_quantity": {"populated": True, "value": fixture_quantity, "weight": weights_for_position.get("fixture_quantity")},
                "fixture_quality": {"populated": fixture_quality_populated, "weight": weights_for_position.get("fixture_quality")},
                "live_odds": {"populated": live_odds_populated, "weight": weights_for_position.get("live_odds")},
            }
            data_confidence = round(xmins * (1.0 if (live_odds_populated or fixture_quality_populated) else 0.0), 3)

            upsert_projection(cur, player_id, gameweek, HORIZON, algorithm_version_id, total_points, per_stat, per_layer, data_confidence)
            written += 1
            base_results[player_id] = {
                "team_id": team_id, "position": position, "per_stat": per_stat, "per_layer": per_layer,
                "data_confidence": data_confidence,
            }

        conn.commit()
        print(
            f"Gameweek {gameweek}, horizon {HORIZON}: {written} projections written "
            f"(algorithm_version {algorithm_version_id}), {no_fixture} skipped (no fixture this gameweek), "
            f"{defense_skipped} defense_special row(s) with no real game_odds posted yet (fell back to 0)."
        )

        # Multi-week horizons - real for every player who got a real
        # horizon-1 result above, using team_schedule_difficulty (see
        # module docstring for the real methodology and its limits).
        league_mean, league_std = load_league_win_total_stats(cur)
        schedule_by_team = load_schedule_difficulty(cur)
        multi_week_written = 0
        for h in MULTI_WEEK_HORIZONS:
            for player_id, base in base_results.items():
                schedule_window = get_schedule_window(schedule_by_team, base["team_id"], gameweek, h)
                if not schedule_window:
                    continue
                total_points, per_stat, real_games, weeks_in_window, multipliers = compute_multi_week_projection(
                    base, schedule_window, gameweek, league_mean, league_std
                )
                weights_for_position = layer_weights.get((h, base["position"]), {})
                per_layer = {
                    "lineup_status": base["per_layer"]["lineup_status"],
                    "form": {"populated": False, "weight": weights_for_position.get("form")},
                    "fixture_quantity": {"populated": True, "value": round(real_games / weeks_in_window, 3), "weight": weights_for_position.get("fixture_quantity")},
                    "fixture_quality": {
                        "populated": True,
                        "value": round(sum(multipliers) / len(multipliers), 3) if multipliers else None,
                        "weight": weights_for_position.get("fixture_quality"),
                    },
                    "live_odds": {"populated": True, "weight": weights_for_position.get("live_odds")},
                }
                data_confidence = round(base["data_confidence"] * (real_games / weeks_in_window), 3)
                upsert_projection(cur, player_id, gameweek, h, algorithm_version_id, total_points, per_stat, per_layer, data_confidence)
                multi_week_written += 1
            conn.commit()

        print(f"Multi-week horizons {MULTI_WEEK_HORIZONS}: {multi_week_written} projections written across all horizons.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
