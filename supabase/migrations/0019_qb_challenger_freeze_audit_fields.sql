-- Audit fields so each frozen qb_challenger_freeze row can be fully
-- reconstructed after the fact - why a challenger variant differed from
-- V1, not just what the final numbers were. Added before any real GW2
-- freeze has been taken (table was empty at the time of this migration -
-- a premature test freeze was deleted, see qb_challenger_freeze.py).
--
-- turnover_participation_status/multiplier is a SEPARATE concept from the
-- existing role_status_used/role_multiplier: the latter describes the
-- no-history opportunity PRODUCTION fallback (established in migration
-- 0018, only meaningful when n_prior_games = 0); the former gates the
-- TURNOVER calculation's expected pass/rush volume for EVERY QB
-- (established veterans included), fixing a real bug where an
-- established player V1 didn't expect to play could still accrue a real
-- historical-average turnover penalty against a near-zero V1 baseline.
alter table qb_challenger_freeze
    add column v1_data_confidence numeric,
    add column int_rate numeric,
    add column int_adjustment numeric,
    add column fumble_adjustment numeric,
    add column opportunity_adjustment numeric,
    add column turnover_participation_status text,
    add column turnover_participation_multiplier numeric;
