"""
scrape_fanteam_stats.py
-------------------------
Pulls FanTeam/ScoutGG's real post-game player stats/points, one call per
real gameweek, for tournament 1136503 ("NFL Regular Season 2026/27").

Confirmed live 2026-09-13 (see docs/data-and-weights.md): the same
`/tournaments/{id}/players` endpoint scrape_fanteam.py already uses returns
real per-player `totalStats`/`points` once a `round` number (not `editable`)
is requested, for every player whose real game has actually been played
(`status: "finished"`). `round=editable&bearer[white_label]=fanteam` also
returns `statsRound`: the latest real gameweek with any finished games -
used here to know how many rounds are worth pulling, rather than guessing
or hammering all 18 gameweeks every run.

RUN:
    python scripts/scrape_fanteam_stats.py
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

TOURNAMENT_ID = "1136503"
BASE = "https://fanteam-game.api.scoutgg.net"
BEARER_QS = "bearer%5Bwhite_label%5D=fanteam"

RAW_OUT = Path(__file__).resolve().parent.parent / "fanteam_stats_raw.json"


def fetch_json(url, retries=5, backoff_seconds=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    last_status = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            last_status = e.code
            if e.code == 401:
                break
        except urllib.error.URLError as e:
            print(f"  Network error on attempt {attempt}/{retries}: {e.reason}")
            last_status = None
        if attempt < retries and last_status != 401:
            status_desc = f"HTTP {last_status}" if last_status is not None else "a network error"
            print(f"  Attempt {attempt}/{retries} got {status_desc} - retrying in {backoff_seconds}s ...")
            time.sleep(backoff_seconds)
    return last_status, None


def main():
    print("Finding the latest real gameweek with finished games ...")
    status, editable_data = fetch_json(f"{BASE}/tournaments/{TOURNAMENT_ID}/players?round=editable&{BEARER_QS}")
    if status != 200:
        raise SystemExit(f"FanTeam request failed: HTTP {status}")
    stats_round = editable_data.get("statsRound")
    if not stats_round:
        print("  statsRound is empty - no real games finished yet this season. Nothing to pull.")
        RAW_OUT.write_text(json.dumps({}, indent=2))
        return
    print(f"  Real games finished through gameweek {stats_round}.")

    by_round = {}
    for gw in range(1, stats_round + 1):
        print(f"Fetching gameweek {gw} ...")
        status, data = fetch_json(f"{BASE}/tournaments/{TOURNAMENT_ID}/players?round={gw}&{BEARER_QS}")
        if status != 200:
            print(f"  [SKIPPED] gameweek {gw}: HTTP {status}")
            continue
        choices = data.get("playerChoices", [])
        finished = [p for p in choices if p.get("status") == "finished"]
        by_round[str(gw)] = choices
        print(f"  {len(finished)} of {len(choices)} players finished.")

    RAW_OUT.write_text(json.dumps(by_round, indent=2))
    print(f"-> {RAW_OUT}")


if __name__ == "__main__":
    main()
