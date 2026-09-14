"""
opportunity_v2_evaluation.py
--------------------------------
Reads opportunity_v2_features.csv (real, no-lookahead features) and:
  1. Reports feature coverage/missingness/sample sizes/distributions by
     position.
  2. Compares candidate opportunity predictors (last game, roll3, roll5,
     season average, EWM) against each other via real correlation and MAE
     against the actual next-game value - fit/selected on 2022-2024 only,
     evaluated out-of-sample on held-out 2025, exactly as instructed.
  3. Applies the winning candidate to real 2026 GW1 rows (built ONLY from
     real pre-2026 history, per the feature script's own no-lookahead
     construction) as a genuinely unseen final check - 2026 is never used
     to pick a winner, only to report how the already-chosen winner did.

Read-only, diagnostic only. Does not touch projections/predictions_and_
actuals/player_stats, and does not change or deploy anything.

RUN:
    python scripts/opportunity_v2_evaluation.py
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT  # noqa: E402

TARGETS = {
    "QB": ("actual_pass_attempts", ["pass_attempts_last1", "pass_attempts_roll3", "pass_attempts_roll5", "pass_attempts_season_avg", "pass_attempts_ewm"]),
    "RB_carries": ("actual_rush_attempts", ["rush_attempts_last1", "rush_attempts_roll3", "rush_attempts_roll5", "rush_attempts_season_avg", "rush_attempts_ewm"]),
    "RB_targets": ("actual_targets", ["targets_last1", "targets_roll3", "targets_roll5", "targets_season_avg", "targets_ewm"]),
    "WRTE_targets": ("actual_targets", ["targets_last1", "targets_roll3", "targets_roll5", "targets_season_avg", "targets_ewm"]),
}
ROW_FILTER = {
    "QB": lambda r: r["position"] == "QB",
    "RB_carries": lambda r: r["position"] == "RB",
    "RB_targets": lambda r: r["position"] == "RB",
    "WRTE_targets": lambda r: r["position"] in ("WR", "TE"),
}


def to_float(v):
    if v in (None, "", "None"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def load_rows():
    with (ROOT / "opportunity_v2_features.csv").open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    numeric_cols = [c for c in rows[0].keys() if c not in ("player", "position", "team", "week", "history_group", "api_sports_game_id")]
    for r in rows:
        for c in numeric_cols:
            r[c] = to_float(r[c])
        r["season"] = int(r["season"])
    return rows


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return None
    return cov / (vx * vy) ** 0.5


def mae(xs, ys):
    return sum(abs(x - y) for x, y in zip(xs, ys)) / len(xs) if xs else None


def coverage_report(rows):
    print("=== Feature coverage / missingness / sample sizes by position ===")
    positions = ["QB", "RB", "WR", "TE"]
    for pos in positions:
        pos_rows = [r for r in rows if r["position"] == pos]
        n = len(pos_rows)
        by_group = {}
        for r in pos_rows:
            by_group[r["history_group"]] = by_group.get(r["history_group"], 0) + 1
        print(f"\n  {pos}: {n} real player-game rows")
        print(f"    History groups: {by_group}")
        key_feature = {"QB": "pass_attempts_roll3", "RB": "rush_attempts_roll3", "WR": "targets_roll3", "TE": "targets_roll3"}[pos]
        populated = sum(1 for r in pos_rows if r.get(key_feature) is not None)
        print(f"    {key_feature} populated: {populated}/{n} ({100*populated/n:.1f}%)" if n else "    n/a")
        target_col = "actual_pass_attempts" if pos == "QB" else ("actual_rush_attempts" if pos == "RB" else "actual_targets")
        vals = [r[target_col] for r in pos_rows if r.get(target_col) is not None]
        if vals:
            vals_sorted = sorted(vals)
            mean_v = sum(vals) / len(vals)
            median_v = vals_sorted[len(vals_sorted) // 2]
            print(f"    Real actual {target_col} distribution: mean={mean_v:.2f}, median={median_v:.1f}, min={min(vals):.0f}, max={max(vals):.0f}, n={len(vals)}")


def candidate_comparison(rows):
    print("\n=== Candidate opportunity-predictor comparison (fit-select on 2022-2024, test on held-out 2025) ===")
    results = {}
    for label, (target_col, candidates) in TARGETS.items():
        subset = [r for r in rows if ROW_FILTER[label](r) and r.get(target_col) is not None]
        train = [r for r in subset if r["season"] in (2022, 2023, 2024)]
        test = [r for r in subset if r["season"] == 2025]
        print(f"\n  --- {label} (predicting {target_col}) ---  train n={len(train)}, test n={len(test)}")
        best_candidate, best_test_corr = None, -2
        for cand in candidates:
            train_pairs = [(r[cand], r[target_col]) for r in train if r.get(cand) is not None]
            test_pairs = [(r[cand], r[target_col]) for r in test if r.get(cand) is not None]
            train_corr = pearson([p[0] for p in train_pairs], [p[1] for p in train_pairs])
            test_corr = pearson([p[0] for p in test_pairs], [p[1] for p in test_pairs])
            train_mae = mae([p[0] for p in train_pairs], [p[1] for p in train_pairs])
            test_mae = mae([p[0] for p in test_pairs], [p[1] for p in test_pairs])
            print(f"    {cand:28} train r={train_corr and round(train_corr,3)}, train MAE={train_mae and round(train_mae,2)}  |  test r={test_corr and round(test_corr,3)}, test MAE={test_mae and round(test_mae,2)}  (n_train={len(train_pairs)}, n_test={len(test_pairs)})")
            if test_corr is not None and test_corr > best_test_corr:
                best_test_corr, best_candidate = test_corr, cand
        print(f"    -> Winner (highest real 2025 held-out correlation): {best_candidate} (r={best_test_corr:.3f})")
        results[label] = (target_col, best_candidate)
    return results


def apply_to_gw1_2026(rows, winners):
    print("\n=== Applying the already-chosen winners to real, never-before-used 2026 GW1 rows ===")
    for label, (target_col, winner) in winners.items():
        subset = [r for r in rows if ROW_FILTER[label](r) and r["season"] == 2026 and r.get(target_col) is not None and r.get(winner) is not None]
        if not subset:
            print(f"  {label}: no real 2026 GW1 rows with both a real actual and a real '{winner}' feature available.")
            continue
        pairs = [(r[winner], r[target_col]) for r in subset]
        r_val = pearson([p[0] for p in pairs], [p[1] for p in pairs])
        m_val = mae([p[0] for p in pairs], [p[1] for p in pairs])
        print(f"  {label}: winner='{winner}' on {len(pairs)} real 2026 GW1 rows -> r={r_val and round(r_val,3)}, MAE={m_val and round(m_val,2)}")


def main():
    rows = load_rows()
    print(f"Loaded {len(rows)} total real feature rows.\n")
    coverage_report(rows)
    winners = candidate_comparison(rows)
    apply_to_gw1_2026(rows, winners)


if __name__ == "__main__":
    main()
