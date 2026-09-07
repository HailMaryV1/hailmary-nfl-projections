-- FanTeam's real NFL scoring matrix for tournament 1136503 (confirmed
-- against the user's own screenshots of the Offense/Defense rules tabs).
-- Points-allowed is modelled as discrete tiers (each a flat-points row,
-- same shape as every other stat) rather than special-cased in the engine -
-- unlike Dream Team's bonus-points system, this really is a flat lookup:
-- the engine picks exactly one points_allowed_* row per team per gameweek.
create table scoring_rules (
  id bigint generated always as identity primary key,
  applies_to text not null check (applies_to in ('offense', 'defense_special')),
  stat text not null,
  points numeric not null,
  notes text,
  unique (applies_to, stat)
);

insert into scoring_rules (applies_to, stat, points, notes) values
  ('offense', 'passing_yards', 0.04, 'per yard'),
  ('offense', 'rushing_yards', 0.1, 'per yard'),
  ('offense', 'receiving_yards', 0.1, 'per yard'),
  ('offense', 'passing_td', 4, null),
  ('offense', 'rushing_td', 6, null),
  ('offense', 'receiving_td', 6, null),
  ('offense', 'return_td', 6, 'punt/kickoff/FG return TD, individual returner'),
  ('offense', 'interception_thrown', -2, null),
  ('offense', 'reception', 1, 'PPR'),
  ('offense', 'fumble_lost', -2, null),
  ('offense', 'two_point_conversion', 2, null),
  ('defense_special', 'sack', 1, null),
  ('defense_special', 'interception', 2, null),
  ('defense_special', 'fumble_recovery', 2, null),
  ('defense_special', 'safety', 2, null),
  ('defense_special', 'blocked_kick', 2, null),
  ('defense_special', 'defensive_td', 6, 'interception/fumble recovery TD'),
  ('defense_special', 'return_td', 6, 'punt/kickoff/FG return TD, unit credit'),
  ('defense_special', 'points_allowed_0', 10, null),
  ('defense_special', 'points_allowed_1_6', 7, null),
  ('defense_special', 'points_allowed_7_13', 4, null),
  ('defense_special', 'points_allowed_14_20', 1, null),
  ('defense_special', 'points_allowed_21_27', 0, null),
  ('defense_special', 'points_allowed_28_34', -1, null),
  ('defense_special', 'points_allowed_35_plus', -4, null);

alter table scoring_rules enable row level security;
create policy "public read" on scoring_rules for select using (true);
-- Writable by an authenticated admin (Phase 4 settings UI) as well as the
-- service-role pipeline.
create policy "admin write" on scoring_rules for all to authenticated using (true) with check (true);
