-- The tunable core of the model: how much each of the four content layers
-- counts toward a player's rating, per horizon and per position. Same
-- design as Dream Team's equivalent migration - Lineup Status has no weight
-- row here, it GATES the others (a player projected as Inactive doesn't get
-- a smaller share of the other layers' opinion, their whole projection
-- scales down to near-zero). The four content layers renormalize over
-- whichever have real data for a given player right now.
create table layer_weights (
  id bigint generated always as identity primary key,
  horizon integer not null check (horizon in (1, 2, 3, 5)),
  position text not null check (position in (
    'quarterback', 'running_back', 'wide_receiver', 'tight_end', 'defense_special'
  )),
  layer text not null check (layer in ('form', 'fixture_quantity', 'fixture_quality', 'live_odds')),
  weight numeric not null check (weight >= 0 and weight <= 1),
  updated_at timestamptz not null default now(),
  unique (horizon, position, layer)
);

-- Starting weights - same real starting logic as Dream Team's (live odds/
-- form matter most at short horizon, fixture components matter more as the
-- horizon lengthens), kept position-agnostic until real per-position
-- calibration data justifies splitting them.
insert into layer_weights (horizon, position, layer, weight)
select h.horizon, p.position, w.layer, w.weight
from (values (1), (2), (3), (5)) as h(horizon),
     (values ('quarterback'), ('running_back'), ('wide_receiver'), ('tight_end'), ('defense_special')) as p(position),
     (values
        (1, 'live_odds', 0.50), (1, 'form', 0.20), (1, 'fixture_quality', 0.20), (1, 'fixture_quantity', 0.10),
        (2, 'live_odds', 0.30), (2, 'form', 0.20), (2, 'fixture_quality', 0.25), (2, 'fixture_quantity', 0.25),
        (3, 'live_odds', 0.15), (3, 'form', 0.20), (3, 'fixture_quality', 0.30), (3, 'fixture_quantity', 0.35),
        (5, 'live_odds', 0.10), (5, 'form', 0.15), (5, 'fixture_quality', 0.35), (5, 'fixture_quantity', 0.40)
     ) as w(horizon, layer, weight)
where w.horizon = h.horizon;

alter table layer_weights enable row level security;
create policy "public read" on layer_weights for select using (true);
create policy "admin write" on layer_weights for all to authenticated using (true) with check (true);
