"""
opportunity_v2_compare_revised.py
-------------------------------------
Isolated test: same 253 real settled 2026 GW1 offensive players, same
metrics as opportunity_v2_compare.py, but adds "revised V2-A" (real
lineup-status-gated fallback) and "revised V2-C" alongside the originals,
so the fallback's real effect can be seen directly. Nothing else about
the model changed - see opportunity_v2_model_revised_fallback.py's own
docstring for exactly what did and didn't change.

RUN:
    python scripts/opportunity_v2_compare_revised.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

INT_POINTS, FUMBLE_POINTS = -2.0, -2.0
POSITIONS = ["QB", "RB", "WR", "TE"]


def to_float(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_v2a_2026(filename):
    with (ROOT / filename).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        if int(r["season"]) != 2026:
            continue
        out[int(r["player_id"])] = {
            "v2a_points": to_float(r["v2a_points"]),
            "expected_interceptions": to_float(r.get("expected_interceptions")),
            "expected_fumbles_lost": to_float(r.get("expected_fumbles_lost")),
            "history_group": r["history_group"],
            "role_status_used": r.get("role_status_used", "n/a"),
            "role_multiplier": r.get("role_multiplier", "1.0"),
        }
    return out


def load_v1_gw1(cur):
    cur.execute(
        """
        select pa.player_id, p.full_name, p.position, pa.predicted_points, pa.actual_points
        from predictions_and_actuals pa
        join players p on p.id = pa.player_id
        where pa.gameweek = 1 and pa.actual_points is not null
          and p.position in ('quarterback','running_back','wide_receiver','tight_end')
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    pos_label = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE"}
    for r in rows:
        r["position"] = pos_label[r["position"]]
    return rows


def summarize(pairs):
    if not pairs:
        return None
    errors = [p - a for p, a in pairs]
    n = len(errors)
    abs_errors = [abs(e) for e in errors]
    return {
        "n": n, "mae": sum(abs_errors) / n, "median_ae": sorted(abs_errors)[n // 2],
        "rmse": (sum(e * e for e in errors) / n) ** 0.5, "bias": sum(errors) / n,
        "within1": 100 * sum(1 for e in abs_errors if e <= 1) / n, "within2": 100 * sum(1 for e in abs_errors if e <= 2) / n,
        "within3": 100 * sum(1 for e in abs_errors if e <= 3) / n, "within5": 100 * sum(1 for e in abs_errors if e <= 5) / n,
        "over10": sum(1 for e in abs_errors if e > 10), "over15": sum(1 for e in abs_errors if e > 15),
    }


def print_summary(label, s):
    if not s:
        print(f"  {label}: no real rows.")
        return
    print(f"  {label:20} n={s['n']:<4} MAE={s['mae']:.2f}  MedAE={s['median_ae']:.2f}  RMSE={s['rmse']:.2f}  Bias={s['bias']:+.2f}  "
          f"±1={s['within1']:.1f}%  ±2={s['within2']:.1f}%  ±3={s['within3']:.1f}%  ±5={s['within5']:.1f}%  >10pt={s['over10']}  >15pt={s['over15']}")


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        v2a_orig = load_v2a_2026("opportunity_v2a_points.csv")
        v2a_rev = load_v2a_2026("opportunity_v2a_points_revised.csv")
        v1_rows = load_v1_gw1(cur)

        merged = []
        for r in v1_rows:
            o, rv = v2a_orig.get(r["player_id"]), v2a_rev.get(r["player_id"])
            if o is None or rv is None or o["v2a_points"] is None or rv["v2a_points"] is None:
                continue
            v1 = float(r["predicted_points"])
            actual = float(r["actual_points"])
            v2a_o, v2a_r = o["v2a_points"], rv["v2a_points"]
            v2c_o = v1 + (o["expected_interceptions"] or 0) * INT_POINTS + (o["expected_fumbles_lost"] or 0) * FUMBLE_POINTS
            v2c_r = v1 + (rv["expected_interceptions"] or 0) * INT_POINTS + (rv["expected_fumbles_lost"] or 0) * FUMBLE_POINTS
            merged.append({**r, "v1": v1, "actual": actual, "v2a_orig": v2a_o, "v2a_rev": v2a_r, "v2c_orig": v2c_o, "v2c_rev": v2c_r,
                           "history_group": o["history_group"], "role_status_used": rv["role_status_used"], "role_multiplier": rv["role_multiplier"]})

        print(f"Real rows in both original and revised V2-A (same 253-player set): {len(merged)}\n")

        print("=== V1 vs original V2-A vs revised V2-A vs original V2-C vs revised V2-C, by position ===")
        for pos in POSITIONS + ["ALL OFFENSE"]:
            subset = merged if pos == "ALL OFFENSE" else [m for m in merged if m["position"] == pos]
            print(f"\n {pos} (n={len(subset)}):")
            for label, key in [("V1", "v1"), ("V2-A original", "v2a_orig"), ("V2-A revised", "v2a_rev"), ("V2-C original", "v2c_orig"), ("V2-C revised", "v2c_rev")]:
                print_summary(label, summarize([(m[key], m["actual"]) for m in subset]))

        print("\n=== Isolated by history group (revised V2-A) ===")
        for group in ("established", "limited", "none"):
            subset = [m for m in merged if m["history_group"] == group]
            print(f"\n {group} (n={len(subset)}):")
            print_summary("V1", summarize([(m["v1"], m["actual"]) for m in subset]))
            print_summary("V2-A original", summarize([(m["v2a_orig"], m["actual"]) for m in subset]))
            print_summary("V2-A revised", summarize([(m["v2a_rev"], m["actual"]) for m in subset]))

        print("\n=== Players whose projection changed by >=3pt solely from the fallback fix ===")
        print(f"  {'Player':22}{'Pos':5}{'Role used':14}{'Mult':6}{'Old':>8}{'New':>8}{'Actual':>8}{'OldAE':>8}{'NewAE':>8}")
        changed = [m for m in merged if m["history_group"] == "none" and abs(m["v2a_rev"] - m["v2a_orig"]) >= 3]
        changed.sort(key=lambda m: m["v2a_orig"] - m["v2a_rev"], reverse=True)
        for m in changed:
            old_ae, new_ae = abs(m["v2a_orig"] - m["actual"]), abs(m["v2a_rev"] - m["actual"])
            print(f"  {m['full_name']:22}{m['position']:5}{m['role_status_used']:14}{float(m['role_multiplier']):<6.2f}{m['v2a_orig']:>8.2f}{m['v2a_rev']:>8.2f}{m['actual']:>8.2f}{old_ae:>8.2f}{new_ae:>8.2f}")
        improved = sum(1 for m in changed if abs(m["v2a_rev"] - m["actual"]) < abs(m["v2a_orig"] - m["actual"]))
        print(f"\n  {improved} of {len(changed)} fallback-driven changes moved closer to the real actual.")

        print("\n=== Named examples explicitly requested ===")
        for name in ["Corey Kiner", "Seth McGowan", "Emanuel Wilson", "Connor Heyward"]:
            m = next((m for m in merged if m["full_name"] == name), None)
            if m:
                print(f"  {name}: role_used={m['role_status_used']}, mult={m['role_multiplier']}, orig={m['v2a_orig']:.2f}, revised={m['v2a_rev']:.2f}, actual={m['actual']:.2f}, "
                      f"orig_AE={abs(m['v2a_orig']-m['actual']):.2f}, revised_AE={abs(m['v2a_rev']-m['actual']):.2f}")
            else:
                print(f"  {name}: not found in this real settled comparison set.")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
