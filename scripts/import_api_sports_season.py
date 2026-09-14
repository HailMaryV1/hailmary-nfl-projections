"""
import_api_sports_season.py
------------------------------
Generalized version of import_api_sports_gw1.py - loads
scrape_api_sports_season.py's raw JSON (any season(s), every real
completed regular-season game) into api_sports_games,
api_sports_player_game_stats, AND api_sports_team_game_stats (new -
migration 0017). Same real parsing/matching rules as the GW1 import - see
that script's own docstring for the exact field-name notes (comp/att
splitting, sacks count-only, etc.), unchanged here.

Team-stats parsing (real API-Sports field names, confirmed live across
2022-2026): `plays.total`, `passing.total`/`comp_att` ("33-53" dash-
separated)/`interceptions_thrown`, `rushings.total`/`attempts`,
`interceptions.total` (real defensive INTs), `fumbles_recovered.total`,
`sacks.total`, `safeties.total`, `int_touchdowns.total`,
`points_against.total`. Real points_scored is read off the game's own
`scores` block, not the team-stats endpoint (which only reports points
*against*, i.e. what the OTHER team scored).

RUN:
    python scripts/import_api_sports_season.py 2022 2023 2024 2025
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402
from name_matching import resolve_player_id_strict  # noqa: E402

PLAYER_PARSED_COLUMNS = [
    "pass_attempts", "pass_completions", "pass_yards", "pass_td", "interceptions_thrown", "sacks_taken",
    "rush_attempts", "rush_yards", "rush_td",
    "targets", "receptions", "receiving_yards", "receiving_td",
    "fumbles_total", "fumbles_lost",
]
TEAM_PARSED_COLUMNS = [
    "offensive_plays", "total_yards", "pass_attempts", "pass_completions", "pass_yards",
    "rush_attempts", "rush_yards", "interceptions_thrown", "points_scored", "points_against",
    "sacks", "def_interceptions", "fumbles_recovered", "safeties", "int_touchdowns",
]


def parse_comp_att(value, sep="/"):
    if not value or sep not in value:
        return None, None
    a, b = value.split(sep, 1)
    try:
        return int(a), int(b)
    except ValueError:
        return None, None


def parse_leading_int(value, sep="-"):
    if value is None:
        return None
    head = str(value).split(sep, 1)[0]
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
        comp, att = parse_comp_att(s.get("comp att"), "/")
        acc["pass_completions"], acc["pass_attempts"] = comp, att
        acc["pass_yards"] = parse_int(s.get("yards"))
        acc["pass_td"] = parse_int(s.get("passing touch downs"))
        acc["interceptions_thrown"] = parse_int(s.get("interceptions"))
        acc["sacks_taken"] = parse_leading_int(s.get("sacks"), "-")
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


def parse_team_stats(stats):
    s = stats
    comp, att = parse_comp_att((s.get("passing") or {}).get("comp_att"), "-")
    return {
        "offensive_plays": parse_int((s.get("plays") or {}).get("total")),
        "total_yards": parse_int((s.get("yards") or {}).get("total")),
        "pass_attempts": att,
        "pass_completions": comp,
        "pass_yards": parse_int((s.get("passing") or {}).get("total")),
        "rush_attempts": parse_int((s.get("rushings") or {}).get("attempts")),
        "rush_yards": parse_int((s.get("rushings") or {}).get("total")),
        "interceptions_thrown": parse_int((s.get("passing") or {}).get("interceptions_thrown")),
        "points_against": parse_int((s.get("points_against") or {}).get("total")),
        "sacks": parse_int((s.get("sacks") or {}).get("total")),
        "def_interceptions": parse_int((s.get("interceptions") or {}).get("total")),
        "fumbles_recovered": parse_int((s.get("fumbles_recovered") or {}).get("total")),
        "safeties": parse_int((s.get("safeties") or {}).get("total")),
        "int_touchdowns": parse_int((s.get("int_touchdowns") or {}).get("total")),
    }


def import_game(cur, entry, team_id_by_name):
    game = entry["game"]["game"]
    teams = entry["game"]["teams"]
    scores = entry["game"].get("scores", {})
    player_stats_response = entry["player_stats_response"]
    team_stats_response = entry["team_stats_response"]

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
            teams["home"]["name"], teams["away"]["name"], game["status"]["short"] or game["status"]["long"],
            datetime.fromtimestamp(game["date"]["timestamp"], tz=timezone.utc) if game["date"].get("timestamp") else None,
            json.dumps(entry),
        ),
    )
    api_sports_game_id = cur.fetchone()[0]

    # --- Player stats ---
    matched, unmatched = 0, 0
    for team_block in player_stats_response.get("response", []):
        team_name = team_block["team"]["name"]
        our_team_id = team_id_by_name.get(team_name)
        by_player = {}
        for group in team_block.get("groups", []):
            if group["name"] not in ("Passing", "Rushing", "Receiving", "Fumbles"):
                continue
            for p in group.get("players", []):
                key = (p["player"]["id"], p["player"]["name"])
                acc = by_player.setdefault(key, {"player_id": p["player"]["id"], "player_name": p["player"]["name"]})
                merge_player_stats(acc, group["name"], p["statistics"])

        for (_pid, player_name), acc in by_player.items():
            our_player_id = resolve_player_id_strict(cur, player_name, [our_team_id]) if our_team_id is not None else None
            matched += 1 if our_player_id else 0
            unmatched += 0 if our_player_id else 1
            cur.execute(
                f"""
                insert into api_sports_player_game_stats
                    (api_sports_game_id, api_sports_player_id, player_name, team_name, {", ".join(PLAYER_PARSED_COLUMNS)}, raw_stats, our_player_id)
                values (%s, %s, %s, %s, {", ".join(["%s"] * len(PLAYER_PARSED_COLUMNS))}, %s, %s)
                on conflict (api_sports_game_id, player_name, team_name) do update set
                    {", ".join(f"{c} = excluded.{c}" for c in PLAYER_PARSED_COLUMNS)},
                    raw_stats = excluded.raw_stats, our_player_id = excluded.our_player_id
                """,
                (
                    api_sports_game_id, acc["player_id"], player_name, team_name,
                    *[acc.get(c) for c in PLAYER_PARSED_COLUMNS],
                    json.dumps(acc.get("raw_groups", {})), our_player_id,
                ),
            )

    # --- Team stats ---
    home_points = (scores.get("home") or {}).get("total")
    away_points = (scores.get("away") or {}).get("total")
    for team_block in team_stats_response.get("response", []):
        team_name = team_block["team"]["name"]
        is_home = team_name == teams["home"]["name"]
        parsed = parse_team_stats(team_block.get("statistics", {}))
        parsed["points_scored"] = home_points if is_home else away_points
        cur.execute(
            f"""
            insert into api_sports_team_game_stats
                (api_sports_game_id, team_name, is_home, {", ".join(TEAM_PARSED_COLUMNS)}, raw_stats)
            values (%s, %s, %s, {", ".join(["%s"] * len(TEAM_PARSED_COLUMNS))}, %s)
            on conflict (api_sports_game_id, team_name) do update set
                {", ".join(f"{c} = excluded.{c}" for c in TEAM_PARSED_COLUMNS)}, raw_stats = excluded.raw_stats
            """,
            (api_sports_game_id, team_name, is_home, *[parsed.get(c) for c in TEAM_PARSED_COLUMNS], json.dumps(team_block.get("statistics", {}))),
        )

    return matched, unmatched


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute("select name, id from teams")
        team_id_by_name = dict(cur.fetchall())

        seasons = [int(a) for a in sys.argv[1:]] or [2022, 2023, 2024, 2025]
        for season in seasons:
            path = ROOT / f"api_sports_season_{season}_raw.json"
            if not path.exists():
                print(f"Skipping {season}: {path} not found - run scrape_api_sports_season.py first.")
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            total_m, total_u = 0, 0
            for entry in data:
                m, u = import_game(cur, entry, team_id_by_name)
                total_m += m
                total_u += u
            conn.commit()
            print(f"Season {season}: {len(data)} games imported, {total_m} player-rows matched, {total_u} unmatched.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
