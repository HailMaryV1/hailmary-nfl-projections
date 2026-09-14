"""
opportunity_v2_compare.py
-----------------------------
Final V1 vs V2-A vs V2-B vs V2-C comparison on real, settled 2026 GW1
offensive players - the genuinely unseen benchmark, never used to fit or
select anything upstream (see opportunity_v2_model.py's own methodology
note on why V2-B/V2-C can only be evaluated here, not chronologically).

V2-B is exactly V1 (same real predicted_points) - listed separately only
because the brief asks for it as its own labeled row, not because it's a
different number.
V2-C = V1's real predicted_points + V2-A's real historical
interception/fumble expectation x their real scoring_rules point values
(-2 each) - the one real, fixed (not tuned) adjustment for the turnover
signal V1 has never priced.

Read-only. Does not touch projections/predictions_and_actuals/
player_stats. Reports metrics, then a real attribution table for players
where V2-A's own opportunity assumption differs materially from V1's.

RUN:
    python scripts/opportunity_v2_compare.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

INT_POINTS = -2.0
FUMBLE_POINTS = -2.0
POSITIONS = ["QB", "RB", "WR", "TE"]


def to_float(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_v2a_2026():
    with (ROOT / "opportunity_v2a_points.csv").open(encoding="utf-8") as f:
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
            "opportunity_source": r["opportunity_source"],
            "expected_pass_attempts": to_float(r.get("expected_pass_attempts")),
            "expected_carries": to_float(r.get("expected_carries")),
            "expected_targets": to_float(r.get("expected_targets")),
        }
    return out


def load_v1_gw1(cur):
    cur.execute(
        """
        select pa.player_id, p.full_name, p.position, t.abbr as team_abbr,
               pa.predicted_points, pa.actual_points,
               f.home_team_id, f.away_team_id, p.team_id,
               ho.abbr as home_abbr, aw.abbr as away_abbr
        from predictions_and_actuals pa
        join players p on p.id = pa.player_id
        left join teams t on t.id = p.team_id
        left join fixtures f on f.gameweek = pa.gameweek and (f.home_team_id = p.team_id or f.away_team_id = p.team_id)
        left join teams ho on ho.id = f.home_team_id
        left join teams aw on aw.id = f.away_team_id
        where pa.gameweek = 1 and pa.actual_points is not null
          and p.position in ('quarterback','running_back','wide_receiver','tight_end')
        """
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    pos_label = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE"}
    for r in rows:
        r["position"] = pos_label[r["position"]]
        r["opponent"] = r["away_abbr"] if r["team_id"] == r["home_team_id"] else r["home_abbr"]
    return rows


def summarize(pairs):
    if not pairs:
        return None
    errors = [p - a for p, a in pairs]
    n = len(errors)
    abs_errors = [abs(e) for e in errors]
    return {
        "n": n,
        "mae": sum(abs_errors) / n,
        "median_ae": sorted(abs_errors)[n // 2],
        "rmse": (sum(e * e for e in errors) / n) ** 0.5,
        "bias": sum(errors) / n,
        "within1": 100 * sum(1 for e in abs_errors if e <= 1) / n,
        "within2": 100 * sum(1 for e in abs_errors if e <= 2) / n,
        "within3": 100 * sum(1 for e in abs_errors if e <= 3) / n,
        "within5": 100 * sum(1 for e in abs_errors if e <= 5) / n,
        "beyond5": 100 * sum(1 for e in abs_errors if e > 5) / n,
        "over10": sum(1 for e in abs_errors if e > 10),
        "over15": sum(1 for e in abs_errors if e > 15),
    }


def print_summary(label, s):
    if not s:
        print(f"  {label}: no real rows.")
        return
    print(f"  {label:10} n={s['n']:<4} MAE={s['mae']:.2f}  MedAE={s['median_ae']:.2f}  RMSE={s['rmse']:.2f}  Bias={s['bias']:+.2f}  "
          f"±1={s['within1']:.1f}%  ±2={s['within2']:.1f}%  ±3={s['within3']:.1f}%  ±5={s['within5']:.1f}%  >5={s['beyond5']:.1f}%  "
          f">10pt={s['over10']}  >15pt={s['over15']}")


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        v2a = load_v2a_2026()
        v1_rows = load_v1_gw1(cur)
        print(f"Real V1 settled GW1 offensive rows: {len(v1_rows)}. Real V2-A 2026 rows available: {len(v2a)}.")

        merged = []
        for r in v1_rows:
            a = v2a.get(r["player_id"])
            if a is None or a["v2a_points"] is None:
                continue
            v1 = float(r["predicted_points"])
            actual = float(r["actual_points"])
            v2a_pts = a["v2a_points"]
            v2b_pts = v1
            exp_int = a["expected_interceptions"] or 0
            exp_fum = a["expected_fumbles_lost"] or 0
            v2c_pts = v1 + exp_int * INT_POINTS + exp_fum * FUMBLE_POINTS
            merged.append({**r, "v1": v1, "actual": actual, "v2a": v2a_pts, "v2b": v2b_pts, "v2c": v2c_pts,
                           "history_group": a["history_group"], "opportunity_source": a["opportunity_source"],
                           "expected_interceptions": exp_int, "expected_fumbles_lost": exp_fum,
                           "expected_pass_attempts": a["expected_pass_attempts"], "expected_carries": a["expected_carries"], "expected_targets": a["expected_targets"]})

        print(f"Real rows present in BOTH V1 and V2-A (exact same settled players used for every comparison below): {len(merged)}\n")

        print("=== Comparison, by position (same player set for every variant) ===")
        for pos in POSITIONS + ["ALL OFFENSE"]:
            subset = merged if pos == "ALL OFFENSE" else [m for m in merged if m["position"] == pos]
            print(f"\n {pos} (n={len(subset)}):")
            for label, key in [("V1", "v1"), ("V2-A Opportunity", "v2a"), ("V2-B Market", "v2b"), ("V2-C Hybrid", "v2c")]:
                pairs = [(m[key], m["actual"]) for m in subset]
                print_summary(label, summarize(pairs))

        print("\n=== Attribution: V2-A vs V1, material differences (|diff| >= 3pt), same real actual ===")
        print(f"  {'Player':22}{'Pos':5}{'V1':>7}{'V2A':>7}{'Act':>7}{'V1 AE':>7}{'V2A AE':>8}  Opportunity used")
        material = [m for m in merged if abs(m["v2a"] - m["v1"]) >= 3]
        material.sort(key=lambda m: abs(m["v1"] - m["actual"]) - abs(m["v2a"] - m["actual"]), reverse=True)
        fixed_volume_misses = 0
        for m in material:
            v1_ae, v2a_ae = abs(m["v1"] - m["actual"]), abs(m["v2a"] - m["actual"])
            opp = m["expected_pass_attempts"] or m["expected_carries"] or m["expected_targets"]
            opp_label = f"{opp:.1f}" if opp is not None else "n/a"
            improved = v2a_ae < v1_ae - 2
            if improved:
                fixed_volume_misses += 1
            flag = " <- V2-A materially closer" if improved else (" <- V1 was closer" if v1_ae < v2a_ae - 2 else "")
            print(f"  {m['full_name']:22}{m['position']:5}{m['v1']:>7.2f}{m['v2a']:>7.2f}{m['actual']:>7.2f}{v1_ae:>7.2f}{v2a_ae:>8.2f}  {opp_label} ({m['history_group']}/{m['opportunity_source']}){flag}")
        print(f"\n  {fixed_volume_misses} of {len(material)} material V2-A differences moved the prediction meaningfully CLOSER to the real actual (>=2pt AE improvement).")

        print("\n=== Attribution: V2-C vs V1 (turnover overlay only) - top 10 largest adjustments ===")
        turnover_diffs = sorted(merged, key=lambda m: abs(m["v2c"] - m["v1"]), reverse=True)[:10]
        print(f"  {'Player':22}{'Pos':5}{'V1':>7}{'V2C':>7}{'Act':>7}{'V1 AE':>7}{'V2C AE':>8}  exp_INT  exp_FUM")
        for m in turnover_diffs:
            v1_ae, v2c_ae = abs(m["v1"] - m["actual"]), abs(m["v2c"] - m["actual"])
            print(f"  {m['full_name']:22}{m['position']:5}{m['v1']:>7.2f}{m['v2c']:>7.2f}{m['actual']:>7.2f}{v1_ae:>7.2f}{v2c_ae:>8.2f}  {m['expected_interceptions']:.3f}   {m['expected_fumbles_lost']:.3f}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
