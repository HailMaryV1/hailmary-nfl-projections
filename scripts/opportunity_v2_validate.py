"""
opportunity_v2_validate.py
------------------------------
Chronological validation of V2-A (Opportunity only) against real
FanTeam-equivalent fantasy points, computed from real box-score outcomes
via the live scoring_rules - not fit/tuned here, just measured. Train
window (2022-2024) is reported for reference; 2025 is the real held-out
window this model's own accuracy is judged on. 2026 GW1 is loaded but
NOT used to pick anything - see opportunity_v2_compare.py for the actual
V1-vs-V2 GW1 comparison.

RUN:
    python scripts/opportunity_v2_validate.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT  # noqa: E402


def to_float(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_rows():
    with (ROOT / "opportunity_v2a_points.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["season"] = int(r["season"])
        r["v2a_points"] = to_float(r["v2a_points"])
        r["real_actual_points"] = to_float(r["real_actual_points"])
    return rows


def summarize(pairs):
    if not pairs:
        return None
    errors = [p - a for p, a in pairs]
    n = len(errors)
    mae = sum(abs(e) for e in errors) / n
    med = sorted(abs(e) for e in errors)[n // 2]
    rmse = (sum(e * e for e in errors) / n) ** 0.5
    bias = sum(errors) / n
    return {"n": n, "mae": mae, "median_ae": med, "rmse": rmse, "bias": bias}


def main():
    rows = load_rows()
    print(f"Loaded {len(rows)} V2-A rows with real actual points.\n")

    for label, seasons in [("Train (2022-2024)", (2022, 2023, 2024)), ("Held-out validation (2025)", (2025,))]:
        print(f"=== {label} ===")
        for pos in ("QB", "RB", "WR", "TE"):
            pairs = [(r["v2a_points"], r["real_actual_points"]) for r in rows if r["position"] == pos and r["season"] in seasons and r["v2a_points"] is not None and r["real_actual_points"] is not None]
            s = summarize(pairs)
            if s:
                print(f"  {pos}: n={s['n']}, MAE={s['mae']:.2f}, Median AE={s['median_ae']:.2f}, RMSE={s['rmse']:.2f}, Bias={s['bias']:+.2f}")
        pairs_all = [(r["v2a_points"], r["real_actual_points"]) for r in rows if r["season"] in seasons and r["v2a_points"] is not None and r["real_actual_points"] is not None]
        s = summarize(pairs_all)
        print(f"  ALL OFFENSE: n={s['n']}, MAE={s['mae']:.2f}, Median AE={s['median_ae']:.2f}, RMSE={s['rmse']:.2f}, Bias={s['bias']:+.2f}\n")

        by_group = {}
        for r in rows:
            if r["season"] in seasons and r["v2a_points"] is not None and r["real_actual_points"] is not None:
                by_group.setdefault(r["history_group"], []).append((r["v2a_points"], r["real_actual_points"]))
        print("  By history group:")
        for group, pairs in by_group.items():
            s = summarize(pairs)
            print(f"    {group}: n={s['n']}, MAE={s['mae']:.2f}, Bias={s['bias']:+.2f}")
        print()


if __name__ == "__main__":
    main()
