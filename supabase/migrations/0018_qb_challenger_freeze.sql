-- Frozen, immutable snapshot of the 4 QB challenger variants
-- (QB-V1 / QB-V1+INT / QB-V1+Opportunity / QB-Hybrid) for a real upcoming
-- gameweek, taken BEFORE kickoff so the later comparison against settled
-- actuals is a genuine prospective test - see scripts/qb_challenger_freeze.py.
-- One row per (player, gameweek), never updated once written.
create table qb_challenger_freeze (
    id bigint generated always as identity primary key,
    player_id bigint not null references players(id),
    gameweek integer not null,
    frozen_at timestamptz not null default now(),
    qb_v1_points numeric not null,
    qb_v1_int_points numeric not null,
    qb_v1_opportunity_points numeric not null,
    qb_hybrid_points numeric not null,
    expected_interceptions numeric,
    expected_fumbles_lost numeric,
    expected_pass_attempts numeric,
    expected_rush_attempts numeric,
    n_prior_games integer not null,
    role_status_used text,
    role_multiplier numeric,
    unique (player_id, gameweek)
);
alter table qb_challenger_freeze enable row level security;
create policy "public read" on qb_challenger_freeze for select using (true);
