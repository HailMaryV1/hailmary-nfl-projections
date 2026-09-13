-- Real single-week injury-swap overrides for a user's own custom
-- playbook. Deliberately NOT a change to custom_pool_players or
-- custom_playbooks - a real injury this week shouldn't rewrite the
-- user's saved 28-player pool or reshuffle any other week's plan (both
-- of those already have a real recompute-the-whole-season write path via
-- buildPool() in app/(site)/playbook/builder/actions.ts; this is a
-- narrower, additive override applied only when rendering one specific
-- (gameweek, slot) on top of the saved plan). One row per slot per real
-- gameweek - a later swap for the same slot/week replaces the row
-- (upsert), a revert deletes it outright.
create table custom_playbook_overrides (
  id bigint generated always as identity primary key,
  pool_id bigint not null references custom_pools(id) on delete cascade,
  gameweek integer not null,
  slot text not null,
  player_id bigint not null references players(id),
  reason text,
  created_at timestamptz not null default now(),
  unique (pool_id, gameweek, slot)
);
create index on custom_playbook_overrides (pool_id, gameweek);

alter table custom_playbook_overrides enable row level security;

-- Same real-ownership-via-auth.uid() pattern as custom_pools/
-- custom_pool_players/custom_playbooks (migration 0013) - this is a real
-- person's own in-season edit, not a shared setting.
create policy "own playbook overrides" on custom_playbook_overrides for all
  to authenticated using (
    exists (select 1 from custom_pools p where p.id = pool_id and p.user_id = auth.uid())
  ) with check (
    exists (select 1 from custom_pools p where p.id = pool_id and p.user_id = auth.uid())
  );
