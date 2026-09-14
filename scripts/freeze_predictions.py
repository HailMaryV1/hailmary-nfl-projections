"""
freeze_predictions.py
-------------------------
Snapshots each player's CURRENT gameweek projection (horizon=1 - "this
week's" number) into `predictions_and_actuals`, once, permanently. This is
what turns a gameweek's projection into a real historical record rather
than a moving target: `projections` keeps changing as compute_projections.py
re-runs closer to kickoff with fresher data, but once a gameweek's
projection is frozen here it never changes again - `on conflict (player_id,
gameweek) do nothing`, deliberately no UPDATE branch.

Ported from the sibling EFL-Projections repo's own freeze_predictions.py,
trimmed to this project's real predictions_and_actuals shape (migration
0009): predicted_points/predicted_rating only. `actual_snap_pct` (the
NFL-specific column that replaces Dream Team's actual_minutes) is filled in
later by capture_actuals.py, if a real source for it is ever wired in - see
that script's own docstring.

Safe to run any time, as often as the rest of the pipeline: a player only
ever gets ONE frozen row per gameweek, from whichever run happens to be the
first to see that gameweek as their current horizon=1 projection.

RUN:
    python scripts/freeze_predictions.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from env_utils import db_connect  # noqa: E402


def main():
    conn = db_connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        cur.execute("select max(id) from algorithm_versions")
        latest = cur.fetchone()[0]
        if latest is None:
            print("No algorithm_versions exist yet - run compute_projections.py first.")
            return

        cur.execute(
            """
            insert into predictions_and_actuals (player_id, gameweek, predicted_points, predicted_rating)
            select player_id, gameweek, total_points, rating
            from projections
            where horizon = 1 and algorithm_version_id = %s
            on conflict (player_id, gameweek) do nothing
            """,
            (latest,),
        )
        frozen = cur.rowcount
        conn.commit()
        print(f"Froze {frozen} new (player, gameweek) prediction(s). Already-frozen gameweeks were left untouched.")
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
