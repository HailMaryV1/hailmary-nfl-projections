-- Real full-season (18-week) matchup + difficulty data from Sharp Football
-- Analysis's Strength of Schedule tool - confirmed live 2026-09-08. Kept
-- deliberately separate from `fixtures`: that table's real contract is
-- precise kickoff logistics (exact date/time, matched against RotoWire/
-- Spreadex), which this source doesn't provide (only a week number and
-- opponent) - representing it as a `fixtures` row would mean inventing a
-- kickoff_at this project doesn't actually have. This table instead
-- answers "who does this team play in week N, and how hard is it" for
-- every week of the season, independent of exact scheduling - exactly
-- what multi-week horizons and a real offense Fixture Quality signal need.
create table team_schedule_difficulty (
  id bigint generated always as identity primary key,
  team_id bigint not null references teams(id),
  gameweek integer not null check (gameweek between 1 and 18),
  -- Both null on a real bye week - never guessed.
  opponent_team_id bigint references teams(id),
  is_home boolean,
  is_bye boolean not null default false,
  -- Sharp Football Analysis's own real metric: the opponent's 2026 Vegas-
  -- projected win total, a legitimate market-derived Fixture Quality
  -- signal (higher = tougher opponent) - not this project's own estimate.
  opponent_win_total numeric,
  source text not null,
  captured_at timestamptz not null default now(),
  unique (team_id, gameweek, source)
);

create index on team_schedule_difficulty (team_id, gameweek);

alter table team_schedule_difficulty enable row level security;
create policy "public read" on team_schedule_difficulty for select using (true);
