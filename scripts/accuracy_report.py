"""
accuracy_report.py
---------------------
Ad-hoc diagnostic report generator for predictions_and_actuals - a
scriptable, exact version of the same real math /admin/accuracy uses
(frontend/lib/accuracyMetrics.ts), for when someone wants a precise
one-off breakdown (e.g. "all players" vs "offense only, no D/ST") rather
than the live page's fixed view. Read-only - never writes to
predictions_and_actuals or projections. Frozen predictions are never
touched by this script.

RUN:
    python scripts/accuracy_report.py [gameweek]
    (defaults to the highest real gameweek with any frozen prediction)
"""
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402

POSITION_ORDER = ["quarterback", "running_back", "wide_receiver", "tight_end", "defense_special"]
POSITION_LABEL = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE", "defense_special": "D/ST"}
OFFENSE_POSITIONS = {"quarterback", "running_back", "wide_receiver", "tight_end"}


def mae(errors):
    return sum(abs(e) for e in errors) / len(errors) if errors else None


def median_ae(errors):
    return statistics.median(abs(e) for e in errors) if errors else None


def rmse(errors):
    return (sum(e * e for e in errors) / len(errors)) ** 0.5 if errors else None


def bias(pred_minus_actual_errors):
    # predicted - actual: positive = over-projection, negative = under-projection.
    return sum(pred_minus_actual_errors) / len(pred_minus_actual_errors) if pred_minus_actual_errors else None


def pct_within(errors, threshold):
    return 100.0 * sum(1 for e in errors if abs(e) <= threshold) / len(errors) if errors else None


def pct_beyond(errors, threshold):
    return 100.0 * sum(1 for e in errors if abs(e) > threshold) / len(errors) if errors else None


def fmt(v, dp=2):
    return f"{v:.{dp}f}" if v is not None else "—"


def summarize(rows):
    """rows: list of (predicted, actual) with actual already not-None."""
    errors = [p - a for p, a in rows]  # predicted - actual, signed
    return {
        "n": len(errors),
        "mae": mae(errors),
        "median_ae": median_ae(errors),
        "rmse": rmse(errors),
        "bias": bias(errors),
        "within1": pct_within(errors, 1),
        "within2": pct_within(errors, 2),
        "within3": pct_within(errors, 3),
        "within5": pct_within(errors, 5),
        "beyond5": pct_beyond(errors, 5),
    }


def print_report(title, frozen_n, captured_rows):
    s = summarize(captured_rows)
    print(f"\n=== {title} ===")
    print(f"  Frozen predictions:       {frozen_n}")
    print(f"  Results captured:         {s['n']}")
    print(f"  MAE:                      {fmt(s['mae'])}")
    print(f"  Median AE:                {fmt(s['median_ae'])}")
    print(f"  RMSE:                     {fmt(s['rmse'])}")
    print(f"  Bias (pred - actual):     {fmt(s['bias'], 3)}  ({'over-projecting' if (s['bias'] or 0) > 0.1 else 'under-projecting' if (s['bias'] or 0) < -0.1 else 'well centred'})")
    print(f"  Within ±1pt:              {fmt(s['within1'], 1)}%")
    print(f"  Within ±2pt:              {fmt(s['within2'], 1)}%")
    print(f"  Within ±3pt:              {fmt(s['within3'], 1)}%")
    print(f"  Within ±5pt:              {fmt(s['within5'], 1)}%")
    print(f"  More than 5pt away:       {fmt(s['beyond5'], 1)}%")
    return s


def print_position_breakdown(all_rows_by_position):
    print("\n=== Position breakdown ===")
    print(f"  {'POS':6}{'n':>5}{'MAE':>8}{'MedAE':>8}{'RMSE':>8}{'Bias':>8}{'±3pt%':>8}{'±5pt%':>8}")
    for pos in POSITION_ORDER:
        rows = all_rows_by_position.get(pos, [])
        s = summarize(rows)
        print(f"  {POSITION_LABEL[pos]:6}{s['n']:>5}{fmt(s['mae']):>8}{fmt(s['median_ae']):>8}{fmt(s['rmse']):>8}{fmt(s['bias'], 3):>8}{fmt(s['within3'], 1):>8}{fmt(s['within5'], 1):>8}")


def print_error_distribution(errors_abs, title):
    bands = [(0, 1), (1, 2), (2, 3), (3, 5), (5, 10), (10, 15), (15, float("inf"))]
    n = len(errors_abs)
    print(f"\n=== Error distribution - {title} ===")
    for lo, hi in bands:
        if lo == 0:
            count = sum(1 for e in errors_abs if lo <= e <= hi)
            label = f"{lo}-{hi}"
        elif hi == float("inf"):
            count = sum(1 for e in errors_abs if e > lo)
            label = f">{lo}"
        else:
            count = sum(1 for e in errors_abs if lo < e <= hi)
            label = f">{lo}-{hi}"
        pct = 100.0 * count / n if n else 0
        print(f"  {label:8} {count:>4}  ({pct:5.1f}%)")


def main():
    gameweek = int(sys.argv[1]) if len(sys.argv) > 1 else None
    conn = db_connect()
    cur = conn.cursor()
    try:
        if gameweek is None:
            cur.execute("select max(gameweek) from predictions_and_actuals")
            gameweek = cur.fetchone()[0]
        print(f"Gameweek {gameweek} - diagnostic accuracy report (read-only, frozen predictions untouched)")

        cur.execute(
            """
            select pa.predicted_points, pa.actual_points, p.position, p.full_name, p.price,
                   t.abbr as team_abbr,
                   opp.abbr as opp_abbr
            from predictions_and_actuals pa
            join players p on p.id = pa.player_id
            left join teams t on t.id = p.team_id
            left join fixtures f on f.gameweek = pa.gameweek and (f.home_team_id = p.team_id or f.away_team_id = p.team_id)
            left join teams opp on opp.id = (case when f.home_team_id = p.team_id then f.away_team_id else f.home_team_id end)
            where pa.gameweek = %s
            """,
            (gameweek,),
        )
        all_rows = cur.fetchall()

        frozen_n = len(all_rows)
        captured = [r for r in all_rows if r[1] is not None]
        captured_pairs = [(float(r[0]), float(r[1])) for r in captured]

        offense_captured = [r for r in captured if r[2] in OFFENSE_POSITIONS]
        offense_pairs = [(float(r[0]), float(r[1])) for r in offense_captured]

        # Report A - all players
        print_report("REPORT A - ALL PLAYERS (QB/RB/WR/TE/D-ST)", frozen_n, captured_pairs)

        by_position_all = {}
        for pos in POSITION_ORDER:
            by_position_all[pos] = [(float(r[0]), float(r[1])) for r in captured if r[2] == pos]
        print_position_breakdown(by_position_all)

        # Report B - offense only
        offense_frozen_n = sum(1 for r in all_rows if r[2] in OFFENSE_POSITIONS)
        print_report("REPORT B - OFFENSIVE PLAYERS ONLY (QB/RB/WR/TE, D/ST EXCLUDED)", offense_frozen_n, offense_pairs)

        by_position_offense = {pos: by_position_all[pos] for pos in OFFENSE_POSITIONS}
        print("\n(Report B position breakdown is the same QB/RB/WR/TE rows shown above, D/ST omitted.)")

        # Error distribution - offense
        offense_errors_abs = [abs(p - a) for p, a in offense_pairs]
        print_error_distribution(offense_errors_abs, "OFFENSE ONLY")

        # Top 10 biggest offensive misses
        print("\n=== Top 10 biggest offensive-player misses ===")
        misses = []
        for pred, actual, position, name, price, team_abbr, opp_abbr in offense_captured:
            pred_f, actual_f = float(pred), float(actual)
            signed = pred_f - actual_f
            misses.append((name, POSITION_LABEL[position], team_abbr, opp_abbr, pred_f, actual_f, signed, abs(signed)))
        misses.sort(key=lambda m: m[7], reverse=True)
        print(f"  {'PLAYER':22}{'POS':5}{'TEAM':6}{'OPP':6}{'PROJ':>8}{'ACTUAL':>8}{'SIGNED':>9}{'ABS':>8}")
        for name, pos, team, opp, pred, actual, signed, absval in misses[:10]:
            print(f"  {name:22}{pos:5}{team or '—':6}{opp or '—':6}{pred:>8.2f}{actual:>8.2f}{signed:>+9.2f}{absval:>8.2f}")

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
