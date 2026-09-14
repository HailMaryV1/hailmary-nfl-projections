-- Permanent raw + parsed historical dataset from API-Sports NFL, for
-- diagnosing real projection errors at the opportunity-stat level (targets,
-- attempts, etc.) - a real second source, independent of FanTeam, with a
-- richer real per-game box score than FanTeam's own sparse stats export.
--
-- Both raw and parsed are stored together, deliberately: `raw_response`/
-- `raw_stats` keep the exact real API payload verbatim, so a parsing bug
-- found later can be fixed by re-deriving from the real source already
-- sitting in the database, without needing to re-call the API (which is
-- rate-limited and reflects a point in time - the actual API response for
-- a past game is itself an artifact worth preserving as-is).

create table api_sports_games (
  id bigint generated always as identity primary key,
  api_sports_game_id bigint not null unique,
  season integer not null,
  week text not null,
  stage text not null,
  home_team_name text not null,
  away_team_name text not null,
  status_short text not null,
  kickoff_at timestamptz,
  -- Our own real fixture this game corresponds to, once matched - nullable
  -- since matching happens as a separate, explicit step, never assumed.
  our_fixture_id bigint references fixtures(id),
  raw_response jsonb not null,
  fetched_at timestamptz not null default now()
);

create index on api_sports_games (season, week);

create table api_sports_player_game_stats (
  id bigint generated always as identity primary key,
  api_sports_game_id bigint not null references api_sports_games(id) on delete cascade,
  api_sports_player_id bigint,
  player_name text not null,
  team_name text not null,

  -- Parsed real box-score fields - see scripts/import_api_sports_gw1.py
  -- for the exact real API-Sports field names each of these comes from
  -- (several are combined strings there, e.g. "21/39", split here).
  pass_attempts integer,
  pass_completions integer,
  pass_yards integer,
  pass_td integer,
  interceptions_thrown integer,
  sacks_taken integer,
  rush_attempts integer,
  rush_yards integer,
  rush_td integer,
  targets integer,
  receptions integer,
  receiving_yards integer,
  receiving_td integer,
  fumbles_total integer,
  fumbles_lost integer,

  -- The real, unparsed group->stats blob(s) for this player in this game
  -- (Passing/Rushing/Receiving/Fumbles groups, whichever real ones they
  -- appeared in) - kept verbatim regardless of parsing above.
  raw_stats jsonb not null,

  -- Our own player, once matched (name + real team scoping, same
  -- convention as scripts/import_rotowire_lineups.py's cross-source
  -- matching) - nullable, never assumed.
  our_player_id bigint references players(id),

  fetched_at timestamptz not null default now(),
  unique (api_sports_game_id, player_name, team_name)
);

create index on api_sports_player_game_stats (our_player_id);

alter table api_sports_games enable row level security;
alter table api_sports_player_game_stats enable row level security;
create policy "public read" on api_sports_games for select using (true);
create policy "public read" on api_sports_player_game_stats for select using (true);
