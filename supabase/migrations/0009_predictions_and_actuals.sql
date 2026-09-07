-- Frozen per-gameweek prediction snapshot (what the engine said BEFORE
-- kickoff) plus the real actual result once played. Frozen separately from
-- `projections` (which keeps getting overwritten right up to kickoff) so
-- grading is always against what was actually shown to a user.
--
-- actual_snap_pct replaces Dream Team's actual_minutes - NFL's real
-- equivalent playing-time signal is offensive/defensive snap percentage,
-- not minutes on a clock.
create table predictions_and_actuals (
  id bigint generated always as identity primary key,
  player_id bigint not null references players(id) on delete cascade,
  gameweek integer not null,
  predicted_points numeric not null,
  predicted_rating numeric,
  frozen_at timestamptz not null default now(),
  actual_points numeric,
  actual_snap_pct numeric,
  actual_captured_at timestamptz,
  unique (player_id, gameweek)
);

create index on predictions_and_actuals (gameweek);

alter table predictions_and_actuals enable row level security;
create policy "public read" on predictions_and_actuals for select using (true);
