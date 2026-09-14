"""
import_api_sports_gw1.py
---------------------------
Loads scrape_api_sports_gw1.py's raw JSON into api_sports_games +
api_sports_player_game_stats - real per-game box-score stats, both parsed
and kept raw (see migration 0016's own comment for why both).

Real parsing notes (API-Sports' own field names, confirmed live
2026-09-14, not assumed from docs):
  Passing group:  "comp att" is a combined "completions/attempts" string;
                  "sacks" is a combined "count-yards_lost" string (only the
                  count is kept - yards lost isn't in our own schema).
  Rushing group:  "total rushes", "yards", "rushing touch downs".
  Receiving group: "targets", "total receptions", "yards",
                  "receiving touch downs" - NOTE "yards" here is a
                  different real stat than Passing/Rushing's own "yards"
                  key of the same name; kept separate by tracking which
                  group each value came from, never merged by raw key name
                  alone.
  Fumbles group:  "total", "lost" (rec/rec_td exist too but aren't in our
                  own schema - the real group's raw JSON is preserved
                  either way).
A player can appear in more than one group (a QB who also rushes; a WR
who also returns punts) - one flat row per (game, player) accumulates
every group they appeared in.

Player matching reuses name_matching.resolve_player_id, scoped to the one
real team the player's group belongs to (tighter than
import_rotowire_lineups.py's two-team scope, since API-Sports already
tells us which specific team each player is grouped under).

RUN:
    python scripts/import_api_sports_gw1.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402
from name_matching import resolve_player_id  # noqa: E402


def parse_comp_att(value):
    if not value or "/" not in value:
        return None, None
    comp, att = value.split("/", 1)
    try:
        return int(comp), int(att)
    except ValueError:
        return None, None


def parse_leading_int(value):
    """'0-0' -> 0 (sacks: count-yards_lost, only count kept)."""
    if value is None:
        return None
    head = str(value).split("-", 1)[0]
    try:
        return int(head)
    except ValueError:
        return None


def parse_int(value):
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def stat_map(entries):
    return {e["name"]: e["value"] for e in entries}


def merge_player_stats(acc, group_name, entries):
    s = stat_map(entries)
    if group_name == "Passing":
        comp, att = parse_comp_att(s.get("comp att"))
        acc["pass_completions"] = comp
        acc["pass_attempts"] = att
        acc["pass_yards"] = parse_int(s.get("yards"))
        acc["pass_td"] = parse_int(s.get("passing touch downs"))
        acc["interceptions_thrown"] = parse_int(s.get("interceptions"))
        acc["sacks_taken"] = parse_leading_int(s.get("sacks"))
    elif group_name == "Rushing":
        acc["rush_attempts"] = parse_int(s.get("total rushes"))
        acc["rush_yards"] = parse_int(s.get("yards"))
        acc["rush_td"] = parse_int(s.get("rushing touch downs"))
    elif group_name == "Receiving":
        acc["targets"] = parse_int(s.get("targets"))
        acc["receptions"] = parse_int(s.get("total receptions"))
        acc["receiving_yards"] = parse_int(s.get("yards"))
        acc["receiving_td"] = parse_int(s.get("receiving touch downs"))
    elif group_name == "Fumbles":
        acc["fumbles_total"] = parse_int(s.get("total"))
        acc["fumbles_lost"] = parse_int(s.get("lost"))
    acc.setdefault("raw_groups", {})[group_name] = entries


PARSED_COLUMNS = [
    "pass_attempts", "pass_completions", "pass_yards", "pass_td", "interceptions_thrown", "sacks_taken",
    "rush_attempts", "rush_yards", "rush_td",
    "targets", "receptions", "receiving_yards", "receiving_td",
    "fumbles_total", "fumbles_lost",
]


def import_game(cur, entry, team_id_by_name):
    game = entry["game"]["game"]
    teams = entry["game"]["teams"]
    stats_response = entry["player_stats_response"]

    cur.execute(
        """
        insert into api_sports_games (api_sports_game_id, season, week, stage, home_team_name, away_team_name, status_short, kickoff_at, raw_response)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (api_sports_game_id) do update set
            status_short = excluded.status_short, raw_response = excluded.raw_response
        returning id
        """,
        (
            game["id"], int(entry["game"]["league"]["season"]), game["week"], game["stage"],
            teams["home"]["name"], teams["away"]["name"], game["status"]["short"],
            datetime.fromtimestamp(game["date"]["timestamp"], tz=timezone.utc) if game["date"].get("timestamp") else None,
            json.dumps(entry),
        ),
    )
    api_sports_game_id = cur.fetchone()[0]

    players_recorded, matched, unmatched = 0, 0, 0
    for team_block in stats_response.get("response", []):
        team_name = team_block["team"]["name"]
        our_team_id = team_id_by_name.get(team_name)

        by_player = {}
        for group in team_block.get("groups", []):
            group_name = group["name"]
            if group_name not in ("Passing", "Rushing", "Receiving", "Fumbles"):
                continue
            for p in group.get("players", []):
                key = (p["player"]["id"], p["player"]["name"])
                acc = by_player.setdefault(key, {"player_id": p["player"]["id"], "player_name": p["player"]["name"]})
                merge_player_stats(acc, group_name, p["statistics"])

        for (_api_player_id, player_name), acc in by_player.items():
            our_player_id = None
            if our_team_id is not None:
                our_player_id = resolve_player_id(cur, player_name, [our_team_id])
            if our_player_id:
                matched += 1
            else:
                unmatched += 1

            cur.execute(
                f"""
                insert into api_sports_player_game_stats
                    (api_sports_game_id, api_sports_player_id, player_name, team_name, {", ".join(PARSED_COLUMNS)}, raw_stats, our_player_id)
                values (%s, %s, %s, %s, {", ".join(["%s"] * len(PARSED_COLUMNS))}, %s, %s)
                on conflict (api_sports_game_id, player_name, team_name) do update set
                    {", ".join(f"{c} = excluded.{c}" for c in PARSED_COLUMNS)},
                    raw_stats = excluded.raw_stats, our_player_id = excluded.our_player_id
                """,
                (
                    api_sports_game_id, acc["player_id"], player_name, team_name,
                    *[acc.get(c) for c in PARSED_COLUMNS],
                    json.dumps(acc.get("raw_groups", {})), our_player_id,
                ),
            )
            players_recorded += 1

    print(f"  Game {game['id']} ({teams['home']['name']} vs {teams['away']['name']}): {players_recorded} players, {matched} matched, {unmatched} unmatched.")
    return matched, unmatched


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        data = json.loads((ROOT / "api_sports_gw1_raw.json").read_text(encoding="utf-8"))
        cur.execute("select name, id from teams")
        team_id_by_name = dict(cur.fetchall())

        total_matched, total_unmatched = 0, 0
        for entry in data:
            m, u = import_game(cur, entry, team_id_by_name)
            total_matched += m
            total_unmatched += u

        conn.commit()
        print(f"\nTotal: {total_matched} matched, {total_unmatched} unmatched across {len(data)} games.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
