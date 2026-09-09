-- Real user-built playbooks: pick a 28-player pool across real price
-- tiers (2 premium/2 under-17m QB, 4/2/2 premium/mid/value RB and WR,
-- 1/2/1 premium/mid/value TE, any 4 DST), then compute the same real
-- 18-week rotation strategy the two built-in playbooks use, restricted to
-- just that pool. The tier structure isn't cosmetic - the real worst-case
-- floor (every mandatory-cheap-tier player used at once) comes to
-- roughly £70m against the real £140M cap, so a legal squad always
-- exists no matter how the premium tier is spent (see the design
-- discussion this migration came out of - no separate doc, the numbers
-- are re-derivable from real horizon-1 prices any time).
--
-- Scoped per real Supabase Auth account from day one - today that's just
-- the site owner, but built so a real second account never needs a
-- schema change to stay private to its own owner.

create table custom_pools (
  id bigint generated always as identity primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null default 'My Pool',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table custom_pool_players (
  id bigint generated always as identity primary key,
  pool_id bigint not null references custom_pools(id) on delete cascade,
  player_id bigint not null references players(id),
  position text not null check (position in (
    'quarterback', 'running_back', 'wide_receiver', 'tight_end', 'defense_special'
  )),
  tier text not null check (tier in ('premium', 'mid', 'value', 'any')),
  unique (pool_id, player_id)
);
create index on custom_pool_players (pool_id);

create table custom_playbooks (
  id bigint generated always as identity primary key,
  pool_id bigint not null references custom_pools(id) on delete cascade,
  algorithm_version_id bigint not null references algorithm_versions(id),
  total_points numeric not null,
  wildcard_gameweek integer,
  extra_transfer_weeks integer[] not null default '{}',
  plan jsonb not null,
  computed_at timestamptz not null default now()
);
create index on custom_playbooks (pool_id, computed_at desc);

alter table custom_pools enable row level security;
alter table custom_pool_players enable row level security;
alter table custom_playbooks enable row level security;

-- Every policy checks real ownership via auth.uid(), not just "any
-- authenticated user" (unlike scoring_rules/layer_weights's single-admin
-- "admin write" policy) - this data is a real person's own pool, not a
-- shared setting.
create policy "own pools" on custom_pools for all
  to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "own pool players" on custom_pool_players for all
  to authenticated using (
    exists (select 1 from custom_pools p where p.id = pool_id and p.user_id = auth.uid())
  ) with check (
    exists (select 1 from custom_pools p where p.id = pool_id and p.user_id = auth.uid())
  );

create policy "own playbooks" on custom_playbooks for all
  to authenticated using (
    exists (select 1 from custom_pools p where p.id = pool_id and p.user_id = auth.uid())
  ) with check (
    exists (select 1 from custom_pools p where p.id = pool_id and p.user_id = auth.uid())
  );
