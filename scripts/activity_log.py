"""
activity_log.py
------------------
One shared helper for writing to the activity_log table (migration 0010,
enriched 0011) - used by every import/compute script at the exact point it
detects a new player, a team change, an external_id reissue, etc.

Ported verbatim from dreamteam-projections/scripts/activity_log.py.

Not a standalone script - imported, no RUN section.
"""

import json


def log_event(cur, event_type, summary, *, actor=None, player_id=None, fixture_id=None, details=None):
    cur.execute(
        """
        insert into activity_log (event_type, actor, player_id, fixture_id, summary, details)
        values (%s, %s, %s, %s, %s, %s)
        """,
        (event_type, actor, player_id, fixture_id, summary, json.dumps(details or {}, default=str)),
    )
