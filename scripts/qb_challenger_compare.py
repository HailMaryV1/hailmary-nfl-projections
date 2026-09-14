"""
qb_challenger_compare.py
----------------------------
QB-only ablation: isolates whether V2's QB improvement comes from the
turnover correction, the opportunity/history layer, or both. RB/WR/TE are
completely untouched - this only ever reads QB rows.

Uses the REVISED (role-gated) V2-A numbers, per instruction to keep that
fix for research rather than the original blind-fallback version.

Four variants, all built from real, already-computed, FIXED components -
nothing here is fit or searched against GW1's own results:
  QB-V1             : V1's own real predicted_points, unchanged.
  QB-V1+INT         : V1 + real historical expected interception/fumble
                       penalty (exp_int x -2 + exp_fumbles x -2) - a clean
                       real ADDITION, since V1 currently prices these at
                       exactly 0 (nothing to double-count).
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
                       this comparison, not after seeing its result.
  QB-Hybrid         : the Opportunity blend above + the same real
                       interception/fumble addition - i.e. Hybrid =
                       Opportunity-variant + INT-variant's own turnover
                       term, decomposable by construction so the
                       comparison below cleanly separates the two effects.

RUN:
    python scripts/qb_challenger_compare.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

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
        v2a = load_v2a_revised_qb_2026()
        v1_rows = load_v1_gw1_qb(cur)

        merged = []
        for r in v1_rows:
            a = v2a.get(r["player_id"])
            if a is None or a["v2a_points"] is None:
                continue
            v1 = float(r["predicted_points"])
            actual = float(r["actual_points"])
            exp_int, exp_fum = a["expected_interceptions"], a["expected_fumbles_lost"]
            v2a_no_turnover = a["v2a_points"] - (exp_int * INT_POINTS + exp_fum * FUMBLE_POINTS)
            turnover_term = exp_int * INT_POINTS + exp_fum * FUMBLE_POINTS

            qb_v1 = v1
            qb_v1_int = v1 + turnover_term
            qb_v1_opp = BLEND_WEIGHT * v1 + (1 - BLEND_WEIGHT) * v2a_no_turnover
            qb_hybrid = qb_v1_opp + turnover_term

            merged.append({"player": r["full_name"], "actual": actual, "qb_v1": qb_v1, "qb_v1_int": qb_v1_int, "qb_v1_opp": qb_v1_opp, "qb_hybrid": qb_hybrid,
                           "expected_interceptions": exp_int, "expected_fumbles_lost": exp_fum})

        print(f"Real GW1 QB rows in both V1 and revised V2-A: {len(merged)}\n")
        print("=== QB-only ablation: same real settled QB sample for every variant ===")
        for label, key in [("QB-V1", "qb_v1"), ("QB-V1+INT", "qb_v1_int"), ("QB-V1+Opportunity", "qb_v1_opp"), ("QB-Hybrid", "qb_hybrid")]:
            print_row(label, summarize([(m[key], m["actual"]) for m in merged]))

        print("\n=== Per-player detail ===")
        print(f"  {'Player':22}{'Actual':>8}{'V1':>8}{'+INT':>8}{'+Opp':>8}{'Hybrid':>8}")
        for m in sorted(merged, key=lambda m: abs(m["qb_v1"] - m["actual"]), reverse=True):
            print(f"  {m['player']:22}{m['actual']:>8.2f}{m['qb_v1']:>8.2f}{m['qb_v1_int']:>8.2f}{m['qb_v1_opp']:>8.2f}{m['qb_hybrid']:>8.2f}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
