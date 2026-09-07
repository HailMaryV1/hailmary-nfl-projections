"""
import_fanteam.py
-------------------
Loads scrape_fanteam.py's raw JSON into fixtures, players and
player_lineup_status.

Unlike Dream Team's importer, this one does NOT need the surname-matching
cascade in name_matching.py: FanTeam/ScoutGG's realPlayerId is confirmed
live (2026-09-07) to be a stable per-person key across gameweeks (unlike
the endpoint's own composite per-row `id`), so every player is matched
directly on external_id = str(realPlayerId). Real fixtures are matched the
same way on external_id = str(realMatchId).

Real, confirmed home/away convention (cross-checked against RotoWire's own
"Away @ Home" listing for every Week 1 game, 2026-09-07): realMatches[].
realTeamIds is [home_team_fanteam_id, away_team_fanteam_id].

RUN:
    python scripts/import_fanteam.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg2.errors

sys.path.insert(0, str(Path(__file__).resolve().parent))
from activity_log import log_event  # noqa: E402
from env_utils import ROOT, db_connect  # noqa: E402

TEAM_CHANGE_COOLDOWN = timedelta(hours=24)


def build_fanteam_team_map(cur, real_teams):
    """fanteam_team_id -> our teams.id, matched on abbr - confirmed
    identical codes (ARI, SEA, NE, ...) between FanTeam's realTeams and our
    seeded teams.abbr. A genuinely unmatched abbr is reported, never
    guessed - the caller skips just the affected fixtures/players."""
    cur.execute("select id, abbr from teams")
    team_id_by_abbr = {abbr: tid for tid, abbr in cur.fetchall()}
    mapping = {}
    unmatched = []
    for t in real_teams:
        our_id = team_id_by_abbr.get(t["abbr"])
        if our_id is None:
            unmatched.append(t["abbr"])
        else:
            mapping[t["id"]] = our_id
    if unmatched:
        print(f"  [unmatched team abbr] {sorted(set(unmatched))} - not in our seeded 32 teams, check scripts/seed_teams.py")
    return mapping


def import_fixtures(cur, real_matches, team_map):
    imported, skipped = 0, 0
    for m in real_matches:
        team_ids = m.get("realTeamIds") or []
        if len(team_ids) != 2:
            skipped += 1
            continue
        home_id = team_map.get(team_ids[0])
        away_id = team_map.get(team_ids[1])
        if home_id is None or away_id is None:
            skipped += 1
            continue
        cur.execute(
            """
            insert into fixtures (external_id, home_team_id, away_team_id, kickoff_at, gameweek)
            values (%s, %s, %s, %s, %s)
            on conflict (external_id) do update set
                home_team_id = excluded.home_team_id,
                away_team_id = excluded.away_team_id,
                kickoff_at = excluded.kickoff_at,
                gameweek = excluded.gameweek
            """,
            (str(m["id"]), home_id, away_id, m["startTime"], m["gameweek"]),
        )
        imported += 1
    print(f"Fixtures: {imported} upserted, {skipped} skipped (unmatched team).")


def import_players_and_lineups(cur, players_data, team_map, team_name_by_our_id):
    cur.execute("select external_id, id, team_id, price from players where external_id is not null")
    existing = {ext_id: (pid, team_id, price) for ext_id, pid, team_id, price in cur.fetchall()}

    cur.execute(
        "select player_id, max(created_at) as last_changed_at "
        "from activity_log where event_type = 'team_changed' group by player_id"
    )
    last_team_change_by_id = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("select id, pending_team_id from players")
    pending_team_by_id = {pid: pending for pid, pending in cur.fetchall()}

    cur.execute("select external_id, id from fixtures where external_id is not null")
    fixture_id_by_external = {ext_id: fid for ext_id, fid in cur.fetchall()}

    created, updated_team, price_changes, unmatched_team, lineup_rows = 0, 0, 0, 0, 0

    for p in players_data:
        external_id = str(p["realPlayerId"])
        live_team_id = team_map.get(p["realTeamId"])
        if live_team_id is None:
            unmatched_team += 1
            continue

        real_player = p["realPlayer"]
        if p["position"] == "defense_special":
            full_name = f"{team_name_by_our_id.get(live_team_id, '?')} D/ST"
        else:
            full_name = f"{real_player.get('firstName') or ''} {real_player.get('lastName') or ''}".strip()

        row = existing.get(external_id)
        if row is None:
            cur.execute(
                """
                insert into players (external_id, full_name, team_id, position, price, is_active)
                values (%s, %s, %s, %s, %s, %s)
                returning id
                """,
                (external_id, full_name, live_team_id, p["position"], p["price"], p["active"]),
            )
            player_id = cur.fetchone()[0]
            created += 1
            log_event(cur, "player_added", f"{full_name} added as a new player ({p['position']})", player_id=player_id)
        else:
            player_id, canonical_team_id, old_price = row
            if canonical_team_id != live_team_id:
                debounce_confirmed = pending_team_by_id.get(player_id) == live_team_id
                last_changed_at = last_team_change_by_id.get(player_id)
                in_cooldown = last_changed_at is not None and datetime.now(timezone.utc) - last_changed_at < TEAM_CHANGE_COOLDOWN
                if debounce_confirmed and not in_cooldown:
                    cur.execute(
                        "update players set team_id = %s, pending_team_id = null, pending_team_seen_at = null where id = %s",
                        (live_team_id, player_id),
                    )
                    updated_team += 1
                    log_event(
                        cur, "team_changed",
                        f"{full_name} moved to {team_name_by_our_id.get(live_team_id, '?')}",
                        player_id=player_id,
                        details={"old_team_id": canonical_team_id, "new_team_id": live_team_id},
                    )
                else:
                    cur.execute(
                        "update players set pending_team_id = %s, pending_team_seen_at = now() where id = %s",
                        (live_team_id, player_id),
                    )
            elif pending_team_by_id.get(player_id) is not None:
                cur.execute("update players set pending_team_id = null, pending_team_seen_at = null where id = %s", (player_id,))

            cur.execute(
                "update players set full_name = %s, position = %s, price = %s, is_active = %s, updated_at = now() where id = %s",
                (full_name, p["position"], p["price"], p["active"], player_id),
            )
            if old_price is not None and float(old_price) != float(p["price"]):
                direction = "risen" if float(p["price"]) > float(old_price) else "fallen"
                price_changes += 1
                log_event(
                    cur, "price_changed", f"{full_name} has {direction} to £{p['price']}m (was £{old_price}m)",
                    player_id=player_id, details={"old_price": float(old_price), "new_price": float(p["price"])},
                )

        fixture_id = fixture_id_by_external.get(str(p["realMatchId"]))
        if fixture_id is not None:
            cur.execute(
                "insert into player_lineup_status (player_id, fixture_id, status, source) values (%s, %s, %s, %s)",
                (player_id, fixture_id, p["lineup"], "fanteam"),
            )
            lineup_rows += 1

    print(
        f"Players: {created} new, {updated_team} team changes, {price_changes} price changes, "
        f"{unmatched_team} skipped (unmatched team). {lineup_rows} lineup_status rows recorded."
    )


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        data = json.loads((ROOT / "fanteam_raw.json").read_text(encoding="utf-8"))
        team_map = build_fanteam_team_map(cur, data["realTeams"])

        cur.execute("select id, name from teams")
        team_name_by_our_id = {tid: name for tid, name in cur.fetchall()}

        import_fixtures(cur, data["realMatches"], team_map)
        import_players_and_lineups(cur, data["playerChoices"], team_map, team_name_by_our_id)

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
