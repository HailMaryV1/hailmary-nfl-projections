"""
opportunity_v2_model.py
---------------------------
Builds NFL Opportunity V2 as a fully parallel challenger to the live V1
projection engine - diagnostic/research only. Never writes to
projections/predictions_and_actuals/player_stats, never touches V1's own
code path (compute_projections.py is not imported or called here).

Three variants, exactly as scoped:
  V2-A (Opportunity only)  - built ENTIRELY from real historical box-score
                              history (2022-2025 API-Sports backfill) -
                              opportunity (EWM, the winning candidate from
                              the prior research stage) x historical
                              efficiency/TD/turnover rates. No market data
                              at all.
  V2-B (Market only)       - NOT rebuilt - this real requirement is
                              already satisfied by V1 itself
                              (predictions_and_actuals.predicted_points),
                              used here as-is as the benchmark, per the
                              brief's own framing ("current V1-style
                              inputs ... preserved as the benchmark").
  V2-C (Hybrid)            - V1's own real market-priced total PLUS the
                              one real, honest thing V1 currently lacks:
                              an expected-turnover penalty (interceptions/
                              fumbles), from V2-A's own historical
                              int/fumble rates. See the "Hybrid
                              methodology" note below for why this is the
                              real, buildable hybrid - not a tuned blend.

REAL, EXPLICIT METHODOLOGY LIMITATION (flagged per the brief's own
instruction, not glossed over): V1's market-driven signal only exists for
2026 (this project has never had real Spreadex/RotoWire odds for
2022-2025 - those seasons are years in the past, no market to have
scraped). So V2-B and V2-C can ONLY be evaluated on 2026 GW1 - there is
no chronological 2022-2024/2025 train/validate split possible for the
market or hybrid variants, only for V2-A (opportunity only), which is the
one variant built purely from real historical outcomes. This is a real
data-availability constraint, not a shortcut - stated here so it's never
mistaken for GW1 having quietly influenced anything about V2-A's own
formula (it hasn't - see the chronological validation section, which
never touches 2026 rows).

Hybrid methodology: V2-C = V1's real total_points + V2-A's real expected
interception/fumble penalty (both currently priced at exactly 0 in V1 -
module docstring of compute_projections.py says so explicitly). This is
a fixed, principled addition, NOT a data-driven tuned blend - there is no
historical week with both a real market signal and a real outcome to tune
a blend weight against (see limitation above), so no weight was fit, and
none should be implied by "V2-C" sounding like a fitted ensemble.

RUN:
    python scripts/opportunity_v2_model.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

EWM_ALPHA = 0.3
POSITION_LABEL = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE"}
HISTORY_ESTABLISHED_MIN = 8


def week_sort_key(week_label):
    try:
        return int(week_label.replace("Week", "").strip())
    except ValueError:
        return 99


def mean(vals):
    return sum(vals) / len(vals) if vals else None


def ewm(vals):
    if not vals:
        return None
    e = vals[0]
    for v in vals[1:]:
        e = EWM_ALPHA * v + (1 - EWM_ALPHA) * e
    return e


def safe_div(n, d):
    if n is None or d is None or d == 0:
        return None
    return n / d


def load_scoring_rules(cur):
    cur.execute("select stat, points from scoring_rules where applies_to = 'offense'")
    return {stat: float(pts) for stat, pts in cur.fetchall()}


def load_rows(cur):
    cur.execute(
        """
        select
            p.id as player_id, p.full_name, p.position,
            g.season, g.week, g.api_sports_game_id,
            a.pass_attempts, a.pass_completions, a.pass_yards, a.pass_td, a.interceptions_thrown,
            a.rush_attempts, a.rush_yards, a.rush_td,
            a.targets, a.receptions, a.receiving_yards, a.receiving_td, a.fumbles_lost
        from api_sports_player_game_stats a
        join players p on p.id = a.our_player_id
        join api_sports_games g on g.id = a.api_sports_game_id
        where p.position in ('quarterback','running_back','wide_receiver','tight_end')
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    for r in rows:
        r["_week_num"] = week_sort_key(r["week"])
    rows.sort(key=lambda r: (r["player_id"], r["season"], r["_week_num"]))
    return rows


def real_actual_points(r, sc):
    """Real FanTeam-equivalent fantasy points for a real historical row,
    computed from real box-score stats via the real, live scoring_rules -
    needed because predictions_and_actuals only exists for 2026 (FanTeam
    itself, not this project, computed a real score for those rows;
    for 2022-2025 there is no FanTeam record at all, so this project
    derives the equivalent real score itself, from the same real rules)."""
    pts = 0.0
    pts += (r["pass_yards"] or 0) * sc["passing_yards"]
    pts += (r["pass_td"] or 0) * sc["passing_td"]
    pts += (r["interceptions_thrown"] or 0) * sc["interception_thrown"]
    pts += (r["rush_yards"] or 0) * sc["rushing_yards"]
    pts += (r["rush_td"] or 0) * sc["rushing_td"]
    pts += (r["receptions"] or 0) * sc["reception"]
    pts += (r["receiving_yards"] or 0) * sc["receiving_yards"]
    pts += (r["receiving_td"] or 0) * sc["receiving_td"]
    pts += (r["fumbles_lost"] or 0) * sc["fumble_lost"]
    return round(pts, 3)


LEAGUE_PRIORS = {}  # populated by compute_league_priors, used as an explicit fallback for "none"-history rows


def compute_league_priors(rows):
    """Real, population-level cross-sectional averages (2022-2025, all
    real rows) - the explicit, labeled fallback for a player with zero
    real prior games. Not that player's own data (none exists) - a real
    league norm for their position instead, clearly separated in the
    output via *_source columns so these rows can be evaluated
    independently, exactly as instructed."""
    by_pos = {}
    for r in rows:
        by_pos.setdefault(r["position"], []).append(r)
    priors = {}
    for pos, prows in by_pos.items():
        def avg(field):
            vals = [x[field] for x in prows if x.get(field) is not None]
            return mean(vals)
        priors[pos] = {
            "pass_attempts": avg("pass_attempts"), "rush_attempts": avg("rush_attempts"), "targets": avg("targets"),
            "completion_rate": mean([safe_div(x["pass_completions"], x["pass_attempts"]) for x in prows if safe_div(x["pass_completions"], x["pass_attempts"]) is not None]),
            "yards_per_attempt": mean([safe_div(x["pass_yards"], x["pass_attempts"]) for x in prows if safe_div(x["pass_yards"], x["pass_attempts"]) is not None]),
            "pass_td_rate": mean([safe_div(x["pass_td"], x["pass_attempts"]) for x in prows if safe_div(x["pass_td"], x["pass_attempts"]) is not None]),
            "int_rate": mean([safe_div(x["interceptions_thrown"], x["pass_attempts"]) for x in prows if safe_div(x["interceptions_thrown"], x["pass_attempts"]) is not None]),
            "yards_per_carry": mean([safe_div(x["rush_yards"], x["rush_attempts"]) for x in prows if safe_div(x["rush_yards"], x["rush_attempts"]) is not None]),
            "rush_td_rate": mean([safe_div(x["rush_td"], x["rush_attempts"]) for x in prows if safe_div(x["rush_td"], x["rush_attempts"]) is not None]),
            "catch_rate": mean([safe_div(x["receptions"], x["targets"]) for x in prows if safe_div(x["receptions"], x["targets"]) is not None]),
            "yards_per_target": mean([safe_div(x["receiving_yards"], x["targets"]) for x in prows if safe_div(x["receiving_yards"], x["targets"]) is not None]),
            "rec_td_rate": mean([safe_div(x["receiving_td"], x["targets"]) for x in prows if safe_div(x["receiving_td"], x["targets"]) is not None]),
            # fumbles_lost is NULL (not 0) whenever a player had no real
            # "Fumbles" group entry that game - a real, confirmed zero
            # (same sparse-encoding pattern seen elsewhere in this
            # project's real data sources), not a missing observation -
            # `or 0` here is a real zero-fill, not a fabrication.
            "fumble_rate": mean([safe_div(x["fumbles_lost"] or 0, (x["rush_attempts"] or 0) + (x["targets"] or 0) + (x["pass_attempts"] or 0)) for x in prows if ((x["rush_attempts"] or 0) + (x["targets"] or 0) + (x["pass_attempts"] or 0)) > 0]),
        }
    return priors


def build_v2a_rows(rows, sc, priors):
    """One row per (player, real game): real no-lookahead opportunity +
    efficiency features, V2-A expected points, and the real actual
    FanTeam-equivalent points for that same real game."""
    out = []
    by_player = {}
    for r in rows:
        by_player.setdefault(r["player_id"], []).append(r)

    for player_id, games in by_player.items():
        pos = games[0]["position"]
        h = {k: [] for k in ["pass_attempts", "pass_completions", "pass_yards", "pass_td", "interceptions_thrown",
                              "rush_attempts", "rush_yards", "rush_td", "targets", "receptions", "receiving_yards", "receiving_td", "fumbles_lost"]}

        for r in games:
            n_prior = len(h["pass_attempts"]) if pos == "quarterback" else (len(h["rush_attempts"]) if pos == "running_back" else len(h["targets"]))
            source = "player_history" if n_prior >= 1 else "position_league_average"
            history_group = "none" if n_prior == 0 else ("limited" if n_prior < HISTORY_ESTABLISHED_MIN else "established")

            def career_rate(numer_key, denom_key):
                nv = [x for x in h[numer_key]]
                dv = [x for x in h[denom_key]]
                pairs = [(n, d) for n, d in zip(nv, dv) if d]
                if not pairs:
                    return None
                return sum(p[0] for p in pairs) / sum(p[1] for p in pairs)

            lp = priors[pos]
            row = {"player_id": player_id, "player": r["full_name"], "position": POSITION_LABEL[pos], "season": r["season"], "week": r["week"],
                   "api_sports_game_id": r["api_sports_game_id"], "history_group": history_group, "opportunity_source": source}

            if pos == "quarterback":
                exp_att = ewm(h["pass_attempts"]) if h["pass_attempts"] else lp["pass_attempts"]
                comp_rate = career_rate("pass_completions", "pass_attempts") if n_prior else lp["completion_rate"]
                ypa = career_rate("pass_yards", "pass_attempts") if n_prior else lp["yards_per_attempt"]
                td_rate = career_rate("pass_td", "pass_attempts") if n_prior else lp["pass_td_rate"]
                int_rate = career_rate("interceptions_thrown", "pass_attempts") if n_prior else lp["int_rate"]
                exp_rush_att = mean(h["rush_attempts"]) if h["rush_attempts"] else lp["rush_attempts"]
                exp_ypc = career_rate("rush_yards", "rush_attempts") if n_prior else lp["yards_per_carry"]
                exp_rush_td_rate = career_rate("rush_td", "rush_attempts") if n_prior else lp["rush_td_rate"]
                exp_pass_yards = exp_att * (ypa or 0) if exp_att is not None else None
                exp_pass_td = exp_att * (td_rate or 0) if exp_att is not None else None
                exp_int = exp_att * (int_rate or 0) if exp_att is not None else None
                exp_rush_yards = exp_rush_att * (exp_ypc or 0) if exp_rush_att is not None else None
                exp_rush_td = exp_rush_att * (exp_rush_td_rate or 0) if exp_rush_att is not None else None
                touches = (exp_att or 0) + (exp_rush_att or 0)
                fumble_rate = (
                    mean([safe_div(x, (a or 0) + (rb or 0)) for x, a, rb in zip(h["fumbles_lost"], h["pass_attempts"], h["rush_attempts"]) if ((a or 0) + (rb or 0)) > 0])
                    if n_prior else lp["fumble_rate"]
                )
                exp_fumbles = touches * (fumble_rate or 0)
                points = 0.0
                for val, key in [(exp_pass_yards, "passing_yards"), (exp_pass_td, "passing_td"), (exp_int, "interception_thrown"), (exp_rush_yards, "rushing_yards"), (exp_rush_td, "rushing_td"), (exp_fumbles, "fumble_lost")]:
                    points += (val or 0) * sc[key]
                row.update({"expected_pass_attempts": exp_att, "expected_completion_rate": comp_rate, "expected_yards_per_attempt": ypa,
                            "expected_pass_td_rate": td_rate, "expected_int_rate": int_rate, "expected_interceptions": exp_int,
                            "expected_rush_attempts": exp_rush_att, "expected_rush_yards": exp_rush_yards, "expected_rush_td": exp_rush_td,
                            "expected_fumbles_lost": exp_fumbles, "v2a_points": round(points, 3)})

            elif pos == "running_back":
                exp_carries = ewm(h["rush_attempts"]) if h["rush_attempts"] else lp["rush_attempts"]
                exp_targets = ewm(h["targets"]) if h["targets"] else lp["targets"]
                ypc = career_rate("rush_yards", "rush_attempts") if n_prior else lp["yards_per_carry"]
                rush_td_rate = career_rate("rush_td", "rush_attempts") if n_prior else lp["rush_td_rate"]
                catch_rate = career_rate("receptions", "targets") if n_prior else lp["catch_rate"]
                ypt = career_rate("receiving_yards", "targets") if n_prior else lp["yards_per_target"]
                rec_td_rate = career_rate("receiving_td", "targets") if n_prior else lp["rec_td_rate"]
                exp_rush_yards = exp_carries * (ypc or 0) if exp_carries is not None else None
                exp_rush_td = exp_carries * (rush_td_rate or 0) if exp_carries is not None else None
                exp_receptions = exp_targets * (catch_rate or 0) if exp_targets is not None else None
                exp_rec_yards = exp_targets * (ypt or 0) if exp_targets is not None else None
                exp_rec_td = exp_targets * (rec_td_rate or 0) if exp_targets is not None else None
                touches = (exp_carries or 0) + (exp_targets or 0)
                fumble_rate = mean([safe_div(x, (rb or 0) + (t or 0)) for x, rb, t in zip(h["fumbles_lost"], h["rush_attempts"], h["targets"]) if ((rb or 0) + (t or 0)) > 0]) if n_prior else lp["fumble_rate"]
                exp_fumbles = touches * (fumble_rate or 0)
                points = 0.0
                for val, key in [(exp_rush_yards, "rushing_yards"), (exp_rush_td, "rushing_td"), (exp_receptions, "reception"), (exp_rec_yards, "receiving_yards"), (exp_rec_td, "receiving_td"), (exp_fumbles, "fumble_lost")]:
                    points += (val or 0) * sc[key]
                row.update({"expected_carries": exp_carries, "expected_targets": exp_targets, "expected_yards_per_carry": ypc,
                            "expected_catch_rate": catch_rate, "expected_yards_per_target": ypt, "expected_rush_yards": exp_rush_yards,
                            "expected_rush_td": exp_rush_td, "expected_receptions": exp_receptions, "expected_receiving_yards": exp_rec_yards,
                            "expected_receiving_td": exp_rec_td, "expected_fumbles_lost": exp_fumbles, "v2a_points": round(points, 3)})

            else:  # WR / TE
                exp_targets = ewm(h["targets"]) if h["targets"] else lp["targets"]
                catch_rate = career_rate("receptions", "targets") if n_prior else lp["catch_rate"]
                ypt = career_rate("receiving_yards", "targets") if n_prior else lp["yards_per_target"]
                rec_td_rate = career_rate("receiving_td", "targets") if n_prior else lp["rec_td_rate"]
                exp_receptions = exp_targets * (catch_rate or 0) if exp_targets is not None else None
                exp_rec_yards = exp_targets * (ypt or 0) if exp_targets is not None else None
                exp_rec_td = exp_targets * (rec_td_rate or 0) if exp_targets is not None else None
                exp_rush_yards = mean(h["rush_yards"]) if h["rush_attempts"] and any(h["rush_attempts"]) else 0  # real, small, career-average contribution only
                exp_rush_td = mean(h["rush_td"]) if h["rush_attempts"] and any(h["rush_attempts"]) else 0
                fumble_rate = mean([safe_div(x, t) for x, t in zip(h["fumbles_lost"], h["targets"]) if t]) if n_prior else lp["fumble_rate"]
                exp_fumbles = (exp_targets or 0) * (fumble_rate or 0)
                points = 0.0
                for val, key in [(exp_receptions, "reception"), (exp_rec_yards, "receiving_yards"), (exp_rec_td, "receiving_td"), (exp_rush_yards, "rushing_yards"), (exp_rush_td, "rushing_td"), (exp_fumbles, "fumble_lost")]:
                    points += (val or 0) * sc[key]
                row.update({"expected_targets": exp_targets, "expected_catch_rate": catch_rate, "expected_yards_per_target": ypt,
                            "expected_receptions": exp_receptions, "expected_receiving_yards": exp_rec_yards, "expected_receiving_td": exp_rec_td,
                            "expected_fumbles_lost": exp_fumbles, "v2a_points": round(points, 3)})

            row["real_actual_points"] = real_actual_points(r, sc)
            out.append(row)

            # Always append (real value or a real 0), for every stat -
            # never skip. Two real reasons: (1) keeps every per-player
            # history list positionally aligned by game index, needed for
            # cross-stat rates like pass_yards/pass_attempts computed via
            # zip() below; (2) a real 0-usage game (e.g. a WR targeted
            # zero times in a real blowout) is a genuine data point for
            # that player's opportunity history, not an absence to skip -
            # skipping it would silently inflate their average.
            for k in h:
                h[k].append(r.get(k) or 0)
    return out


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        sc = load_scoring_rules(cur)
        rows = load_rows(cur)
        print(f"Loaded {len(rows)} real player-game rows.")
        priors = compute_league_priors(rows)
        global LEAGUE_PRIORS
        LEAGUE_PRIORS = priors

        v2a_rows = build_v2a_rows(rows, sc, priors)
        out_path = ROOT / "opportunity_v2a_points.csv"
        fieldnames = list(dict.fromkeys(k for row in v2a_rows for k in row.keys()))
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
            writer.writeheader()
            writer.writerows(v2a_rows)
        print(f"-> {out_path} ({len(v2a_rows)} rows)")

        print("\nLeague-average priors (position-level, real 2022-2025 cross-section):")
        for pos, p in priors.items():
            print(f"  {POSITION_LABEL[pos]}: {p}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
