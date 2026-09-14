"""
scrape_api_sports_gw1.py
---------------------------
Pulls real 2026 NFL Week 1 games from API-Sports (league=1/NFL), then real
per-game player box-score statistics for every REAL completed game
(status "FT" or "AOT" - After Over Time, still a finished game).

Real, confirmed-live API quirks (2026-09-14):
- `week` is not a valid /games query filter ("The Week field do not
  exist.") - fetch the whole real season and filter client-side on
  game.stage == "Regular Season" and game.week == "Week 1".
- The free plan returns a real, explicit error for the 2026 season
  ("Free plans do not have access to this season, try from 2022 to
  2024.") - this script assumes a paid plan that has real 2026 access
  (confirmed live once upgraded).

Writes one raw JSON file (list of {game, player_stats_response}) for
import_api_sports_gw1.py to parse - same scrape/import split as every
other real ingestion script in this project.

RUN:
    python scripts/scrape_api_sports_gw1.py
"""
import json
import os
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, load_env  # noqa: E402
BASE = "https://v1.american-football.api-sports.io"
LEAGUE_ID = 1  # NFL
SEASON = 2026
WEEK_LABEL = "Week 1"
RAW_OUT = ROOT / "api_sports_gw1_raw.json"

FINISHED_STATUSES = {"FT", "AOT"}


def api_get(path, params, api_key):
    resp = requests.get(f"{BASE}{path}", params=params, headers={"x-apisports-key": api_key}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("errors"):
        raise SystemExit(f"API-Sports error on {path} {params}: {data['errors']}")
    return data


def main():
    load_env()
    api_key = os.environ.get("API_SPORTS_KEY")
    if not api_key:
        raise SystemExit("API_SPORTS_KEY not set in .env")

    print(f"Fetching real {SEASON} NFL games ...")
    games_data = api_get("/games", {"league": LEAGUE_ID, "season": SEASON}, api_key)
    all_games = games_data["response"]
    week1_games = [g for g in all_games if g["game"]["stage"] == "Regular Season" and g["game"]["week"] == WEEK_LABEL]
    print(f"  {len(week1_games)} real Week 1 regular season games found.")

    completed = [g for g in week1_games if g["game"]["status"]["short"] in FINISHED_STATUSES]
    not_completed = [g for g in week1_games if g["game"]["status"]["short"] not in FINISHED_STATUSES]
    print(f"  {len(completed)} completed, {len(not_completed)} not yet finished (skipped): "
          f"{[g['teams']['home']['name'] + ' vs ' + g['teams']['away']['name'] for g in not_completed]}")

    results = []
    for g in completed:
        game_id = g["game"]["id"]
        home, away = g["teams"]["home"]["name"], g["teams"]["away"]["name"]
        print(f"  Fetching player stats for game {game_id} ({home} vs {away}) ...")
        stats_data = api_get("/games/statistics/players", {"id": game_id}, api_key)
        results.append({"game": g, "player_stats_response": stats_data})
        time.sleep(0.3)  # polite pacing, well within the real 7500/day Pro quota

    RAW_OUT.write_text(json.dumps(results, indent=2))
    print(f"-> {RAW_OUT} ({len(results)} real completed games)")


if __name__ == "__main__":
    main()
