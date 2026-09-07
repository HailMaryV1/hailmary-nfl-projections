# Data and weights - build log

Real-incident log for this project, same discipline as Dream Team
Projections' equivalent doc. Each entry is a real thing that happened, not a
hypothetical.

## 2026-09-07 - Phase 0: repo scaffolding, DB wired

- New GitHub repo `HailMaryV1/hailmary-nfl-projections`, new Supabase
  project `hailmary-nfl-projections` (ref `bfwcmwouaavefjfzgetv`, region
  eu-central-1), no shared infra with any other Hail Mary game.
- Confirmed real DB connectivity via the pooler connection string
  (`aws-0-eu-central-1.pooler.supabase.com:5432`) - `select version()`
  returned PostgreSQL 17.6.
- Confirmed three real data sources before writing any ingestion code (see
  CLAUDE.md for full detail): FanTeam/ScoutGG API (unauthenticated,
  players+fixtures+teams+config in one call), Spreadex (real NFL match
  odds + "Weekly Player Markets" player props), RotoWire lineups (real
  Starter/Inactive/Questionable + weather, but Cloudflare-protected -
  needs a real browser, modest scrape cadence).
- Received `SUPABASE_SERVICE_ROLE_KEY` from the user - `.env` fully populated.

## 2026-09-07 - Phase 1: database schema, real teams seeded

- 10 migrations applied cleanly against the live DB: teams/players,
  fixtures + weather, player_stats, market odds + lineup status,
  scoring_rules (25 real rows: 11 offense + 14 defense_special, incl. the
  points-allowed tiers as discrete rows), layer_weights (80 rows: 4
  horizons x 5 positions x 4 layers), algorithm_versions, projections,
  predictions_and_actuals, activity_log.
- Real design departures from Dream Team's schema, each for a real reason:
  - No `competition` column on `fixtures` - one competition only. A team
    with no fixture row for a gameweek IS a real bye week; no separate
    bye_weeks table needed (same "absence = blank" logic Dream Team uses).
  - New `fixture_weather` table - wind/precipitation/dome, no Dream Team
    equivalent, sourced from RotoWire.
  - New `game_odds` table for real spread/moneyline/total - Spreadex and
    RotoWire both carry this, kept distinguishable by `source`.
  - `player_lineup_status.status` covers both real sources' own vocab
    (RotoWire's starter/questionable/doubtful/inactive, FanTeam's
    expected/injured/possible/refuted/unexpected) rather than inventing one
    scale - same discipline as Dream Team using Spreadex's real vocab as-is.
  - `predictions_and_actuals.actual_snap_pct` replaces Dream Team's
    `actual_minutes` - NFL's real playing-time signal is snap percentage,
    not a running clock.
  - `player_stats` carries defense_special's unit-level stats (sacks,
    interceptions, points_allowed, etc.) as columns on the SAME table as
    offensive per-player stats - one row per real team's D/ST per gameweek,
    not per individual defender, since FanTeam scores D/ST as a single unit.
- Seeded all 32 real NFL teams (`scripts/seed_teams.py`) - abbreviations
  confirmed by direct observation against RotoWire's real Week 1 lineups
  page, not guessed.
