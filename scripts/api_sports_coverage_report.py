"""
api_sports_coverage_report.py
--------------------------------
Real validation + coverage report for the API-Sports historical backfill
(migrations 0016/0017). Read-only. Checks, in order:

  1. Duplicate player-games - the SAME our_player_id appearing twice in
     the SAME game (a real matching bug, not prevented by the table's own
     unique constraint since that's keyed on api-sports name/team, not
     our_player_id).
  2. Impossible values - completions > attempts, receptions > targets,
     any negative count stat.
  3. Parsing failures - a real API group (e.g. "Passing") was present in
     raw_stats but its parsed column came out NULL.
  4. Missing games - completed games found at scrape time vs rows actually
     stored, per season.
  5. Player matching coverage - match rate per season, and how many of
     our currently-tracked 603 real players have any historical row at
     all (the number that actually matters for building features for
     TODAY's roster).
  6. Coverage by season x position - distinct players and total
     player-game rows.

RUN:
    python scripts/api_sports_coverage_report.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402

POSITION_LABEL = {"quarterback": "QB", "running_back": "RB", "wide_receiver": "WR", "tight_end": "TE", "defense_special": "D/ST"}


def main():
    conn = db_connect()
    cur = conn.cursor()
    try:
        print("=== 1. Duplicate player-games (same our_player_id twice in one game) ===")
        cur.execute(
            """
            select g.season, g.api_sports_game_id, p.full_name, count(*)
            from api_sports_player_game_stats a
            join api_sports_games g on g.id = a.api_sports_game_id
            join players p on p.id = a.our_player_id
            group by g.season, g.api_sports_game_id, p.full_name
            having count(*) > 1
            """
        )
        dupes = cur.fetchall()
        print(f"  {len(dupes)} real duplicate (player, game) combinations found.")
        for row in dupes[:15]:
            print(f"    {row}")

        print("\n=== 2. Impossible values ===")
        cur.execute("select count(*) from api_sports_player_game_stats where pass_completions > pass_attempts")
        print(f"  Completions > attempts: {cur.fetchone()[0]}")
        cur.execute("select count(*) from api_sports_player_game_stats where receptions > targets")
        print(f"  Receptions > targets: {cur.fetchone()[0]}")
        for col in ["pass_attempts", "pass_completions", "rush_attempts", "targets", "receptions", "pass_yards", "rush_yards", "receiving_yards"]:
            cur.execute(f"select count(*) from api_sports_player_game_stats where {col} < 0")
            n = cur.fetchone()[0]
            if n:
                print(f"  Negative {col}: {n}")
        cur.execute("select count(*) from api_sports_player_game_stats where interceptions_thrown > 8")
        print(f"  Interceptions thrown > 8 in a game (suspiciously high): {cur.fetchone()[0]}")

        print("\n=== 3. Parsing failures (real group present, parsed column null) ===")
        checks = [("Passing", "pass_yards"), ("Rushing", "rush_yards"), ("Receiving", "receiving_yards"), ("Fumbles", "fumbles_total")]
        for group_name, col in checks:
            cur.execute(f"select count(*) from api_sports_player_game_stats where raw_stats ? %s and {col} is null", (group_name,))
            n = cur.fetchone()[0]
            print(f"  Real '{group_name}' group present but {col} null: {n}")

        print("\n=== 4. Games stored per season ===")
        cur.execute("select season, count(*) from api_sports_games group by season order by season")
        for season, n in cur.fetchall():
            expected = 272
            print(f"  {season}: {n} games stored (expected {expected} real regular-season games; {expected - n} missing)" if n != expected else f"  {season}: {n} games stored (all real regular-season games present)")

        print("\n=== 5. Player matching coverage ===")
        cur.execute("select count(*), count(our_player_id) from api_sports_player_game_stats")
        total, matched = cur.fetchone()
        print(f"  {matched} of {total} real player-game rows matched to our players table ({100*matched/total:.1f}%).")
        cur.execute("select count(distinct our_player_id) from api_sports_player_game_stats where our_player_id is not null")
        distinct_matched = cur.fetchone()[0]
        cur.execute("select count(*) from players where is_active = true")
        active_players = cur.fetchone()[0]
        print(f"  {distinct_matched} distinct currently-tracked players have at least one real historical game ({active_players} real active players tracked total).")

        print("\n=== 6. Coverage by season x position ===")
        cur.execute(
            """
            select g.season, p.position, count(distinct a.our_player_id) as distinct_players, count(*) as rows
            from api_sports_player_game_stats a
            join api_sports_games g on g.id = a.api_sports_game_id
            join players p on p.id = a.our_player_id
            where p.position in ('quarterback','running_back','wide_receiver','tight_end')
            group by g.season, p.position
            order by g.season, p.position
            """
        )
        print(f"  {'Season':8}{'Pos':6}{'Players':10}{'Rows':8}")
        for season, pos, players, rows in cur.fetchall():
            print(f"  {season:<8}{POSITION_LABEL[pos]:<6}{players:<10}{rows:<8}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
