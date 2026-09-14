-- Explicitly records WHICH live V1 model version backed each frozen QB
-- challenger row's baseline, so a later comparison can never accidentally
-- imply GW1 and a subsequent gameweek shared the same underlying V1 model
-- (e.g. once the Form layer goes live, V1 itself changes, independent of
-- and before any QB/opportunity challenger work) - see
-- scripts/qb_challenger_freeze.py and compute_projections.py's
-- MODEL_CODE_VERSION for how this is populated.
alter table qb_challenger_freeze
    add column v1_algorithm_version_id bigint references algorithm_versions(id),
    add column v1_algorithm_note text;
