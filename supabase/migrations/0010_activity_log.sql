-- Generic audit trail: who/what changed, when, before/after. Every settings
-- save (Phase 4) writes here, as does the import pipeline's external_id-
-- reissue handling and any debounced team-change promotion.
create table activity_log (
  id bigint generated always as identity primary key,
  event_type text not null,
  actor text,
  details jsonb,
  created_at timestamptz not null default now()
);

create index on activity_log (event_type, created_at desc);

alter table activity_log enable row level security;
create policy "public read" on activity_log for select using (true);
