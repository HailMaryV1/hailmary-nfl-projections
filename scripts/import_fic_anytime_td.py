"""
import_fic_anytime_td.py
---------------------------
Loads scrape_fic_anytime_td.py's raw JSON into player_market_odds as
market 'anytime_td_1plus', source 'fic' (a real, live Caesars sportsbook
line, confirmed live - see the scraper's own module docstring). Stored as
a raw implied probability (from the real American odds), the same
convention every other market in this project uses - compute_projections.py
converts it to an expected count via the Poisson anytime-count formula at
read time, not here.

RUN:
    python scripts/import_fic_anytime_td.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402
from name_matching import resolve_player_id  # noqa: E402
from stat_math import american_to_decimal  # noqa: E402


def find_fixture(cur, home_abbr, away_abbr):
    cur.execute(
        """
        select f.id, f.home_team_id, f.away_team_id
        from fixtures f
        join teams ht on ht.id = f.home_team_id
        join teams at_ on at_.id = f.away_team_id
        where ht.abbr = %s and at_.abbr = %s and f.kickoff_at > now() - interval '6 hours'
        order by f.kickoff_at asc
        limit 1
        """,
        (home_abbr, away_abbr),
    )
    return cur.fetchone()


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        rows = json.loads((ROOT / "fic_anytime_td_raw.json").read_text(encoding="utf-8"))

        fixture_cache = {}
        written, unmatched, no_fixture = 0, 0, 0
        for row in rows:
            key = (row["home"], row["away"])
            if key not in fixture_cache:
                fixture_cache[key] = find_fixture(cur, row["home"], row["away"])
            fixture_row = fixture_cache[key]
            if fixture_row is None:
                no_fixture += 1
                continue
            fixture_id, home_team_id, away_team_id = fixture_row

            player_id = resolve_player_id(cur, row["name"], (home_team_id, away_team_id))
            if player_id is None:
                unmatched += 1
                continue

            decimal_odds = american_to_decimal(row["mline"])
            implied_prob = round(1.0 / decimal_odds, 4)
            cur.execute(
                """
                insert into player_market_odds (player_id, fixture_id, market, value, source, captured_at)
                values (%s, %s, 'anytime_td_1plus', %s, 'fic', now())
                """,
                (player_id, fixture_id, implied_prob),
            )
            written += 1

        conn.commit()
        print(f"Done: {written} anytime_td_1plus rows written, {unmatched} unmatched names, {no_fixture} skipped (no fixture found).")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
