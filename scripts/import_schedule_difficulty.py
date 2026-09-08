"""
import_schedule_difficulty.py
--------------------------------
Loads scrape_schedule_difficulty.py's raw JSON into team_schedule_difficulty.

Matches the "current team" by exact name (confirmed identical strings
against our seeded teams.name) and the opponent by abbreviation, with one
confirmed real override: this source uses "LVR" for the Las Vegas Raiders
where this project's own seeded abbr is "LV" - every other one of the 32
real abbreviations matched exactly on the first run, verified by checking
all 32 distinct opponent abbreviations resolved before writing anything.

RUN:
    python scripts/import_schedule_difficulty.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

ABBR_OVERRIDES = {"LVR": "LV"}


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        data = json.loads((ROOT / "schedule_difficulty_raw.json").read_text(encoding="utf-8"))

        cur.execute("select id, name from teams")
        team_id_by_name = {name: tid for tid, name in cur.fetchall()}
        cur.execute("select id, abbr from teams")
        team_id_by_abbr = {abbr: tid for tid, abbr in cur.fetchall()}

        written, unmatched_team, unmatched_opponent = 0, 0, 0
        unmatched_opponent_abbrs = set()

        for entry in data:
            team_id = team_id_by_name.get(entry["team"])
            if team_id is None:
                unmatched_team += 1
                print(f"  [unmatched team] {entry['team']!r}")
                continue

            for w in entry["weeks"]:
                if w.get("isBye"):
                    cur.execute(
                        """
                        insert into team_schedule_difficulty (team_id, gameweek, opponent_team_id, is_home, is_bye, opponent_win_total, source)
                        values (%s, %s, null, null, true, null, 'sharpfootballanalysis')
                        on conflict (team_id, gameweek, source) do update set
                            opponent_team_id = excluded.opponent_team_id, is_home = excluded.is_home,
                            is_bye = excluded.is_bye, opponent_win_total = excluded.opponent_win_total, captured_at = now()
                        """,
                        (team_id, w["week"]),
                    )
                    written += 1
                    continue

                abbr = w.get("opponentAbbr")
                resolved_abbr = ABBR_OVERRIDES.get(abbr, abbr)
                opponent_team_id = team_id_by_abbr.get(resolved_abbr)
                if opponent_team_id is None:
                    unmatched_opponent += 1
                    unmatched_opponent_abbrs.add(abbr)
                    continue

                is_home = w.get("homeAway") == "H"
                cur.execute(
                    """
                    insert into team_schedule_difficulty (team_id, gameweek, opponent_team_id, is_home, is_bye, opponent_win_total, source)
                    values (%s, %s, %s, %s, false, %s, 'sharpfootballanalysis')
                    on conflict (team_id, gameweek, source) do update set
                        opponent_team_id = excluded.opponent_team_id, is_home = excluded.is_home,
                        is_bye = excluded.is_bye, opponent_win_total = excluded.opponent_win_total, captured_at = now()
                    """,
                    (team_id, w["week"], opponent_team_id, is_home, w.get("winsValue")),
                )
                written += 1

        conn.commit()
        print(f"Done: {written} rows written, {unmatched_team} unmatched team(s), {unmatched_opponent} unmatched opponent row(s).")
        if unmatched_opponent_abbrs:
            print(f"  Unmatched opponent abbreviations (need an ABBR_OVERRIDES entry): {sorted(unmatched_opponent_abbrs)}")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
