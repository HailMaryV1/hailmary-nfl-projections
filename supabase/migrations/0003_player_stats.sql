-- Per-player, per-gameweek real stats. Columns cover every stat this
-- tournament's real scoring rules (migration 0005) price directly for
-- offensive players; the defense_special columns are only ever populated
-- for that unit's own rows (one row per real team per gameweek, not per
-- individual defender - FanTeam scores defense/special teams as a single
-- unit). Anything not priced directly lives in raw_stats, same discipline
-- as Dream Team's player_stats.
create table player_stats (
  id bigint generated always as identity primary key,
  player_id bigint not null references players(id) on delete cascade,
  season text not null default '2026',
  gameweek integer,

  -- Offense
  passing_attempts integer,
  passing_completions integer,
  passing_yards integer,
  passing_tds integer,
  interceptions_thrown integer,
  rushing_attempts integer,
  rushing_yards integer,
  rushing_tds integer,
  receptions integer,
  receiving_yards integer,
  receiving_tds integer,
  return_tds integer,
  fumbles_lost integer,
  two_point_conversions integer,

  -- Defense/Special Teams unit (defense_special position rows only)
  sacks numeric,
  def_interceptions integer,
  fumble_recoveries integer,
  safeties integer,
  blocked_kicks integer,
  def_special_tds integer,
  points_allowed integer,

  total_points numeric,
  raw_stats jsonb,
  created_at timestamptz not null default now(),
  unique (player_id, season, gameweek)
);

create index on player_stats (player_id, season);

alter table player_stats enable row level security;
create policy "public read" on player_stats for select using (true);
