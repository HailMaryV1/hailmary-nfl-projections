"""
import_fanteam_stats.py
-------------------------
Loads scrape_fanteam_stats.py's raw JSON into player_stats - one real row
per player per finished real gameweek.

Player matching uses the same convention as import_fanteam.py:
external_id = str(realPlayerId), direct, no surname-matching cascade.

Column mapping (FanTeam's real `totalStats` key -> our real column) is
built only from keys actually observed live 2026-09-13 across gameweek 1's
finished games - see STAT_KEY_MAP below. A handful of real, scored stats
(supabase/migrations/0005_scoring_rules.sql: two_point_conversion, safety,
blocked_kick, defensive_td, return_td) hadn't occurred yet in that sample,
so their real FanTeam key spelling is still unconfirmed - rather than
guess, this leaves those columns null and prints any unmapped `totalStats`
key it encounters, so a real occurrence gets caught and STAT_KEY_MAP
extended with a confirmed spelling, never a guessed one. The full raw
`totalStats` blob is always stored in `raw_stats` regardless, so nothing
is ever lost while a mapping is still unconfirmed.

RUN:
    python scripts/import_fanteam_stats.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402

SEASON = "2026"

# FanTeam totalStats key -> player_stats column. Confirmed live 2026-09-13
# against gameweek 1's real finished games (offense: QB/RB/WR stat lines;
# defense_special: real D/ST unit lines).
STAT_KEY_MAP = {
    "passingYards": "passing_yards",
    "passingTd": "passing_tds",
    "intercepted": "interceptions_thrown",
    "rushingYards": "rushing_yards",
    "rushingTd": "rushing_tds",
    "reception": "receptions",
    "receivingYards": "receiving_yards",
    "receivingTd": "receiving_tds",
    "fumbleLost": "fumbles_lost",
    "sack": "sacks",
    "interception": "def_interceptions",
    "fumbleRecovery": "fumble_recoveries",
    "pointsAllowed": "points_allowed",
}
# Real keys that are meta/bonus-threshold flags, not stats our schema has a
# column for - deliberately not mapped, but not "unmapped" warnings either.
KNOWN_UNMAPPED_KEYS = {"matchCount", "startCount", "minutesPlayed", "allowed21", "allowed7", "receivingYards100", "rushingYards100", "passingYards300"}

STAT_COLUMNS = sorted(set(STAT_KEY_MAP.values()))


def import_stats(cur, by_round):
    cur.execute("select external_id, id from players where external_id is not null")
    player_id_by_external = {ext_id: pid for ext_id, pid in cur.fetchall()}

    upserted, skipped_unfinished, skipped_unmatched = 0, 0, 0
    unmapped_keys_seen = set()

    for gw_str, choices in by_round.items():
        gameweek = int(gw_str)
        for p in choices:
            if p.get("status") != "finished":
                skipped_unfinished += 1
                continue
            external_id = str(p["realPlayerId"])
            player_id = player_id_by_external.get(external_id)
            if player_id is None:
                skipped_unmatched += 1
                continue

            raw_stats = p.get("totalStats") or {}
            for key in raw_stats:
                if key not in STAT_KEY_MAP and key not in KNOWN_UNMAPPED_KEYS:
                    unmapped_keys_seen.add(key)

            values = {col: raw_stats.get(fanteam_key) for fanteam_key, col in STAT_KEY_MAP.items()}
            # Every mapped column is scored only when the player actually
            # played (status == "finished" confirmed above) - a real,
            # confirmed absence of a key means that stat is really 0 for
            # this game (FanTeam omits zero-valued keys), not unknown.
            values = {col: (0 if v is None else v) for col, v in values.items()}
            # `points` (== `lastPoints` in every real row seen so far) is
            # this specific round's real score - `totalPoints` reads 0 in
            # every sample observed 2026-09-13 (gameweek 1, the only round
            # played so far) and looks unpopulated by FanTeam rather than a
            # real season-to-date figure; re-verify once gameweek 2 finishes.
            total_points = p.get("points")

            columns = ["player_id", "season", "gameweek", "total_points", "raw_stats", *STAT_COLUMNS]
            placeholders = ", ".join(["%s"] * len(columns))
            update_clause = ", ".join(f"{c} = excluded.{c}" for c in columns if c not in ("player_id", "season", "gameweek"))
            cur.execute(
                f"""
                insert into player_stats ({", ".join(columns)})
                values ({placeholders})
                on conflict (player_id, season, gameweek) do update set {update_clause}
                """,
                (player_id, SEASON, gameweek, total_points, json.dumps(raw_stats), *[values[c] for c in STAT_COLUMNS]),
            )
            upserted += 1

    print(f"player_stats: {upserted} upserted, {skipped_unfinished} not-yet-finished, {skipped_unmatched} unmatched player.")
    if unmapped_keys_seen:
        print(f"  [REVIEW] real stats keys seen with no column mapping yet: {sorted(unmapped_keys_seen)} - see STAT_KEY_MAP.")


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        by_round = json.loads((ROOT / "fanteam_stats_raw.json").read_text(encoding="utf-8"))
        if not by_round:
            print("No real gameweeks with finished games yet - nothing to import.")
            return
        import_stats(cur, by_round)
        conn.commit()
        print("Done.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
