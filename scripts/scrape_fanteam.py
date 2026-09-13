"""
scrape_fanteam.py
-------------------
Pulls FanTeam/ScoutGG's single players endpoint for tournament 1136503
("NFL Regular Season 2026/27") - confirmed live 2026-09-07 to return
players, real fixtures (with real home/away team ids and kickoff times) and
real teams all in one unauthenticated call. Unlike the football tournament
in the sibling dreamteam-scraper repo, no separate authenticated fixtures
call is needed here - this one response has everything.

Real regression found and fixed 2026-09-13: this endpoint started
returning a real HTTP 401 ("no_client") sometime after the season kicked
off 2026-09-10, even from a plain residential IP (not the GitHub-runner
datacenter-IP issue `docs/data-and-weights.md` already documents) -
`fanteam_raw.json` had gone stale since 2026-09-07. Confirmed live in the
browser: FanTeam's own frontend always sends a `bearer[white_label]=fanteam`
query param (visible on every one of its own API calls, including the
public, signed-out team-dashboard pages) - not a secret, not tied to any
user/session, just an app identifier the API now enforces. Adding it here
restores the real unauthenticated call.

RUN:
    python scripts/scrape_fanteam.py
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

TOURNAMENT_ID = "1136503"
BASE = "https://fanteam-game.api.scoutgg.net"
# Not a secret and not tied to any user/session - FanTeam's own frontend
# sends this on every API call, signed in or not. See the module docstring.
BEARER_QS = "bearer%5Bwhite_label%5D=fanteam"

RAW_OUT = Path(__file__).resolve().parent.parent / "fanteam_raw.json"


def fetch_json(url, retries=8, backoff_seconds=30):
    # Same resilience pattern as the sibling dreamteam-scraper repo's
    # scraper_fanteam.py - a single transient blip (rate-limit, WAF hiccup)
    # shouldn't kill an entire scheduled run. A 401 is never transient
    # (missing/wrong auth, not a rate limit), so that one fails fast rather
    # than burning the full retry budget - the real cause of a run taking
    # 4 minutes just to fail, found live 2026-09-13.
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
    print("Fetching FanTeam NFL players/fixtures/teams ...")
    status, data = fetch_json(f"{BASE}/tournaments/{TOURNAMENT_ID}/players?round=editable&{BEARER_QS}")
    if status != 200:
        raise SystemExit(f"FanTeam request failed: HTTP {status}")

    RAW_OUT.write_text(json.dumps(data, indent=2))
    print(
        f"  {len(data.get('playerChoices', []))} players, "
        f"{len(data.get('realMatches', []))} fixtures, "
        f"{len(data.get('realTeams', []))} teams -> {RAW_OUT}"
    )


if __name__ == "__main__":
    main()
