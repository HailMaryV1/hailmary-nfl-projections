"""
capture_actuals.py
----------------------
Fills in the real result for every frozen prediction whose gameweek has
now actually been played - the other half of the freeze/capture pair
(freeze_predictions.py freezes the forecast; this fills in what really
happened, as each player's real game completes). Real, direct values
only: `player_stats` already has a genuine per-gameweek row (real
`total_points`) once import_fanteam_stats.py has captured that gameweek -
this just copies it across.

Known, permanent gap for now: `predictions_and_actuals.actual_snap_pct`
(NFL's real playing-time signal, replacing Dream Team's actual_minutes -
see migration 0009's own comment) stays null. FanTeam's real per-player
stats (scripts/import_fanteam_stats.py's STAT_KEY_MAP) don't currently
expose a real snap-percentage figure - this project's "never fabricate a
number" rule means it is never backfilled from a proxy. If a real source
for it is wired in later, this script is where to fill it in.

Fixture gate (ported from the sibling EFL-Projections repo's own real bug
fix): a player_stats row existing for a gameweek does NOT by itself mean
that player's own real game has kicked off - a frozen prediction is only
captured once every real fixture for that player's team in that gameweek
has a `kickoff_at` already in the past.

Idempotent and safe to run as often as the rest of the pipeline - harmless
to re-copy an unchanged real result, and a genuinely later correction is
picked up automatically since this always overwrites with the current
real player_stats value, never skips an already-captured row.

RUN:
    python scripts/capture_actuals.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402

SEASON = "2026"  # must match scripts/import_fanteam_stats.py's own SEASON


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute(
            """
            update predictions_and_actuals pa
            set actual_points = ps.total_points, actual_captured_at = now()
            from player_stats ps
            join players p on p.id = ps.player_id
            where ps.player_id = pa.player_id and ps.gameweek = pa.gameweek and ps.season = %s
              and ps.total_points is not null
              and exists (
                  select 1 from fixtures f
                  where f.gameweek = ps.gameweek and (f.home_team_id = p.team_id or f.away_team_id = p.team_id)
              )
              and not exists (
                  select 1 from fixtures f
                  where f.gameweek = ps.gameweek and (f.home_team_id = p.team_id or f.away_team_id = p.team_id)
                    and f.kickoff_at >= now()
              )
            """,
            (SEASON,),
        )
        captured = cur.rowcount
        conn.commit()

        cur.execute("select count(*) from predictions_and_actuals where actual_points is null")
        still_pending = cur.fetchone()[0]
        print(f"Captured/refreshed {captured} real actual result(s). {still_pending} frozen prediction(s) still awaiting a played gameweek.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
