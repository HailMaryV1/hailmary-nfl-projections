"""
import_rotowire_lineups.py
-----------------------------
Loads scrape_rotowire_lineups.py's raw JSON into player_lineup_status,
game_odds and fixture_weather.

Real per-player status codes observed live on RotoWire's own page (empty =
no designation = starting normally, "Q" = questionable) - mapped to our
schema's vocabulary. An unrecognised code is logged and defaults to
'questionable' rather than crashing the run (a genuinely new real code is
worth a follow-up fix, not a reason to lose the rest of the batch).

Fixture matching: RotoWire gives no explicit calendar date (just a day
abbreviation + kickoff time with no year/month), so matching is done on the
real (home_abbr, away_abbr) team pair against our fixtures table (already
populated with real kickoff timestamps from FanTeam) - picking whichever
matching, not-yet-kicked-off fixture is soonest. Player matching uses the
real full name RotoWire provides via each link's title attribute (e.g.
"Rhamondre Stevenson", not the abbreviated "R. Stevenson" shown on the
page), scoped to the two real teams in that fixture.

RUN:
    python scripts/import_rotowire_lineups.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import ROOT, db_connect  # noqa: E402
from name_matching import resolve_player_id  # noqa: E402

STATUS_MAP = {
    "": "starter",
    "Q": "questionable",
    "D": "doubtful",
    "O": "inactive",
    "IR": "inactive",
    "PUP": "inactive",
}

SPREAD_RE = re.compile(r"^([A-Z]{2,4})\s*([+-]?\d+\.?\d*)$")
LINE_RE = re.compile(r"^([A-Z]{2,4})\s+([+-]?\d+)$")
WEATHER_RE = re.compile(r"(\d+)\s*°.*?([\d.]+)\s*mph", re.DOTALL)


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


def record_players(cur, entries, fixture_id, team_id, force_status=None):
    recorded, unmatched = 0, 0
    for entry in entries:
        if entry.get("placeholder"):
            continue
        name = entry.get("title") or entry.get("name")
        if not name:
            continue
        player_id = resolve_player_id(cur, name, [team_id])
        if player_id is None:
            unmatched += 1
            if entry.get("pos") != "K":
                print(f"    [unmatched name] {name!r} ({entry.get('pos')})")
            continue
        status = force_status or STATUS_MAP.get(entry.get("statusText", ""), None)
        if status is None:
            print(f"  [unrecognised status] {name!r}: {entry.get('statusText')!r} - defaulting to questionable")
            status = "questionable"
        cur.execute(
            "insert into player_lineup_status (player_id, fixture_id, status, source) values (%s, %s, %s, %s)",
            (player_id, fixture_id, status, "rotowire"),
        )
        recorded += 1
    return recorded, unmatched


def parse_spread(value, home_abbr, away_abbr):
    m = SPREAD_RE.match(value)
    if not m:
        return None
    team, num = m.group(1), float(m.group(2))
    if team == home_abbr:
        return num
    if team == away_abbr:
        return -num
    return None


def parse_moneyline(value, home_abbr, away_abbr):
    m = LINE_RE.match(value)
    if not m:
        return None, None
    team, num = m.group(1), int(m.group(2))
    if team == home_abbr:
        return num, None
    if team == away_abbr:
        return None, num
    return None, None


def import_game(cur, game):
    home_abbr, away_abbr = game["abbrHome"], game["abbrVisit"]
    fixture_row = find_fixture(cur, home_abbr, away_abbr)
    if fixture_row is None:
        print(f"  [unmatched fixture] {away_abbr} @ {home_abbr} - no upcoming fixture found")
        return None

    fixture_id, home_team_id, away_team_id = fixture_row

    recorded = unmatched = 0
    r, u = record_players(cur, game["startersHome"], fixture_id, home_team_id)
    recorded += r
    unmatched += u
    r, u = record_players(cur, game["startersVisit"], fixture_id, away_team_id)
    recorded += r
    unmatched += u
    r, u = record_players(cur, game["inactivesHome"], fixture_id, home_team_id, force_status="inactive")
    recorded += r
    unmatched += u
    r, u = record_players(cur, game["inactivesVisit"], fixture_id, away_team_id, force_status="inactive")
    recorded += r
    unmatched += u

    home_spread = away_spread = home_ml = away_ml = total_ou = None
    for item in game.get("oddsItems", []):
        label, value = item.get("label"), item.get("value", "")
        if label == "SPREAD":
            home_spread = parse_spread(value, home_abbr, away_abbr)
        elif label == "LINE":
            home_ml, away_ml = parse_moneyline(value, home_abbr, away_abbr)
        elif label == "O/U":
            try:
                total_ou = float(value)
            except ValueError:
                total_ou = None

    if any(v is not None for v in (home_spread, home_ml, away_ml, total_ou)):
        cur.execute(
            """
            insert into game_odds (fixture_id, home_spread, home_moneyline, away_moneyline, total_points_over_under, source)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (fixture_id, home_spread, home_ml, away_ml, total_ou, "rotowire"),
        )

    is_dome = game.get("isDome", False)
    temperature_f = wind_mph = precipitation_pct = None
    if not is_dome and game.get("weatherFullText"):
        m = WEATHER_RE.search(game["weatherFullText"])
        if m:
            temperature_f, wind_mph = float(m.group(1)), float(m.group(2))
        if game.get("weatherBold", "").endswith("%"):
            try:
                precipitation_pct = float(game["weatherBold"].rstrip("%"))
            except ValueError:
                precipitation_pct = None

    cur.execute(
        """
        insert into fixture_weather (fixture_id, temperature_f, wind_mph, precipitation_pct, is_dome, source)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (fixture_id, temperature_f, wind_mph, precipitation_pct, is_dome, "rotowire"),
    )

    print(f"  {away_abbr} @ {home_abbr}: {recorded} lineup rows recorded, {unmatched} unmatched names")
    return recorded


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        games = json.loads((ROOT / "rotowire_lineups_raw.json").read_text(encoding="utf-8"))
        for game in games:
            import_game(cur, game)
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
