"""
seed_teams.py
-------------
Seeds the 32 real NFL teams (static reference data - doesn't change season
to season beyond relocation/rebrand, which hasn't happened since this list
was compiled). Abbreviations confirmed live against RotoWire's real Week 1
lineups page (2026-09-07) - every code below was directly observed there.

Safe to run repeatedly: upserts on the unique team name.

RUN:
    python scripts/seed_teams.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect

TEAMS = [
    # (name, abbr, conference, division)
    ("Buffalo Bills", "BUF", "AFC", "East"),
    ("Miami Dolphins", "MIA", "AFC", "East"),
    ("New England Patriots", "NE", "AFC", "East"),
    ("New York Jets", "NYJ", "AFC", "East"),
    ("Baltimore Ravens", "BAL", "AFC", "North"),
    ("Cincinnati Bengals", "CIN", "AFC", "North"),
    ("Cleveland Browns", "CLE", "AFC", "North"),
    ("Pittsburgh Steelers", "PIT", "AFC", "North"),
    ("Houston Texans", "HOU", "AFC", "South"),
    ("Indianapolis Colts", "IND", "AFC", "South"),
    ("Jacksonville Jaguars", "JAX", "AFC", "South"),
    ("Tennessee Titans", "TEN", "AFC", "South"),
    ("Denver Broncos", "DEN", "AFC", "West"),
    ("Kansas City Chiefs", "KC", "AFC", "West"),
    ("Las Vegas Raiders", "LV", "AFC", "West"),
    ("Los Angeles Chargers", "LAC", "AFC", "West"),
    ("Dallas Cowboys", "DAL", "NFC", "East"),
    ("New York Giants", "NYG", "NFC", "East"),
    ("Philadelphia Eagles", "PHI", "NFC", "East"),
    ("Washington Commanders", "WAS", "NFC", "East"),
    ("Chicago Bears", "CHI", "NFC", "North"),
    ("Detroit Lions", "DET", "NFC", "North"),
    ("Green Bay Packers", "GB", "NFC", "North"),
    ("Minnesota Vikings", "MIN", "NFC", "North"),
    ("Atlanta Falcons", "ATL", "NFC", "South"),
    ("Carolina Panthers", "CAR", "NFC", "South"),
    ("New Orleans Saints", "NO", "NFC", "South"),
    ("Tampa Bay Buccaneers", "TB", "NFC", "South"),
    ("Arizona Cardinals", "ARI", "NFC", "West"),
    ("Los Angeles Rams", "LAR", "NFC", "West"),
    ("San Francisco 49ers", "SF", "NFC", "West"),
    ("Seattle Seahawks", "SEA", "NFC", "West"),
]


def main():
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            for name, abbr, conference, division in TEAMS:
                cur.execute(
                    """
                    insert into teams (name, abbr, conference, division)
                    values (%s, %s, %s, %s)
                    on conflict (name) do update set abbr = excluded.abbr
                    returning id
                    """,
                    (name, abbr, conference, division),
                )
                team_id = cur.fetchone()[0]
                cur.execute(
                    "insert into team_aliases (team_id, alias) values (%s, %s) on conflict (alias) do nothing",
                    (team_id, abbr),
                )
        conn.commit()
        print(f"Seeded {len(TEAMS)} real NFL teams.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
