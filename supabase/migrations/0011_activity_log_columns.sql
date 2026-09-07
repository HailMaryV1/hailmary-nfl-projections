-- Enrich activity_log with real, indexed columns rather than cramming
-- everything into `details` jsonb - same shape as Dream Team's equivalent
-- migration.
alter table activity_log add column summary text;
alter table activity_log add column player_id bigint references players(id);
alter table activity_log add column fixture_id bigint references fixtures(id);

create index on activity_log (player_id);
