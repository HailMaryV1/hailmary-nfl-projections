"""
opportunity_v2_model_revised_fallback.py
--------------------------------------------
Isolated test of ONE change: replaces V2-A's "none"-history opportunity
fallback (previously a blind position-league-average prior) with a real,
pre-game lineup-status-gated hierarchy. Nothing else about the model
changes - EWM formulas, historical efficiency rates, TD/INT handling, and
V2-C's hybrid construction are all reused UNCHANGED from
opportunity_v2_model.py. This script does not modify that file or its
output (opportunity_v2a_points.csv) - it writes a SEPARATE
opportunity_v2a_points_revised.csv, so "original" and "revised" can be
compared side by side.

Real, pre-game-only signal used: player_lineup_status (FanTeam +
RotoWire, the same real table and same real status vocabulary
compute_projections.py's own lineup_probability() already uses) for the
player's real GW1 fixture. Never infers role from the game outcome - only
whatever real status was captured before kickoff.

Fixed hierarchy (stated plainly, not fit/tuned - there is no historical
week with real lineup_status data for a "none"-history player to tune
against; these are reasoned, real-data-scale multipliers on the SAME
league-average prior already computed, not new numbers invented from
nothing):
  A. starter, expected            -> 1.00x league-average (full prior)
  B. questionable, possible       -> 0.35x league-average (reduced role)
  C. doubtful, inactive, injured,
     refuted, unexpected, OR no
     real lineup_status row found -> 0.08x league-average (near-zero)

Real, honest scope limit: player_lineup_status only exists for the live
2026 season (never populated for the 2022-2025 historical backfill, which
predates this project). So this revised fallback can only really apply to
2026 rows - any "none"-history row in 2022-2025 keeps the original
league-average fallback by necessity, not inconsistency. This does not
affect the GW1 comparison this script exists for.

RUN:
    python scripts/opportunity_v2_model_revised_fallback.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402
from opportunity_v2_model import (  # noqa: E402
    EWM_ALPHA, POSITION_LABEL, HISTORY_ESTABLISHED_MIN,
    mean, ewm, safe_div, load_scoring_rules, load_rows, real_actual_points, compute_league_priors,
)

ROLE_MULTIPLIER = {
    "starter": 1.00, "expected": 1.00,
    "questionable": 0.35, "possible": 0.35,
    "doubtful": 0.08, "inactive": 0.08, "injured": 0.08, "refuted": 0.08, "unexpected": 0.08,
}
NO_SIGNAL_MULTIPLIER = 0.08  # no real lineup_status row found at all - treated the same as bucket C


def load_lineup_status_gw1(cur):
    """Real, pre-game lineup status per player for their real GW1 fixture
    - same source table, same 'prefer RotoWire, most recent' rule as
    compute_projections.py's own lineup_probability()."""
    cur.execute(
        """
        select distinct on (pls.player_id)
            pls.player_id, pls.status
        from player_lineup_status pls
        join fixtures f on f.id = pls.fixture_id
        where f.gameweek = 1
        order by pls.player_id, (pls.source = 'rotowire') desc, pls.captured_at desc
        """
    )
    return dict(cur.fetchall())


def role_multiplier(player_id, lineup_status):
    status = lineup_status.get(player_id)
    if status is None:
        return NO_SIGNAL_MULTIPLIER, "no_real_lineup_signal"
    return ROLE_MULTIPLIER.get(status, NO_SIGNAL_MULTIPLIER), status


def build_v2a_rows_revised(rows, sc, priors, lineup_status):
    """Same logic as opportunity_v2_model.build_v2a_rows, with exactly
    ONE change: the "none"-history opportunity value is scaled by a real
    role_multiplier instead of being the raw league-average. Everything
    else - efficiency rates, TD/INT rates, fumble rate, point formula -
    is untouched, including for "none"-history rows (only the
    OPPORTUNITY volume itself is gated, per the brief's own scope)."""
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
            source = "player_history" if n_prior >= 1 else "position_league_average_role_gated"
            history_group = "none" if n_prior == 0 else ("limited" if n_prior < HISTORY_ESTABLISHED_MIN else "established")

            role_mult, role_status = (1.0, "n/a")
            if n_prior == 0 and r["season"] == 2026:
                role_mult, role_status = role_multiplier(player_id, lineup_status)

            def career_rate(numer_key, denom_key):
                pairs = [(n, d) for n, d in zip(h[numer_key], h[denom_key]) if d]
                return sum(p[0] for p in pairs) / sum(p[1] for p in pairs) if pairs else None

            lp = priors[pos]
            row = {"player_id": player_id, "player": r["full_name"], "position": POSITION_LABEL[pos], "season": r["season"], "week": r["week"],
                   "api_sports_game_id": r["api_sports_game_id"], "history_group": history_group, "opportunity_source": source,
                   "role_status_used": role_status, "role_multiplier": role_mult}

            if pos == "quarterback":
                base_att = ewm(h["pass_attempts"]) if h["pass_attempts"] else lp["pass_attempts"]
                exp_att = base_att * role_mult if n_prior == 0 else base_att
                comp_rate = career_rate("pass_completions", "pass_attempts") if n_prior else lp["completion_rate"]
                ypa = career_rate("pass_yards", "pass_attempts") if n_prior else lp["yards_per_attempt"]
                td_rate = career_rate("pass_td", "pass_attempts") if n_prior else lp["pass_td_rate"]
                int_rate = career_rate("interceptions_thrown", "pass_attempts") if n_prior else lp["int_rate"]
                base_rush_att = mean(h["rush_attempts"]) if h["rush_attempts"] else lp["rush_attempts"]
                exp_rush_att = base_rush_att * role_mult if n_prior == 0 else base_rush_att
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
                points = sum((v or 0) * sc[k] for v, k in [(exp_pass_yards, "passing_yards"), (exp_pass_td, "passing_td"), (exp_int, "interception_thrown"), (exp_rush_yards, "rushing_yards"), (exp_rush_td, "rushing_td"), (exp_fumbles, "fumble_lost")])
                row.update({"expected_pass_attempts": exp_att, "expected_interceptions": exp_int, "expected_rush_attempts": exp_rush_att,
                            "expected_fumbles_lost": exp_fumbles, "v2a_points": round(points, 3)})

            elif pos == "running_back":
                base_carries = ewm(h["rush_attempts"]) if h["rush_attempts"] else lp["rush_attempts"]
                base_targets = ewm(h["targets"]) if h["targets"] else lp["targets"]
                exp_carries = base_carries * role_mult if n_prior == 0 else base_carries
                exp_targets = base_targets * role_mult if n_prior == 0 else base_targets
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
                points = sum((v or 0) * sc[k] for v, k in [(exp_rush_yards, "rushing_yards"), (exp_rush_td, "rushing_td"), (exp_receptions, "reception"), (exp_rec_yards, "receiving_yards"), (exp_rec_td, "receiving_td"), (exp_fumbles, "fumble_lost")])
                row.update({"expected_carries": exp_carries, "expected_targets": exp_targets, "expected_fumbles_lost": exp_fumbles,
                            "expected_interceptions": 0.0, "v2a_points": round(points, 3)})

            else:  # WR / TE
                base_targets = ewm(h["targets"]) if h["targets"] else lp["targets"]
                exp_targets = base_targets * role_mult if n_prior == 0 else base_targets
                catch_rate = career_rate("receptions", "targets") if n_prior else lp["catch_rate"]
                ypt = career_rate("receiving_yards", "targets") if n_prior else lp["yards_per_target"]
                rec_td_rate = career_rate("receiving_td", "targets") if n_prior else lp["rec_td_rate"]
                exp_receptions = exp_targets * (catch_rate or 0) if exp_targets is not None else None
                exp_rec_yards = exp_targets * (ypt or 0) if exp_targets is not None else None
                exp_rec_td = exp_targets * (rec_td_rate or 0) if exp_targets is not None else None
                exp_rush_yards = mean(h["rush_yards"]) if h["rush_attempts"] and any(h["rush_attempts"]) else 0
                exp_rush_td = mean(h["rush_td"]) if h["rush_attempts"] and any(h["rush_attempts"]) else 0
                fumble_rate = mean([safe_div(x, t) for x, t in zip(h["fumbles_lost"], h["targets"]) if t]) if n_prior else lp["fumble_rate"]
                exp_fumbles = (exp_targets or 0) * (fumble_rate or 0)
                points = sum((v or 0) * sc[k] for v, k in [(exp_receptions, "reception"), (exp_rec_yards, "receiving_yards"), (exp_rec_td, "receiving_td"), (exp_rush_yards, "rushing_yards"), (exp_rush_td, "rushing_td"), (exp_fumbles, "fumble_lost")])
                row.update({"expected_targets": exp_targets, "expected_fumbles_lost": exp_fumbles, "expected_interceptions": 0.0, "v2a_points": round(points, 3)})

            row["real_actual_points"] = real_actual_points(r, sc)
            out.append(row)

            for k in h:
                h[k].append(r.get(k) or 0)
    return out


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        sc = load_scoring_rules(cur)
        rows = load_rows(cur)
        priors = compute_league_priors(rows)
        lineup_status = load_lineup_status_gw1(cur)
        print(f"Loaded {len(rows)} real player-game rows, {len(lineup_status)} real GW1 lineup_status records.")

        v2a_rows = build_v2a_rows_revised(rows, sc, priors, lineup_status)
        out_path = ROOT / "opportunity_v2a_points_revised.csv"
        fieldnames = list(dict.fromkeys(k for row in v2a_rows for k in row.keys()))
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, restval="")
            writer.writeheader()
            writer.writerows(v2a_rows)
        print(f"-> {out_path} ({len(v2a_rows)} rows)")

        from collections import Counter
        gw1_none_2026 = [r for r in v2a_rows if r["season"] == 2026 and r["history_group"] == "none"]
        print(f"\n2026 GW1 'none'-history rows: {len(gw1_none_2026)}")
        print("Role status distribution used:", Counter(r["role_status_used"] for r in gw1_none_2026))
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
