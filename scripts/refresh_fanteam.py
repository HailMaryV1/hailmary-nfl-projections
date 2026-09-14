"""
refresh_fanteam.py
---------------------
Single entrypoint for everything FanTeam-sourced: real players/fixtures/
prices/lineup status, real post-game player stats/points, and capturing
those into predictions_and_actuals for the Accuracy page. Exists because
FanTeam's own API returns a real, persistent 401 to GitHub Actions'
shared datacenter-IP runners (confirmed 2026-09-08, see
docs/data-and-weights.md) - this is meant to run on a real machine with a
normal IP instead (this one, via Windows Task Scheduler - see
docs/data-and-weights.md's 2026-09-14 entry for the exact setup), not CI.

Does NOT run freeze_predictions.py - that only depends on `projections`
(already computed independently every 6 hours in the automated CI
workflow), not on anything FanTeam-sourced, so it has nothing to gain from
running here too.

Same "one step's failure doesn't block the rest" resilience pattern as
refresh_nfl.py.

RUN:
    python scripts/refresh_fanteam.py
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    "scrape_fanteam.py",
    "import_fanteam.py",
    "scrape_fanteam_stats.py",
    "import_fanteam_stats.py",
    "capture_actuals.py",
]


def run_step(script_name):
    print(f"\n=== {script_name} ===", flush=True)
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script_name)], cwd=ROOT)
    ok = result.returncode == 0
    if not ok:
        print(f"[FAILED] {script_name} (exit {result.returncode})")
    return ok


def main():
    results = {step: run_step(step) for step in STEPS}

    print("\n=== Summary ===")
    for step, ok in results.items():
        print(f"  {'OK' if ok else 'FAILED'} - {step}")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
