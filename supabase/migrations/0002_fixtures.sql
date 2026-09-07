-- Real NFL regular-season fixtures. Simpler than Dream Team's fixtures
-- table - one competition only (no cup/European equivalents), so no
-- `competition` column. A team with no fixture row for a given gameweek IS
-- a real bye week - the Fixture Quantity layer reads that as zero games
-- that week the same way Dream Team reads an absent fixture as a blank,
-- no separate bye_weeks table needed.
create table fixtures (
  id bigint generated always as identity primary key,
  external_id text unique,
  home_team_id bigint not null references teams(id),
  away_team_id bigint not null references teams(id),
  kickoff_at timestamptz not null,
  gameweek integer not null check (gameweek between 1 and 18),
  created_at timestamptz not null default now()
);

create index on fixtures (gameweek);
create index on fixtures (kickoff_at);

-- Real per-fixture weather - a genuinely NFL-specific signal with no Dream
-- Team equivalent (outdoor stadiums suppress passing volume; dome games get
-- no adjustment). Append-only/time-series like the market-odds tables below
-- - a forecast gets more accurate as kickoff approaches, so each capture is
-- its own row rather than an overwrite.
create table fixture_weather (
  id bigint generated always as identity primary key,
  fixture_id bigint not null references fixtures(id) on delete cascade,
  temperature_f numeric,
  wind_mph numeric,
  precipitation_pct numeric,
  is_dome boolean not null default false,
  source text not null,
  captured_at timestamptz not null default now()
);

create index on fixture_weather (fixture_id, captured_at desc);

alter table fixtures enable row level security;
alter table fixture_weather enable row level security;
create policy "public read" on fixtures for select using (true);
create policy "public read" on fixture_weather for select using (true);
