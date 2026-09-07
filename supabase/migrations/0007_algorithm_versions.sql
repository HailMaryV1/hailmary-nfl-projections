-- Versioned snapshot of the full weight configuration (layer_weights +
-- scoring_rules) every time either changes, so a past projection stays
-- attributable to the exact weights that produced it. Ported concept from
-- Dream Team Projections' equivalent migration.
create table algorithm_versions (
  id bigint generated always as identity primary key,
  revision integer not null,
  weights jsonb not null,
  created_at timestamptz not null default now(),
  created_by text,
  note text,
  unique (revision)
);

alter table algorithm_versions enable row level security;
create policy "public read" on algorithm_versions for select using (true);
create policy "admin write" on algorithm_versions for all to authenticated using (true) with check (true);
