-- The engine's real output: one row per (player, gameweek, algorithm
-- version). total_points is the priced expected-points number; rating is
-- the 1-10 absolute-scale view for a given horizon. per_stat and per_layer
-- carry the full breakdown the explainability page reads from - never
-- recomputed client-side.
create table projections (
  id bigint generated always as identity primary key,
  player_id bigint not null references players(id) on delete cascade,
  gameweek integer not null,
  horizon integer not null check (horizon in (1, 2, 3, 5)),
  algorithm_version_id bigint not null references algorithm_versions(id),
  total_points numeric not null,
  rating numeric,
  -- { "passing_yards": {"expected_count": 210, "points": 8.4, ...}, "passing_td": {...}, ... }
  per_stat jsonb not null,
  -- { "lineup_status": 0.95, "form": {"weight": 0.2, "value": 7.1, "populated": true}, "fixture_quantity": {...}, "fixture_quality": {...}, "live_odds": {"populated": false} }
  per_layer jsonb not null,
  data_confidence numeric,
  created_at timestamptz not null default now(),
  unique (player_id, gameweek, horizon, algorithm_version_id)
);

create index on projections (player_id, gameweek);
create index on projections (gameweek, horizon);

alter table projections enable row level security;
create policy "public read" on projections for select using (true);
