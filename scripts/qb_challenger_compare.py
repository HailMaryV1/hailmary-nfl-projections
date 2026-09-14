"""
qb_challenger_compare.py
----------------------------
QB-only ablation: isolates whether V2's QB improvement comes from the
turnover correction, the opportunity/history layer, or both. RB/WR/TE are
completely untouched - this only ever reads QB rows.

Uses the REVISED (role-gated) V2-A numbers for the Opportunity variant's
own production (pass/rush yards, TDs), per instruction to keep that fix
for research rather than the original blind-fallback version.

Four variants, all built from real, already-computed, FIXED components -
nothing here is fit or searched against GW1's own results:
  QB-V1             : V1's own real predicted_points, unchanged.
  QB-V1+INT         : V1 + a real, PARTICIPATION-GATED expected
                       interception/fumble penalty - see "Turnover
                       participation gate" below. A clean real ADDITION,
                       since V1 currently prices turnovers at exactly 0
                       (nothing to double-count).
  QB-V1+Opportunity : a 50/50 average of V1's own total and V2-A's own
                       opportunity-based total with its turnover penalty
                       backed out first. A blend, not a raw addition -
                       unlike interceptions, V1 already has a real
                       (market-priced) view of passing/rushing production,
                       so combining a SECOND independent estimate of the
                       SAME quantity calls for averaging two forecasts,
                       not summing them (which would double-count).
                       FLAGGED EXPLICITLY: 50/50 is a fixed, stated
                       choice, not tuned or searched - there is no prior
                       week with both signals to tune a weight against
                       (same real constraint noted for the original
                       Hybrid), and this weight was chosen before running
                       this comparison, not after seeing its result. This
                       variant's own passing/rushing production is NOT
                       touched by the turnover participation gate below -
                       out of scope for this fix.
  QB-Hybrid         : the Opportunity blend above + the same real,
                       participation-gated interception/fumble addition -
                       i.e. Hybrid = Opportunity-variant + INT-variant's
                       own turnover term, decomposable by construction so
                       the comparison below cleanly separates the two
                       effects.

Turnover participation gate (fix, not GW1 tuning):
  Previously, expected interceptions/fumbles were computed from each QB's
  raw historical opportunity (EWM/career pass+rush attempts) with NO
  regard for whether V1's own real, current-week signal expects that QB
  to play at all. For an established veteran who wasn't actually expected
  to see the field that week (e.g. real GW1 case: Carson Wentz, Kenny
  Pickett, Stetson Bennett - all real FanTeam-flagged "unexpected" that
  week), this produced a real turnover PENALTY subtracted from a real
  near-zero V1 baseline, driving the projection negative - a fantasy
  score can never actually be that, so this was a genuine defect, not a
  harsh-but-fair result.
  Fix: expected pass/rush attempts used for the turnover calculation ONLY
  are scaled by a real, pre-game participation signal - the SAME fixed
  ROLE_MULTIPLIER table already established (and never GW1-tuned) in
  opportunity_v2_model_revised_fallback.py for the no-history fallback,
  now applied here to EVERY QB (not just no-history ones), because "will
  this QB actually play" is a real question for established players too:
    starter, expected            -> 1.00x (unchanged)
    questionable, possible       -> 0.35x
    doubtful/inactive/injured/
    refuted/unexpected/no signal -> 0.08x (near-zero, not exactly zero -
                                    a real, if unlikely, chance of a
                                    surprise appearance is still possible)
  expected_interceptions = (raw expected pass attempts x participation
  multiplier) x real historical INT rate - so a near-zero participation
  multiplier drives expected interceptions, and therefore the turnover
  penalty, to near-zero too, exactly as it should. This only changes how
  MUCH pass/rush volume feeds the turnover formula - it does not touch
  the historical INT/fumble RATES themselves, and it does not touch the
  Opportunity variant's own separate production estimate (scope is the
  turnover adjustment only, per the brief).
  This reuses the EXISTING fixed multiplier table verbatim - no new
  number was chosen after seeing this comparison's results.

  A tiny residual negative can still occur (0.08x is "near-zero", not
  exactly zero, per the multiplier table's own design - a real, if
  unlikely, chance of a surprise appearance) when V1's own baseline is
  exactly 0. Since a fantasy score can never actually be negative, every
  final challenger projection (not the intermediate audit figures, which
  keep their real signed math) is floored at 0 as a last, non-tuned step.

RUN:
    python scripts/qb_challenger_compare.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402
from opportunity_v2_model_revised_fallback import load_lineup_status_gw1, role_multiplier  # noqa: E402

INT_POINTS, FUMBLE_POINTS = -2.0, -2.0
BLEND_WEIGHT = 0.5  # fixed, stated, not tuned - see module docstring


def to_float(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_v2a_revised_qb_2026():
    with (ROOT / "opportunity_v2a_points_revised.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        if int(r["season"]) != 2026 or r["position"] != "QB":
            continue
        out[int(r["player_id"])] = {
            "v2a_points": to_float(r["v2a_points"]),
            "expected_interceptions": to_float(r.get("expected_interceptions")) or 0.0,
            "expected_fumbles_lost": to_float(r.get("expected_fumbles_lost")) or 0.0,
        }
    return out


def load_v2a_original_qb_2026():
    """Raw (ungated) historical opportunity - used only as the volume input
    to the participation-gated turnover calculation, so a none-history
    fallback multiplier isn't accidentally applied twice."""
    with (ROOT / "opportunity_v2a_points.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        if int(r["season"]) != 2026 or r["position"] != "QB":
            continue
        out[int(r["player_id"])] = {
            "expected_pass_attempts": to_float(r["expected_pass_attempts"]) or 0.0,
            "expected_rush_attempts": to_float(r["expected_rush_attempts"]) or 0.0,
            "expected_int_rate": to_float(r.get("expected_int_rate")) or 0.0,
            "expected_fumbles_lost": to_float(r.get("expected_fumbles_lost")) or 0.0,
        }
    return out


def load_v1_gw1_qb(cur):
    cur.execute(
        """
        select pa.player_id, p.full_name, pa.predicted_points, pa.actual_points
        from predictions_and_actuals pa
        join players p on p.id = pa.player_id
        where pa.gameweek = 1 and pa.actual_points is not null and p.position = 'quarterback'
        """
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def summarize(pairs):
    if not pairs:
        return None
    errors = [p - a for p, a in pairs]
    n = len(errors)
    abs_errors = [abs(e) for e in errors]
    return {
        "n": n, "mae": sum(abs_errors) / n, "median_ae": sorted(abs_errors)[n // 2],
        "rmse": (sum(e * e for e in errors) / n) ** 0.5, "bias": sum(errors) / n,
        "within3": 100 * sum(1 for e in abs_errors if e <= 3) / n, "within5": 100 * sum(1 for e in abs_errors if e <= 5) / n,
        "over10": sum(1 for e in abs_errors if e > 10), "over15": sum(1 for e in abs_errors if e > 15),
    }


def print_row(label, s):
    print(f"  {label:20} n={s['n']:<4} MAE={s['mae']:.2f}  MedAE={s['median_ae']:.2f}  RMSE={s['rmse']:.2f}  Bias={s['bias']:+.2f}  "
          f"±3={s['within3']:.1f}%  ±5={s['within5']:.1f}%  >10pt={s['over10']}  >15pt={s['over15']}")


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        v2a_revised = load_v2a_revised_qb_2026()
        v2a_raw = load_v2a_original_qb_2026()
        v1_rows = load_v1_gw1_qb(cur)
        lineup_status = load_lineup_status_gw1(cur)

        merged = []
        negative_before_fix = 0
        for r in v1_rows:
            rev = v2a_revised.get(r["player_id"])
            raw = v2a_raw.get(r["player_id"])
            if rev is None or raw is None or rev["v2a_points"] is None:
                continue
            v1 = float(r["predicted_points"])
            actual = float(r["actual_points"])

            participation_mult, participation_status = role_multiplier(r["player_id"], lineup_status)
            gated_pass_att = raw["expected_pass_attempts"] * participation_mult
            gated_rush_att = raw["expected_rush_attempts"] * participation_mult
            int_rate = raw["expected_int_rate"]
            raw_touches = raw["expected_pass_attempts"] + raw["expected_rush_attempts"]
            fumble_rate = (raw["expected_fumbles_lost"] / raw_touches) if raw_touches else 0.0

            exp_int = gated_pass_att * int_rate
            exp_fum = (gated_pass_att + gated_rush_att) * fumble_rate
            int_adjustment = exp_int * INT_POINTS
            fumble_adjustment = exp_fum * FUMBLE_POINTS
            turnover_term = int_adjustment + fumble_adjustment

            unfixed_exp_int, unfixed_exp_fum = rev["expected_interceptions"], rev["expected_fumbles_lost"]
            unfixed_turnover_term = unfixed_exp_int * INT_POINTS + unfixed_exp_fum * FUMBLE_POINTS
            if v1 + unfixed_turnover_term < 0:
                negative_before_fix += 1

            v2a_no_turnover = rev["v2a_points"] - unfixed_turnover_term

            qb_v1 = max(0.0, v1)
            qb_v1_int = max(0.0, v1 + turnover_term)
            qb_v1_opp = max(0.0, BLEND_WEIGHT * v1 + (1 - BLEND_WEIGHT) * v2a_no_turnover)
            opportunity_adjustment = qb_v1_opp - v1
            qb_hybrid = max(0.0, qb_v1_opp + turnover_term)

            merged.append({
                "player": r["full_name"], "actual": actual, "v1": v1,
                "qb_v1": qb_v1, "qb_v1_int": qb_v1_int, "qb_v1_opp": qb_v1_opp, "qb_hybrid": qb_hybrid,
                "participation_status": participation_status, "participation_multiplier": participation_mult,
                "int_rate": int_rate, "expected_interceptions": exp_int, "int_adjustment": int_adjustment,
                "opportunity_adjustment": opportunity_adjustment,
            })

        print(f"Real GW1 QB rows in both V1 and revised V2-A: {len(merged)}")
        print(f"Rows that WOULD have gone negative under the pre-fix (ungated) turnover term: {negative_before_fix}\n")
        print("=== QB-only ablation: same real settled QB sample for every variant ===")
        for label, key in [("QB-V1", "qb_v1"), ("QB-V1+INT", "qb_v1_int"), ("QB-V1+Opportunity", "qb_v1_opp"), ("QB-Hybrid", "qb_hybrid")]:
            print_row(label, summarize([(m[key], m["actual"]) for m in merged]))

        floored = [m for m in merged if m["v1"] + (m["int_adjustment"]) < 0]
        print(f"\nRows where the near-zero-participation turnover penalty still exceeded V1's own baseline (floored at 0): {len(floored)}")
        for m in floored:
            print(f"  {m['player']}: status={m['participation_status']}, mult={m['participation_multiplier']}, "
                  f"final +INT={m['qb_v1_int']:.2f}, final Hybrid={m['qb_hybrid']:.2f} "
                  f"(V1 itself said {m['v1']:.2f} - a separate V1 lineup-uncertainty miss, not masked here)")

        print("\n=== Per-player detail ===")
        print(f"  {'Player':22}{'Actual':>8}{'V1':>8}{'+INT':>8}{'+Opp':>8}{'Hybrid':>8}  Participation")
        for m in sorted(merged, key=lambda m: abs(m["qb_v1"] - m["actual"]), reverse=True):
            print(f"  {m['player']:22}{m['actual']:>8.2f}{m['qb_v1']:>8.2f}{m['qb_v1_int']:>8.2f}{m['qb_v1_opp']:>8.2f}{m['qb_hybrid']:>8.2f}  "
                  f"{m['participation_status']} ({m['participation_multiplier']:.2f}x)")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
