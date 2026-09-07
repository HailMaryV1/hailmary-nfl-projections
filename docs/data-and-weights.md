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
- Still needed before Phase 1 (schema): `SUPABASE_SERVICE_ROLE_KEY` (for
  server-side writes bypassing RLS) - `.env` has a `REPLACE_ME` placeholder.
