-- Lets a customer look up their real FanTeam entry by id/URL and see it
-- rendered with Hail Mary's own real projections/fixtures/stats on top.
-- One linked entry per customer for v1 - re-connecting replaces it.
--
-- Real, inherent limitation (not a bug): FanTeam's own public dashboards
-- have no ownership check at all (confirmed live - any entry's full
-- roster renders in a never-authenticated browser tab by id alone), and
-- FanTeam gives us no OAuth to prove an entry belongs to whoever pastes it
-- in here. This table just remembers which public entry id a customer
-- asked us to look up, same trust model as pasting a public profile link.
create table user_fanteam_teams (
  id bigint generated always as identity primary key,
  user_id uuid not null unique references auth.users(id) on delete cascade,
  fanteam_entry_id bigint not null,
  team_name text,
  connected_at timestamptz not null default now()
);

alter table user_fanteam_teams enable row level security;

-- Same per-user-owns-their-own-row pattern as custom_pools (migration 0013).
create policy "own fanteam team" on user_fanteam_teams for all
  to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
