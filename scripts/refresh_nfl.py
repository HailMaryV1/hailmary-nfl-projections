"""
refresh_nfl.py
-----------------
Single entrypoint for the automated data-refresh pipeline. Runs every real
ingestion script in the order its own output depends on the step before it,
then exits non-zero if anything failed (so a GitHub Actions run goes red) -
but a step's own failure doesn't stop the rest of the pipeline running (a
transient Spreadex/RotoWire hiccup in one step shouldn't also block every
step after it), same reasoning as Dream Team Projections'
scripts/refresh_dreamteam.py.

Order, and why:
  1. seed_teams.py                    - idempotent; everything below assumes teams/team_aliases exist
  2. scrape_fanteam.py                - real players/fixtures/teams in one call
  3. import_fanteam.py                - reads that raw file -> fixtures, players, lineup_status (source 'fanteam')
  4. scrape_rotowire_lineups.py       - real starters/inactives/odds/weather - needs our fixtures to already exist (step 3)
  5. import_rotowire_lineups.py       - lineup_status (source 'rotowire'), game_odds, fixture_weather
  6. scrape_spreadex_nfl_props.py     - real player-prop odds - needs our fixtures + players to already exist
  7. scrape_fic_anytime_td.py         - real live "Score Any TD" odds (Caesars line via fantasyinfocentral.com)
  8. import_fic_anytime_td.py         - anytime_td market - needs our fixtures + players to already exist
  9. scrape_schedule_difficulty.py    - real full-season (18-week) matchups + Vegas-derived opponent win totals
 10. import_schedule_difficulty.py    - team_schedule_difficulty - only needs teams (step 1), independent of the rest

This is data ingestion only - the projection engine (Phase 3) that turns
these real rows into a rating is a separate, later step, not run here.

FanTeam (steps 2-3) is excluded from the automated GitHub Actions schedule
via --skip fanteam: their player prices have never moved once across this
whole project's history, and their own API returns a real, persistent 401
to GitHub's shared runner IPs regardless (see docs/data-and-weights.md).
Run it manually instead - `python scripts/scrape_fanteam.py && python
scripts/import_fanteam.py` - whenever a new gameweek needs its fixtures
pulled in, or once real games are played and gameweek points need capturing.

RUN:
    python scripts/refresh_nfl.py             # everything, incl. FanTeam
    python scripts/refresh_nfl.py --skip fanteam   # what CI actually runs
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = [
    "seed_teams.py",
    "scrape_fanteam.py",
    "import_fanteam.py",
    "scrape_rotowire_lineups.py",
    "import_rotowire_lineups.py",
    "scrape_spreadex_nfl_props.py",
    "scrape_fic_anytime_td.py",
    "import_fic_anytime_td.py",
    "scrape_schedule_difficulty.py",
    "import_schedule_difficulty.py",
]

# Maps a --skip name to the script-name substrings it excludes.
SKIP_GROUPS = {
    "fanteam": ["fanteam.py"],
}


def run_step(script_name):
    print(f"\n=== {script_name} ===")
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script_name)], cwd=ROOT)
    ok = result.returncode == 0
    if not ok:
        print(f"[FAILED] {script_name} (exit {result.returncode})")
    return ok


def main():
    skip_names = set()
    if "--skip" in sys.argv:
        skip_names = set(sys.argv[sys.argv.index("--skip") + 1].split(","))
    skip_substrings = [s for name in skip_names for s in SKIP_GROUPS.get(name, [])]

    steps = [s for s in STEPS if not any(sub in s for sub in skip_substrings)]
    for skipped in set(STEPS) - set(steps):
        print(f"\n=== {skipped} === [SKIPPED via --skip]")

    results = {step: run_step(step) for step in steps}

    print("\n=== Summary ===")
    for step, ok in results.items():
        print(f"  {'OK' if ok else 'FAILED'} - {step}")

    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
