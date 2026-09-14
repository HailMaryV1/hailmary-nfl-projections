"""
qb_challenger_gw2_report.py
--------------------------------
Read-only comparison of the 4 frozen GW2 QB challenger variants
(QB-V1 / QB-V1+INT / QB-V1+Opportunity / QB-Hybrid) against real settled
GW2 actuals - the genuine prospective test the GW1 ablation
(qb_challenger_compare.py) could not be, since GW1's own frozen numbers
were computed retrospectively from already-played games.

Reads ONLY from qb_challenger_freeze (frozen before GW2 kickoff, never
touched since) and predictions_and_actuals (real settled actual_points).
Does not recompute, adjust, or backfill anything - whatever was frozen is
what gets graded, exactly as the freeze's own design intends.

Same metrics as the GW1 ablation (MAE, median AE, RMSE, bias, ±3, ±5,
>10pt, >15pt misses), plus a per-QB before/after error table (V1's own
error vs each challenger's error) so an aggregate improvement can be
checked for being broad across the sample versus driven by one or two
outliers.

RUN (once GW2 has real settled actuals):
    python scripts/qb_challenger_gw2_report.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402

GAMEWEEK = 2
VARIANTS = [("QB-V1", "qb_v1_points"), ("QB-V1+INT", "qb_v1_int_points"),
            ("QB-V1+Opportunity", "qb_v1_opportunity_points"), ("QB-Hybrid", "qb_hybrid_points")]


def load_frozen(cur):
    cur.execute(
        """
        select player_id, qb_v1_points, qb_v1_int_points, qb_v1_opportunity_points, qb_hybrid_points, frozen_at
        from qb_challenger_freeze
        where gameweek = %s
        """,
        (GAMEWEEK,),
    )
    cols = [d[0] for d in cur.description]
    return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


def load_actuals(cur, player_ids):
    if not player_ids:
        return {}
    cur.execute(
        """
        select pa.player_id, p.full_name, pa.actual_points
        from predictions_and_actuals pa
        join players p on p.id = pa.player_id
        where pa.gameweek = %s and pa.player_id = any(%s) and pa.actual_points is not null
        """,
        (GAMEWEEK, list(player_ids)),
    )
    cols = [d[0] for d in cur.description]
    return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


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
        frozen = load_frozen(cur)
        if not frozen:
            print(f"No frozen qb_challenger_freeze rows exist for gameweek {GAMEWEEK} yet - run scripts/qb_challenger_freeze.py {GAMEWEEK} before kickoff first.")
            return

        actuals = load_actuals(cur, list(frozen.keys()))
        merged = []
        for player_id, f in frozen.items():
            a = actuals.get(player_id)
            if a is None:
                continue
            merged.append({"player": a["full_name"], "actual": float(a["actual_points"]), **{v[1]: float(f[v[1]]) for v in VARIANTS}})

        total_frozen = len(frozen)
        settled = len(merged)
        print(f"Frozen GW2 QB rows: {total_frozen}. Real settled actuals available so far: {settled}.")
        if settled < total_frozen:
            print(f"NOTE: {total_frozen - settled} frozen QB(s) do not have a real settled actual yet - GW2 may not be fully complete. "
                  f"Re-run this report once all of GW2 has finished; this run only grades the {settled} already-settled QB(s).\n")
        if not merged:
            print("No settled GW2 QB actuals yet - nothing to report.")
            return

        print("\n=== GW2 prospective QB ablation: real frozen (pre-kickoff) projections vs real settled actuals ===")
        for label, key in VARIANTS:
            print_row(label, summarize([(m[key], m["actual"]) for m in merged]))

        print("\n=== Per-QB before/after error (V1's own error vs each challenger's error) ===")
        print(f"  {'Player':22}{'Actual':>8}{'V1':>8}{'V1 AE':>8}{'+INT AE':>9}{'+Opp AE':>9}{'Hybrid AE':>10}")
        for m in sorted(merged, key=lambda m: abs(m["qb_v1_points"] - m["actual"]), reverse=True):
            v1_ae = abs(m["qb_v1_points"] - m["actual"])
            int_ae = abs(m["qb_v1_int_points"] - m["actual"])
            opp_ae = abs(m["qb_v1_opportunity_points"] - m["actual"])
            hybrid_ae = abs(m["qb_hybrid_points"] - m["actual"])
            print(f"  {m['player']:22}{m['actual']:>8.2f}{m['qb_v1_points']:>8.2f}{v1_ae:>8.2f}{int_ae:>9.2f}{opp_ae:>9.2f}{hybrid_ae:>10.2f}")

        print("\n=== Broad improvement vs outlier-driven check ===")
        for label, key in VARIANTS[1:]:
            deltas = [abs(m["qb_v1_points"] - m["actual"]) - abs(m[key] - m["actual"]) for m in merged]
            improved = sum(1 for d in deltas if d > 0.01)
            worsened = sum(1 for d in deltas if d < -0.01)
            unchanged = len(deltas) - improved - worsened
            print(f"  {label:20} improved on {improved}/{len(deltas)} QBs, worsened on {worsened}, unchanged on {unchanged} "
                  f"(net MAE change driven by {improved + worsened} real per-player differences, not a single outlier, if both counts are > 1)")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
