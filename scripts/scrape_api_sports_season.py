"""
scrape_api_sports_season.py
------------------------------
Generalized version of scrape_api_sports_gw1.py - pulls every real
completed Regular Season game (any week, not just Week 1) for one or more
real seasons, plus BOTH player and team box-score stats per game.

Real, confirmed-live status-encoding quirk (2026-09-14, checked across
2022-2025): a finished game is either {"short": "FT", "long": "Finished"}
or, for a real overtime game, {"short": None, "long": "Final/OT"} - older
seasons never use the 2026 season's own "AOT" short code. Both real
patterns are treated as completed here; anything else (postponed, not yet
played) is skipped.

Writes one raw JSON file per season: api_sports_season_{season}_raw.json
(list of {game, player_stats_response, team_stats_response}).

RUN:
    python scripts/scrape_api_sports_season.py 2022 2023 2024 2025
"""
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, load_env  # noqa: E402
import os  # noqa: E402

BASE = "https://v1.american-football.api-sports.io"
LEAGUE_ID = 1  # NFL


def is_completed(status):
    return status["short"] in ("FT", "AOT") or status["long"] == "Final/OT"


def api_get(path, params, api_key, retries=3):
    for attempt in range(1, retries + 1):
        resp = requests.get(f"{BASE}{path}", params=params, headers={"x-apisports-key": api_key}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            if attempt < retries:
                print(f"  [retry] {path} {params}: {data['errors']}")
                time.sleep(2)
                continue
            raise SystemExit(f"API-Sports error on {path} {params}: {data['errors']}")
        return data
    return None


def scrape_season(season, api_key):
    out_path = ROOT / f"api_sports_season_{season}_raw.json"
    print(f"\n=== Season {season} ===")
    games_data = api_get("/games", {"league": LEAGUE_ID, "season": season}, api_key)
    all_games = games_data["response"]
    season_games = [g for g in all_games if g["game"]["stage"] == "Regular Season"]
    completed = [g for g in season_games if is_completed(g["game"]["status"])]
    print(f"  {len(season_games)} real regular season games, {len(completed)} completed.")

    results = []
    for i, g in enumerate(completed, 1):
        game_id = g["game"]["id"]
        home, away = g["teams"]["home"]["name"], g["teams"]["away"]["name"]
        print(f"  [{i}/{len(completed)}] game {game_id} ({g['game']['week']}: {home} vs {away}) ...", flush=True)
        player_stats = api_get("/games/statistics/players", {"id": game_id}, api_key)
        time.sleep(0.15)
        team_stats = api_get("/games/statistics/teams", {"id": game_id}, api_key)
        time.sleep(0.15)
        results.append({"game": g, "player_stats_response": player_stats, "team_stats_response": team_stats})

    out_path.write_text(json.dumps(results, indent=2))
    print(f"  -> {out_path} ({len(results)} real completed games)")


def main():
    load_env()
    api_key = os.environ.get("API_SPORTS_KEY")
    if not api_key:
        raise SystemExit("API_SPORTS_KEY not set in .env")

    seasons = [int(a) for a in sys.argv[1:]] or [2022, 2023, 2024, 2025]
    for season in seasons:
        scrape_season(season, api_key)


if __name__ == "__main__":
    main()
