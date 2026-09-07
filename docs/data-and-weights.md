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

## 2026-09-07 - Phase 2 (part 1): FanTeam ingestion live

- `scripts/scrape_fanteam.py` + `scripts/import_fanteam.py` - real, working
  end to end. 603 real players, 16 real fixtures, 0 skipped/unmatched.
- Confirmed live: FanTeam/ScoutGG's `realPlayerId` is a stable per-person
  key across gameweeks (unlike the endpoint's own composite per-row `id`),
  so player matching is direct on external_id - no surname-matching
  cascade needed here, unlike Dream Team's importer (which has to cope with
  Dream Team's own id reissues).
  players endpoint's response also carries real fixtures (`realMatches`)
  and teams (`realTeams`) in the SAME call - no separate authenticated
  fixtures request needed, unlike the sibling dreamteam-scraper repo's
  football tournament (which needs a Playwright+bearer-token call for
  fixtures). One theory disproven: assumed this might also be needed here -
  it isn't.
- Confirmed real home/away convention by cross-referencing every one of
  Week 1's 16 real games against RotoWire's own "Away @ Home" listing:
  `realMatches[].realTeamIds` is `[home_team_id, away_team_id]`.
- Defense/Special Teams comes through as one row per real team
  (`position: "defense_special"`, `realPlayer.lastName: "DST"`,
  `firstName: null`) - named "{Team Name} D/ST" at import time rather than
  storing the literal "DST" string.
- `player_lineup_status` gets a row per player per import run from FanTeam's
  own `lineup` field (source `'fanteam'`) - RotoWire will add a second,
  independent observation (source `'rotowire'`) once that scraper is built.

## 2026-09-07 - Phase 2 (part 2): RotoWire ingestion live

- `scripts/scrape_rotowire_lineups.py` (Playwright, real DOM selectors -
  `.lineup.is-nfl` > `.lineup__box`, confirmed live by manual inspection)
  + `scripts/import_rotowire_lineups.py` - real, working end to end. 191
  real lineup_status rows, 16 real game_odds rows, 16 real fixture_weather
  rows from the first live run.
- Fixture matching has no explicit calendar date to key off (RotoWire only
  gives a day abbreviation + time, no year/month) - matched instead on the
  real (home_abbr, away_abbr) team pair against fixtures already populated
  by FanTeam, picking the soonest upcoming match. Real home/away spread
  sign and moneyline side cross-validated correctly against FanTeam's own
  independent home/away assignment (e.g. CAR home +3.0 underdog matches
  CHI away -150 moneyline favorite).
- Real cross-source divergence, exactly the reason two lineup-status
  sources are worth having: Christian McCaffrey showed FanTeam lineup
  `'expected'` but RotoWire `'questionable'` (a real "Q" tag) - RotoWire
  is catching an in-week injury designation FanTeam's own field hadn't
  reflected yet.
- Two real name-matching gaps found and fixed in `scripts/name_matching.py`
  (NFL-specific, added only to this project's own copy of the file, not
  the shared Dream Team original):
  1. FanTeam's real full names carry generational suffixes RotoWire's
     display names drop entirely ("Marvin Harrison Jr." vs "Marvin
     Harrison", "Deebo Samuel Sr." vs "Deebo Samuel", "James Cook III" vs
     "James Cook") - `_strip_generational_suffix()` now strips a trailing
     Jr/Sr/II/III/IV/V token before computing the surname key.
  2. Same-team, same-surname collisions (Minnesota real-rosters both
     "Aaron Jones Sr." and "Jeshaun Jones") - `resolve_player_id()` now
     adds a first-initial tiebreak when the surname key alone is
     ambiguous, same pattern Dream Team's fuller import cascade already
     uses.
- Remaining unmatched names after both fixes are Kickers (FanTeam has no
  Kicker position at all, so RotoWire's real K slot can never match - an
  expected, permanent, harmless gap) plus one real player (Keenan Allen)
  confirmed genuinely absent from FanTeam's current player pool - not a
  matching bug.
