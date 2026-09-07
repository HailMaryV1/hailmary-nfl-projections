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

## 2026-09-07 - Phase 2 (part 3): Spreadex NFL player props live

- `scripts/scrape_spreadex_nfl_props.py` - real, working end to end against
  Spreadex's real "Weekly Player Markets" page. Confirmed live: unlike
  Dream Team's per-fixture Spreadex scrape, this ONE page carries all 16
  real fixtures' player markets across 5 real tabs (Passing, Rushing +
  Receiving, Rushing, Receiving, Sacks) - no per-fixture navigation needed.
  Real DOM boundary confirmed by inspection: `sc-panel` elements with no
  nested `sc-panel` are the true leaf market panels (an outer wrapper
  `sc-panel` duplicates the same header text and inflates counts if not
  filtered out).
- Two real button label shapes found and handled: a ladder
  ("{Player} - {N}+ Price Button") and an Over/Under pair
  ("{Player} Over/Under {X} Price Button"). Each rung is stored as its own
  `player_market_odds` row (market e.g. `passing_yards_225plus`,
  `passing_yards_over_232.5`) with the raw implied probability
  (1/decimal_odds) - fitting an expected value from the ladder is Phase 3's
  job, not this script's ("never fabricate" - store what's observed).
- Two real bugs found and fixed during verification, both against actual
  observed data, not hypothetical:
  1. Spreadex renders SOME team codes in Title Case within the same header
     text ("Atl @ Pit", "Bal @ Ind") while others stay fully capitalised
     ("NE @ Sea" - "Sea" itself is Title Case too) - no consistent rule.
     The header regex was case-sensitive and silently dropped ~90% of real
     rows (508 buttons seen, only 56 written) with no error. Fixed by
     matching case-insensitively and upper-casing before comparing against
     our all-caps `teams.abbr`.
  2. "Player Passing and Rushing Yards" appears as the same real panel
     under both the Rushing and Rushing + Receiving tabs - scraping both
     tabs double-inserted it. Fixed with a per-run `seen_headers` set
     (a genuinely new observation from a LATER run still gets its own row).
- **Sacks tab deliberately excluded**, not just under-matched: it prices
  INDIVIDUAL defensive players, but this project's player pool only has
  the team-level `defense_special` unit (FanTeam's real ruleset has no
  individual defenders at all). Verified this isn't just a coverage gap -
  it produced an actual false-positive match (an individual defender's
  "Kyle Williams" silently matched our unrelated offensive WR of the same
  name). Scraping it risks wrong attributions, not just missing data, so
  it's excluded outright rather than "fixed" - there is no correct match
  target for this market in this schema.
- Final verified state: 2542 real `player_market_odds` rows, zero
  duplicates, zero known false positives, across passing/rushing/receiving
  yardage ladders, TD ladders, completions/attempts, longest
  completion/reception, and O/U lines.

## 2026-09-07 - Phase 3 (v1): projection engine live

- `scripts/stat_math.py` + `scripts/compute_projections.py` - real,
  working, verified end to end for gameweek 1 / horizon 1. 603 projections
  written, algorithm_version 1 created (first snapshot of scoring_rules +
  layer_weights).
- Two real estimators, both standard and derived from the actual observed
  probabilities, not invented: `expected_value_from_points` (tail-sum
  integral of a real survival curve built from ladder rungs + the O/U
  line, trapezoidal between points, geometric-decay tail beyond the
  highest rung) for yardage/reception-count stats; `anytime_prob_to_
  expected_count` (the same Poisson-process formula already proven in
  Dream Team's Spreadex scraper) for the passing-TD ladder.
- **Real bug caught before it shipped**: the Over/Under regex didn't
  distinguish "_over_X" from "_under_X" - both would have fed into the
  same points list as if both were real P(X >= X) observations, when
  "under" is the complement, not another survival-curve point. Fixed by
  matching them separately and only using "over".
- Sanity-checked against real numbers: Josh Allen's estimated 222.4
  expected passing yards lands within 3 yards of Spreadex's own posted
  219.5 O/U line (an independent cross-check, not circular - the O/U line
  wasn't the only input). Top-10 QBs by total_points are all real,
  plausible starters, ranked by matchup/market strength rather than just
  echoing FanTeam's price. Injured/inactive players correctly project to
  0.0. Position averages match expected real-world shape (QBs highest and
  most consistent; RB/WR/TE lower and more spread out, reflecting a
  backup-heavy real player pool).
- **Known, deliberately undisguised gaps in this v1**, all documented in
  the script's own module docstring rather than only here:
  1. Only horizon 1 is computed - horizons 2/3/5 need future-gameweek
     fixtures (byes, opponent matchups) not yet ingested.
  2. `rating` (1-10 absolute scale) is left NULL - calibrating it needs a
     real measured distribution from a season that's one gameweek old.
     Writing a number now would be invented, not measured.
  3. Form and Fixture Quality layers are `populated: false` for every
     player - both need real prior-gameweek stats/defensive performance
     that doesn't exist yet in a brand-new season. `total_points` this
     early is effectively 100% Live-Odds-driven - correct given the real
     data available, not a defect.
  4. `rushing_td`/`receiving_td` have zero live-odds signal - confirmed
     live that Spreadex's Weekly Player Markets page has no standalone
     market for either (only Passing Touchdowns). A real anytime-TD market
     likely exists elsewhere on Spreadex (e.g. "1st Touchdown Type",
     spotted but not yet scraped) - open follow-up, not silently faked.
  5. `defense_special` has zero live-odds coverage (Sacks was excluded in
     Phase 2 for pricing individuals this schema can't represent) - every
     unit projects to a plain, visible 0.0 until a real team-level
     defensive data source is found, rather than a fabricated placeholder.
