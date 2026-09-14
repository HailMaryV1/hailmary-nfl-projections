"""
import_fanteam_stats.py
-------------------------
Loads scrape_fanteam_stats.py's raw JSON into player_stats - one real row
per player per finished real gameweek.

Player matching uses the same convention as import_fanteam.py:
external_id = str(realPlayerId), direct, no surname-matching cascade.

Column mapping (FanTeam's real `totalStats` key -> our real column) is
built only from keys actually observed live - see STAT_KEY_MAP below. A
handful of real, scored stats (supabase/migrations/0005_scoring_rules.sql:
two_point_conversion, safety, blocked_kick, defensive_td, return_td)
hadn't occurred at all in the first gameweek-1 sample (2026-09-13); two of
them (`blockedKick`, `defensiveTd`) showed up unambiguously the next day
once more of gameweek 1 had finished and are now mapped.

`conversion`/`conversionPass`/`conversionReturn` are deliberately still
NOT mapped despite appearing live 2026-09-14: a real example showed a QB
with BOTH `conversion: 1` AND `conversionPass: 1` set on his own row for
what looks like a single real 2-point conversion pass he threw (to a
teammate whose own row separately shows `conversion: 1` alone) - summing
both keys into `two_point_conversions` would double-count that passer's
real credit, and mapping only one of them risks under-counting whichever
real case actually needs both. Real attribution isn't confirmed yet, so
rather than guess, these keep surfacing in the unmapped-keys warning below
until verified against FanTeam's own real scoring breakdown for an
affected player. The full raw `totalStats` blob is always stored in
`raw_stats` regardless, so nothing is ever lost while a mapping is still
unconfirmed.

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
    "blockedKick": "blocked_kicks",
    "defensiveTd": "def_special_tds",
}
# Real keys that are meta/bonus-threshold flags, not stats our schema has a
# column for - deliberately not mapped, but not "unmapped" warnings either.
# The allowedN family are all real points-allowed scoring-tier flags -
# redundant with the real pointsAllowed number itself (already mapped).
KNOWN_UNMAPPED_KEYS = {
    "matchCount", "startCount", "minutesPlayed",
    "allowed7", "allowed14", "allowed21", "allowed28", "allowed35",
    "receivingYards100", "rushingYards100", "passingYards300",
}

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

            # Summed, not overwritten - more than one FanTeam key can map
            # to the same real column (none currently do, but a silent
            # dict-comprehension overwrite would be the wrong semantics if
            # one ever does). A real, confirmed absence of a key means
            # that stat is really 0 for this game (FanTeam omits
            # zero-valued keys, and status == "finished" confirms the
            # player actually played), not unknown.
            values = {col: 0 for col in STAT_COLUMNS}
            for fanteam_key, col in STAT_KEY_MAP.items():
                v = raw_stats.get(fanteam_key)
                if v is not None:
                    values[col] += v
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
