-- Real per-game TEAM box-score stats from API-Sports, same raw+parsed
-- discipline as migration 0016's player table - permanent historical data
-- for building real offensive-volume and D/ST features, not a live
-- pipeline input yet.
create table api_sports_team_game_stats (
  id bigint generated always as identity primary key,
  api_sports_game_id bigint not null references api_sports_games(id) on delete cascade,
  team_name text not null,
  is_home boolean not null,
  offensive_plays integer,
  total_yards integer,
  pass_attempts integer,
  pass_completions integer,
  pass_yards integer,
  rush_attempts integer,
  rush_yards integer,
  interceptions_thrown integer,
  points_scored integer,
  points_against integer,
  -- Real defense/special-teams unit stats for this team.
  sacks integer,
  def_interceptions integer,
  fumbles_recovered integer,
  safeties integer,
  int_touchdowns integer,
  raw_stats jsonb not null,
  fetched_at timestamptz not null default now(),
  unique (api_sports_game_id, team_name)
);

create index on api_sports_team_game_stats (team_name);

alter table api_sports_team_game_stats enable row level security;
create policy "public read" on api_sports_team_game_stats for select using (true);
