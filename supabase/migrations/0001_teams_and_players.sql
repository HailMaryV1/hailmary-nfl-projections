-- Core identity tables: the 32 real NFL teams and players (one row per real
-- person, FanTeam's own realPlayerId as the live-sync key). Single-game
-- simplification, same as Dream Team Projections' equivalent migration:
-- FanTeam's position and price live directly on `players`.

create table teams (
  id bigint generated always as identity primary key,
  name text not null unique,
  abbr text not null unique,
  conference text not null check (conference in ('AFC', 'NFC')),
  division text not null check (division in ('East', 'North', 'South', 'West')),
  created_at timestamptz not null default now()
);

-- Real display-name variants an ingestion script might see for a team
-- across FanTeam / Spreadex / RotoWire (each names/abbreviates teams
-- slightly differently - e.g. RotoWire's "NE" vs FanTeam's full name),
-- mapped to the canonical teams.name. Same purpose as Dream Team's
-- team_aliases table.
create table team_aliases (
  id bigint generated always as identity primary key,
  team_id bigint not null references teams(id),
  alias text not null unique,
  created_at timestamptz not null default now()
);

create table players (
  id bigint generated always as identity primary key,
  -- FanTeam/ScoutGG's realPlayerId - stable across gameweeks, unlike the
  -- players endpoint's own composite per-row `id` (which is per-gameweek).
  external_id text unique,
  full_name text not null,
  team_id bigint references teams(id),
  -- Debounced team-change handling (a mid-season trade), same pattern
  -- ported from Dream Team's import_dreamteam.py: a name-matched player
  -- whose team_id looks stale gets the new team_id written here first,
  -- promoted to the real team_id only once seen again on a second,
  -- separate import run.
  pending_team_id bigint references teams(id),
  pending_team_seen_at timestamptz,
  -- Real FanTeam position vocabulary, confirmed live against tournament
  -- 1136503's own config (safetyNetPositions) - no separate Kicker
  -- position exists in this ruleset.
  position text check (position in (
    'quarterback', 'running_back', 'wide_receiver', 'tight_end', 'defense_special'
  )),
  price numeric,
  ownership_pct numeric,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index on players (team_id);
create index on players (is_active);

alter table teams enable row level security;
alter table team_aliases enable row level security;
alter table players enable row level security;

create policy "public read" on teams for select using (true);
create policy "public read" on team_aliases for select using (true);
create policy "public read" on players for select using (true);
