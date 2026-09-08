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
  4b. **Closed same-day** (2026-09-07, user's own follow-up: "Lets find the
     Anytime TD market"). Real trail, each step verified before moving on:
     - Spreadex: confirmed live it has NO standalone anytime-TD market
       posted yet for Week 1 (checked every tab on a fixture page plus all
       5 Weekly Player Markets tabs) - only referenced in generic SEO
       boilerplate text, not an actual live panel.
     - Oddschecker: real, live "Anytime Touchdown Scorer" market found and
       fully inspected (real per-player fractional odds via a genuine
       `/api/markets/v2/all-odds` JSON endpoint) - but a plain headless
       Playwright session was actively Cloudflare-blocked ("Attention
       Required" page), confirmed by direct test, not assumed.
     - Midnite (a real GB-licensed operator): same real market exists, same
       outcome - AWS WAF actively blocked headless Playwright ("Midnite is
       unavailable" soft-block).
     - FanDuel: blocked by this environment's own browsing policy before
       any technical check was even possible (a live wagering platform).
     - jedibets.com: real, unblocked, but is a historical per-game
       TD-scoring RATE ("4 of last 10 games, 2025 season"), not a live
       market probability - user correctly rejected this as inconsistent
       with the project's real-live-odds discipline ("hold up if thats not
       odds why we using it??"). Built, then fully removed (scraper,
       importer, and the 125 imported rows) rather than left half-used.
     - **fantasyinfocentral.com**: real, live, unblocked - confirmed via a
       direct Playwright test with zero bot-protection cookies. Displays a
       real, live Caesars sportsbook line (confirmed: every row's
       bookmaker attribution reads "Caesars") as editorial content, one
       page covering all 16 real Week 1 fixtures at once (no per-fixture
       navigation needed, unlike every other source in this project).
       `scripts/scrape_fic_anytime_td.py` + `scripts/import_fic_anytime_td.py`
       - 105/105 real players matched with zero unmatched names on the
       first real run (the earlier generational-suffix and same-team-
       surname fixes carried over directly).
     - Wired into `compute_projections.py` as a new `anytime_td` stat,
       priced via the `rushing_td` scoring rate (confirmed identical to
       `receiving_td` at 6pts - the market doesn't distinguish which type
       of TD, so it doesn't matter which rate is borrowed). Verified the
       full pipeline against real numbers: Jahmyr Gibbs' real -335 odds ->
       1.47 expected TDs, matching the stored value exactly; Josh Allen's
       total rose from 18.4 to 22.0 (his real rushing-TD upside, previously
       invisible); Gibbs became the week's top-projected RB, matching his
       real status as the market's TD favorite.
  5. `defense_special` had zero coverage - **closed same-day** (2026-09-07,
     user's own suggestion): "defense special teams get good points for
     not conceding so maybe projection could be based on the likelihood
     of the opponent that week scoring highly or low". Implemented as a
     real Fixture Quality signal: the opponent's expected points is
     derived from the same RotoWire game_odds (spread + total) already
     ingested (`home_expected = (total - home_spread) / 2`, confirmed
     against real data), then turned into an expected points-allowed
     score via a Normal-distribution approximation across FanTeam's real
     scoring tiers (`stat_math.points_allowed_distribution`, sd=10 - a
     documented, commonly-observed NFL scoring-variance assumption, not
     measured from this project's own data yet). Verified against real
     numbers: Jacksonville's D/ST (facing Cleveland, a -420 moneyline
     underdog) topped the real projection list; Arizona's (facing a
     10-point-favorite Chargers team) sat at the bottom - correct
     direction. Individual defensive-play stats (sacks, turnovers, blocked
     kicks, defensive/return TDs) still have no real data source and stay
     at 0 - a real, separate, still-open gap.

## 2026-09-07 - Phase 5 v1: public frontend live

- Real projections pool at `/` (Server Component, direct Supabase query -
  no client-side fetch/loading-spinner needed for the initial view) -
  position filter tabs, mobile card list (same reason every other list
  view in the Hail Mary portfolio needs one - a table overflows badly
  under `sm:`), desktop table. Verified against the live DB: top-ranked
  players and exact point values match the values already spot-checked
  via direct SQL earlier in Phase 3.
- Real per-player page at `/players/[id]` - the "how this was built"
  explainability view the original design called for, done from day one
  rather than deferred: shows each of the five layers' real state
  (`Live` vs `Not yet available`, never invented) plus the full per-stat
  breakdown. Verified the numbers are internally consistent, not just
  plausible-looking: Justin Herbert's displayed 13.03 + 9.79 + 2.56 sums
  to exactly his displayed 25.4 total; Jacksonville's D/ST page correctly
  shows `Fixture Quality: Live` / `Live Odds: Not yet available` (matching
  the real architecture decision from the points-allowed work above, not
  a mislabelled layer).
- **Real gap caught before shipping**: the frontend needs its OWN
  `frontend/.env.local` (Next.js only reads `NEXT_PUBLIC_*` vars from
  there, or real Vercel env vars) - the repo-root `.env` the Python
  scripts use is a separate file Next.js never reads. Missing this
  produced a real, reproducible `supabaseUrl is required` 500 on every
  page load until fixed.
- **Real gap caught in the same pass**: root `.gitignore` only listed
  `.env`, not `.env.local` - the new frontend env file (holding the real
  service-role secret) would have been committed on the next `git add -A`
  had this not been caught immediately. Fixed before the file was ever
  staged.
- Deployed to `nfl.hailmaryfantasysports.co.uk` via Vercel (user's own
  GitHub push + Vercel project + Hostinger CNAME, walked through step by
  step) - confirmed live and rendering the real placeholder content
  before this frontend work replaced it with the real pool.


## 2026-09-08 - Phase 4 v1: admin settings UI live

- Real Supabase-Auth-gated `/admin` - `frontend/proxy.ts` (Next.js 16's
  middleware.ts rename, same convention as Dream Team Projections) redirects
  any unauthenticated `/admin/*` request to `/login`. Two real editors:
  - **Scoring Rules** - every row from migration 0005, editable inline,
    grouped by offense/defense_special.
  - **Layer Weights** - horizon x position tabs (20 combos) rather than all
    80 rows at once, with a live effective-split sum shown (green at 1.00,
    amber otherwise) so a save can't silently leave weights not summing to
    1 without at least a visible warning.
  - Both write via Server Actions using the real authenticated session
    (`lib/supabaseServerClient.ts`), and log every real change to
    `activity_log` with the actual old/new values and the signed-in
    admin's email as `actor` - shown on the new `/admin` dashboard's
    "Recent activity" list.
- **Verified the security model actually works, not just that the UI
  hides the buttons**: sent a raw unauthenticated PATCH to
  `scoring_rules` via the public anon key, got back a real HTTP 200 with
  an empty result array (Postgres RLS's real behaviour for a policy that
  evaluates false - not a 403, a silent "0 rows matched"), then confirmed
  directly against the DB that the value was genuinely untouched. RLS's
  `to authenticated` policy is doing real work, not just decorative.
- Deliberately did NOT build the third panel from the original design
  (rating-anchor recalibration) - `rating` is still NULL project-wide
  (see Phase 3 docstring), so a "recalibrate the 1-10 scale" action would
  have nothing real to operate on yet. Revisit once real season data
  exists.
- One real manual step left before this is usable, deliberately not done
  here: creating the actual admin login. Per this project's own
  credential-handling rule, Claude never sets or enters a password on the
  user's behalf, even a first one - the user creates it directly in
  Supabase Dashboard -> Authentication -> Users -> Add User.

## 2026-09-08 - Real production build failure caught post-push

- The Phase 4 push almost certainly failed to deploy on Vercel: `/login`'s
  `useSearchParams()` wasn't wrapped in a `<Suspense>` boundary, which
  `next build` treats as a hard prerender error (confirmed by running a
  real local production build - `npm run dev` never surfaces this class
  of error, only `next build` does). Live site was still serving the old
  Phase 5 build (confirmed: the new "Admin" header link wasn't present)
  while `/admin` 404'd - consistent with a failed Vercel build, not just
  "still deploying".
- Fixed by splitting `/login` into a server `page.tsx` (wraps in
  `<Suspense>`) and a client `LoginForm.tsx` (holds the actual
  `useSearchParams()` call) - verified with a real local `npm run build`
  before pushing again, not just re-deploying and hoping.
- **Process lesson for this project going forward**: `npm run dev` is not
  sufficient verification before a push that's expected to deploy - run
  a real `npm run build` locally first whenever a change touches
  `useSearchParams`, `useSelectedLayoutSegment`, or anything else with
  known static-rendering caveats.
