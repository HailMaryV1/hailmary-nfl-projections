"""
qb_challenger_freeze.py
----------------------------
Prospective (not retrospective) test of the 4 QB challenger variants from
qb_challenger_compare.py - freezes QB-V1 / QB-V1+INT / QB-V1+Opportunity /
QB-Hybrid for a real upcoming gameweek BEFORE it kicks off, into
qb_challenger_freeze (migration 0018 + 0019 for the audit columns). Once a
(player, gameweek) row exists it is never updated (`on conflict do
nothing`) - same discipline as freeze_predictions.py - so re-running this
script as fresher real lineup data arrives before kickoff only adds
players who don't have a row yet, it never rewrites an already-frozen
number. Run it again right before the real kickoff for the freshest
possible freeze; whatever is frozen first is what "prospective" then
holds you to.

Uses the SAME formulas as opportunity_v2_model.py's QB block and the SAME
real, fixed, role-gated fallback as opportunity_v2_model_revised_fallback.py
(the improved fallback the user asked to keep for research) - nothing new
is invented here, this only projects those existing formulas one real game
further than they've been run before (GW1's played games -> GW2's
not-yet-played game), using each QB's real career history through the most
recent real completed game.

QB-V1+Opportunity uses the same fixed 50/50 blend weight as
qb_challenger_compare.py (BLEND_WEIGHT=0.5, stated there as a fixed,
non-tuned choice) - reused verbatim, not re-derived.

Turnover participation gate (same fix as qb_challenger_compare.py - see
that module's docstring for the full rationale): expected pass/rush
attempts used ONLY for the turnover (INT/fumble) calculation are scaled by
a real, pre-game participation multiplier - the SAME fixed ROLE_MULTIPLIER
table, applied here to EVERY QB regardless of history group (not just the
no-history production fallback, which stays scoped to n_prior==0 as
before). Every final challenger point value is floored at 0 - a fantasy
score can never be negative, and 0.08x is "near-zero", not exactly zero,
so a tiny residual can otherwise appear when V1's own baseline is exactly
0.

Guard: refuses to freeze a gameweek's QBs unless V1 itself has a real,
already-computed (data_confidence > 0) market-driven projection for that
gameweek - see load_v1_qb_projections(). Placeholder/uncomputed rows are
never frozen as if they were real zeros.

RUN (any time before the target gameweek's real kickoff):
    python scripts/qb_challenger_freeze.py <gameweek>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402
from opportunity_v2_model import (  # noqa: E402
    load_scoring_rules, load_rows, compute_league_priors, mean, ewm, safe_div,
)
from opportunity_v2_model_revised_fallback import ROLE_MULTIPLIER, NO_SIGNAL_MULTIPLIER  # noqa: E402

INT_POINTS, FUMBLE_POINTS = -2.0, -2.0
BLEND_WEIGHT = 0.5  # fixed, stated, not tuned - reused verbatim from qb_challenger_compare.py


def load_lineup_status(cur, gameweek):
    cur.execute(
        """
        select distinct on (pls.player_id)
            pls.player_id, pls.status
        from player_lineup_status pls
        join fixtures f on f.id = pls.fixture_id
        where f.gameweek = %s
        order by pls.player_id, (pls.source = 'rotowire') desc, pls.captured_at desc
        """,
        (gameweek,),
    )
    return dict(cur.fetchall())


def role_multiplier(player_id, lineup_status):
    status = lineup_status.get(player_id)
    if status is None:
        return NO_SIGNAL_MULTIPLIER, "no_real_lineup_signal"
    return ROLE_MULTIPLIER.get(status, NO_SIGNAL_MULTIPLIER), status


def load_v1_qb_projections(cur, gameweek):
    """Only real, actually-computed V1 numbers - data_confidence = 0 is
    compute_projections.py's own signal for an uncomputed/placeholder row
    (no real market data yet for that gameweek), not a genuine projection
    of zero, so those rows are excluded rather than frozen as real zeros."""
    cur.execute("select max(id) from algorithm_versions")
    latest = cur.fetchone()[0]
    cur.execute(
        """
        select pr.player_id, pr.total_points, pr.data_confidence
        from projections pr
        join players p on p.id = pr.player_id
        where pr.gameweek = %s and pr.horizon = 1 and pr.algorithm_version_id = %s
          and p.position = 'quarterback' and pr.data_confidence > 0
        """,
        (gameweek, latest),
    )
    return {pid: (float(pts), float(conf)) for pid, pts, conf in cur.fetchall()}


def project_next_opportunity(games, priors, lineup_status):
    """Runs the exact same accumulation loop opportunity_v2_model_revised_
    fallback.py's build_v2a_rows_revised uses per real played game, but
    stops after the LAST real game and evaluates the formula one more time
    for the next (not-yet-played) game - i.e. genuinely pre-game, not a
    backtest. Returns BOTH the production-side expected values (gated only
    for a true no-history player, exactly as opportunity_v2_model_revised_
    fallback.py does it) and the raw (ungated) base rates, so the caller
    can apply the separate, universal turnover participation gate without
    multiplying a no-history player's fallback twice."""
    h = {k: [] for k in ["pass_attempts", "pass_completions", "pass_yards", "pass_td", "interceptions_thrown",
                          "rush_attempts", "rush_yards", "rush_td", "fumbles_lost"]}
    for r in games:
        for k in h:
            h[k].append(r.get(k) or 0)

    n_prior = len(h["pass_attempts"])
    lp = priors["quarterback"]
    role_mult, role_status = (1.0, "n/a")
    if n_prior == 0:
        player_id = games[0]["player_id"] if games else None
        role_mult, role_status = role_multiplier(player_id, lineup_status)

    def career_rate(numer_key, denom_key):
        pairs = [(n, d) for n, d in zip(h[numer_key], h[denom_key]) if d]
        return sum(p[0] for p in pairs) / sum(p[1] for p in pairs) if pairs else None

    base_att = ewm(h["pass_attempts"]) if h["pass_attempts"] else lp["pass_attempts"]
    exp_att = base_att * role_mult if n_prior == 0 else base_att
    ypa = career_rate("pass_yards", "pass_attempts") if n_prior else lp["yards_per_attempt"]
    td_rate = career_rate("pass_td", "pass_attempts") if n_prior else lp["pass_td_rate"]
    int_rate = career_rate("interceptions_thrown", "pass_attempts") if n_prior else lp["int_rate"]
    base_rush_att = mean(h["rush_attempts"]) if h["rush_attempts"] else lp["rush_attempts"]
    exp_rush_att = base_rush_att * role_mult if n_prior == 0 else base_rush_att
    exp_ypc = career_rate("rush_yards", "rush_attempts") if n_prior else lp["yards_per_carry"]
    exp_rush_td_rate = career_rate("rush_td", "rush_attempts") if n_prior else lp["rush_td_rate"]
    exp_pass_yards = exp_att * (ypa or 0) if exp_att is not None else None
    exp_pass_td = exp_att * (td_rate or 0) if exp_att is not None else None
    exp_rush_yards = exp_rush_att * (exp_ypc or 0) if exp_rush_att is not None else None
    exp_rush_td = exp_rush_att * (exp_rush_td_rate or 0) if exp_rush_att is not None else None
    fumble_rate = (
        mean([safe_div(x, (a or 0) + (rb or 0)) for x, a, rb in zip(h["fumbles_lost"], h["pass_attempts"], h["rush_attempts"]) if ((a or 0) + (rb or 0)) > 0])
        if n_prior else lp["fumble_rate"]
    )

    return {
        "n_prior": n_prior, "role_status": role_status, "role_multiplier": role_mult,
        "base_att": base_att, "base_rush_att": base_rush_att, "int_rate": int_rate or 0.0, "fumble_rate": fumble_rate or 0.0,
        "exp_att": exp_att, "exp_rush_att": exp_rush_att,
        "exp_pass_yards": exp_pass_yards, "exp_pass_td": exp_pass_td, "exp_rush_yards": exp_rush_yards, "exp_rush_td": exp_rush_td,
    }


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/qb_challenger_freeze.py <gameweek>")
        sys.exit(1)
    gameweek = int(sys.argv[1])

    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        sc = load_scoring_rules(cur)
        rows = load_rows(cur)
        priors = compute_league_priors(rows)
        lineup_status = load_lineup_status(cur, gameweek)
        v1_data = load_v1_qb_projections(cur, gameweek)
        print(f"Real V1 GW{gameweek} QB projections available (data_confidence > 0): {len(v1_data)}. "
              f"Real GW{gameweek} lineup_status rows: {len(lineup_status)}.")
        if not v1_data:
            print(f"No real (data_confidence > 0) V1 projections exist yet for gameweek {gameweek} - "
                  f"compute_projections.py hasn't priced this gameweek with real market data yet. Nothing frozen. "
                  f"Re-run this script closer to kickoff, once the automated 6-hourly refresh has real GW{gameweek} numbers.")
            return

        by_player = {}
        for r in rows:
            if r["position"] == "quarterback":
                by_player.setdefault(r["player_id"], []).append(r)

        frozen = 0
        for player_id, (v1, data_confidence) in v1_data.items():
            games = by_player.get(player_id, [])
            opp = project_next_opportunity(games, priors, lineup_status)

            # Production side (Opportunity variant) - unchanged, gated only for a true no-history player.
            exp_pass_yards, exp_pass_td = opp["exp_pass_yards"] or 0.0, opp["exp_pass_td"] or 0.0
            exp_rush_yards, exp_rush_td = opp["exp_rush_yards"] or 0.0, opp["exp_rush_td"] or 0.0

            # Turnover side - universal participation gate, applied to EVERY QB (fixes the negative-projection bug).
            turnover_mult, turnover_status = role_multiplier(player_id, lineup_status)
            gated_pass_att = (opp["base_att"] or 0.0) * turnover_mult
            gated_rush_att = (opp["base_rush_att"] or 0.0) * turnover_mult
            exp_int = gated_pass_att * opp["int_rate"]
            exp_fum = (gated_pass_att + gated_rush_att) * opp["fumble_rate"]
            int_adjustment = exp_int * INT_POINTS
            fumble_adjustment = exp_fum * FUMBLE_POINTS
            turnover_term = int_adjustment + fumble_adjustment

            v2a_no_turnover = sum((v or 0) * sc[k] for v, k in [
                (exp_pass_yards, "passing_yards"), (exp_pass_td, "passing_td"),
                (exp_rush_yards, "rushing_yards"), (exp_rush_td, "rushing_td"),
            ])

            qb_v1 = max(0.0, v1)
            qb_v1_int = max(0.0, v1 + turnover_term)
            qb_v1_opp_raw = BLEND_WEIGHT * v1 + (1 - BLEND_WEIGHT) * v2a_no_turnover
            qb_v1_opp = max(0.0, qb_v1_opp_raw)
            opportunity_adjustment = qb_v1_opp_raw - v1
            qb_hybrid = max(0.0, qb_v1_opp_raw + turnover_term)

            cur.execute(
                """
                insert into qb_challenger_freeze
                    (player_id, gameweek, qb_v1_points, qb_v1_int_points, qb_v1_opportunity_points, qb_hybrid_points,
                     expected_interceptions, expected_fumbles_lost, expected_pass_attempts, expected_rush_attempts,
                     n_prior_games, role_status_used, role_multiplier,
                     v1_data_confidence, int_rate, int_adjustment, fumble_adjustment, opportunity_adjustment,
                     turnover_participation_status, turnover_participation_multiplier)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (player_id, gameweek) do nothing
                """,
                (player_id, gameweek, round(qb_v1, 3), round(qb_v1_int, 3), round(qb_v1_opp, 3), round(qb_hybrid, 3),
                 round(exp_int, 4), round(exp_fum, 4), opp["exp_att"], opp["exp_rush_att"],
                 opp["n_prior"], opp["role_status"], opp["role_multiplier"],
                 round(data_confidence, 4), round(opp["int_rate"], 6), round(int_adjustment, 4), round(fumble_adjustment, 4),
                 round(opportunity_adjustment, 3), turnover_status, turnover_mult),
            )
            frozen += cur.rowcount

        conn.commit()
        print(f"Froze {frozen} new QB row(s) for gameweek {gameweek}. Already-frozen players were left untouched.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
