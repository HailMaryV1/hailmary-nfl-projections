# Hail Mary NFL Projections

A standalone NFL fantasy projections site for FanTeam's real-money "NFL
Regular Season 2026/27" tournament (tournament ID `1136503`), deployed at
`NFL.hailmaryfantasysports.co.uk`.

**This project is fully independent.** It does not share a repo, database,
deployment, or any code path with Dream Team Projections or any other game
in the Hail Mary portfolio. Every data source, table, and script here is
built from scratch for NFL. Do not suggest reusing Dream Team's DB, importing
its code, or merging routes/UI - that was an explicit, deliberate decision
(see the "why" below), not an oversight.

## Why a separate project

FanTeam's NFL tournament is a different sport, a different real scoring
system, and a different real ruleset from every other Hail Mary game. Sharing
infrastructure with Dream Team (or any other game) risks the two silently
drifting into each other - a squad-list assumption, a calibration constant,
a UI convention that only makes sense for football leaking into NFL, or vice
versa. Every game in this portfolio gets its own route tree, its own UI, and
its own learning - see the sibling projects' own CLAUDE.md files for the same
rule applied elsewhere.

## Real scoring rules (FanTeam NFL)

**Offense** (per real statistical event):
- Passing Yards: 0.04/yd
- Rushing Yards: 0.1/yd
- Receiving Yards: 0.1/yd
- Passing TD: 4
- Rushing TD: 6
- Receiving TD: 6
- Punt/Kickoff/FG return TD: 6
- Interception thrown: -2
- Reception (PPR): +1
- Fumble Lost: -2
- Two-point conversion: +2

**Defense/Special Teams** - a single unit, position `defense_special`. There
is no separate Kicker position in this tournament's ruleset.
- Sack: 1
- Interception: 2
- Fumble Recovery: 2
- Safety: 2
- Blocked Kick: 2
- Interception/Fumble recovery TD: 6
- Punt/Kickoff/FG return TD: 6
- Points allowed: 0 -> 10, 1-6 -> 7, 7-13 -> 4, 14-20 -> 1, 21-27 -> 0,
  28-34 -> -1, 35+ -> -4

## Real tournament rules

- 18 gameweeks (one per real NFL regular-season week).
- Top 10% of entries paid.
- Max 3 players from the same real NFL team.
- Max 15 entries per user.
- 2 free transfers per gameweek; unused transfers save up to a cap of 34.
- -8 points per transfer beyond the free allowance.
- Transfers are revertible until each gameweek's real deadline.
- One Wildcard per tournament (resets saved transfers when played).
- Squad budget: £140M.
- No tie-breakers - shared placement.
- Real auto-substitution "safety net": if a starter scores 0 fantasy points
  in their real match, they're replaced by a same-team, same-position player
  of equal or lower cost. Applies to positions: quarterback, running_back,
  wide_receiver, tight_end, defense_special.

## Confirmed real data sources

1. **FanTeam/ScoutGG API** -
   `https://fanteam-game.api.scoutgg.net/tournaments/1136503/players?round=editable`.
   Fully unauthenticated, public. Returns players, `realMatches` (fixtures,
   incl. odds), `realTeams`, and tournament config in one call. Same
   platform proven working in the sibling `dreamteam-scraper` repo's
   `scraper_fanteam.py` for a different (UK Premier League) tournament.
2. **Spreadex** - `spreadex.com/sports/en-GB/spread-betting/american-football`.
   Real NFL section: match odds/spreads/totals plus a genuine "Weekly Player
   Markets" category with real per-fixture player props - Passing (yardage
   bands, O/U, TDs, completions, attempts, longest completion), Rushing,
   Receiving, Rushing+Receiving combined, Sacks. No standalone "anytime TD
   scorer" market - derive that from the TD-count markets. This is the Live
   Odds layer source. The category page has no server-renderable deep link
   (client-side SPA routing) - reach it by clicking through from the
   homepage nav, not by constructing a URL directly.
3. **RotoWire lineups** - `rotowire.com/football/lineups.php/{week}`. Real
   per-team predicted starting lineups, per-player Inactive/Questionable("Q")
   tags, plus bundled spread/moneyline/O-U and weather (temp/wind/
   precipitation/dome) per fixture. Server-rendered HTML, no JSON API.
   **The page carries real Cloudflare Bot Management (`__cf_bm`) and Google
   reCAPTCHA cookies** - scrape with a real browser (Playwright) at a modest
   cadence (a few times a day), never aggressive polling. This is the
   primary Lineup Status layer source and the weather sub-signal source.

## The rating model - five layers (adapted from Dream Team's proven design)

1. **Lineup Status** - RotoWire Starter/Inactive/Questionable, cross-checked
   against FanTeam's own `lineup` field (expected/injured/possible/refuted/
   unexpected - same vocabulary FanTeam uses across all its games).
2. **Form** - decay-weighted recent real per-game fantasy production.
3. **Fixture Quantity** - bye weeks matter here instead of blanks/doubles;
   a player on a bye scores 0 fantasy points for that gameweek, full stop.
4. **Fixture Quality** - real opponent defensive strength against the
   player's position (e.g. real yards/points allowed to WRs, to RBs, etc.).
5. **Live Odds** - Spreadex player-prop markets, weighted in only once
   available (same "renormalize over whichever layers are populated"
   mechanic as Dream Team - a layer with no data yet simply doesn't
   contribute, no fallback logic needed).

Plus one NFL-specific addition with no Dream Team equivalent: a small
**weather** sub-signal (wind/precipitation suppresses passing volume; dome
games get no adjustment) sourced from RotoWire.

## Status

Phase 0 (scaffolding), Phase 1 (schema, 32 real teams), Phase 2 (data
ingestion - FanTeam, RotoWire, Spreadex, FantasyInfoCentral anytime-TD) and
Phase 3 v1 (projection engine, incl. real anytime-TD odds and a real
defense/special-teams points-allowed projection) done. Pipeline:
`python scripts/refresh_nfl.py` then `python scripts/compute_projections.py`.
Real, honestly-documented gaps remain - see compute_projections.py's own
module docstring and docs/data-and-weights.md (horizon 1 only, no rating
yet, individual defensive-play stats still unprojected).

Phase 5 v1 (public frontend) done: live at
`nfl.hailmaryfantasysports.co.uk` (Vercel, auto-deploys on push to main).
Real projections pool (`/`, position-filterable, mobile card list + desktop
table) and a real per-player explainability page (`/players/[id]`) showing
the actual per_stat/per_layer breakdown - "Not yet available" shown
honestly wherever a layer has no real data, never a fabricated number.
Phase 4 v1 done: real Supabase-Auth-gated admin at `/admin` (Scoring Rules
+ Layer Weights editors, both writing straight to the real tables via RLS's
"admin write" policy - confirmed live that an unauthenticated write is
silently rejected, not just UI-hidden). Admin login created and working.

Phase 6 done: `.github/workflows/refresh_nfl.yml` runs the full pipeline
(ingestion + projection engine) every 6 hours plus on-demand via
workflow_dispatch, same continue-on-error resilience pattern as Dream Team
Projections. Needs a `DATABASE_URL` repository secret set in GitHub
(Settings -> Secrets and variables -> Actions) before its first real run.
