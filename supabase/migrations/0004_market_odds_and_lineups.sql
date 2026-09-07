-- Real bookmaker-derived signal for the Live Odds layer, plus real game-
-- level context and lineup status. Same append-only, flexible market/value
-- shape as Dream Team's equivalent migration - "never fabricate a number"
-- means an unavailable market is simply absent, no is_estimated flag needed.

-- Game-level real market context (spread/moneyline/total), sourced from
-- Spreadex and/or RotoWire - both carry this, kept distinguishable by
-- `source` so one can cross-validate the other.
create table game_odds (
  id bigint generated always as identity primary key,
  fixture_id bigint not null references fixtures(id) on delete cascade,
  home_spread numeric,
  home_moneyline numeric,
  away_moneyline numeric,
  total_points_over_under numeric,
  source text not null,
  captured_at timestamptz not null default now()
);

create index on game_odds (fixture_id, captured_at desc);

-- One row per (player, fixture, market) observation. `market` values are
-- real Spreadex "Weekly Player Markets" categories - 'passing_yards',
-- 'passing_tds', 'passing_completions', 'passing_attempts',
-- 'rushing_yards', 'rushing_tds', 'receiving_yards', 'receiving_tds',
-- 'rushing_receiving_yards', 'sacks' - extend as new markets get wired in
-- (see docs/data-and-weights.md), never by adding a column.
create table player_market_odds (
  id bigint generated always as identity primary key,
  player_id bigint not null references players(id) on delete cascade,
  fixture_id bigint not null references fixtures(id) on delete cascade,
  market text not null,
  value numeric not null,
  source text not null,
  captured_at timestamptz not null default now()
);

create index on player_market_odds (fixture_id, market, captured_at desc);
create index on player_market_odds (player_id, market, captured_at desc);

-- Real lineup status. Vocabulary covers both real sources actually in use:
-- RotoWire's own (starter/questionable/doubtful/inactive) and FanTeam's own
-- lineup field (expected/injured/possible/refuted/unexpected) - kept
-- distinguishable by `source` rather than forced into one made-up scale.
create table player_lineup_status (
  id bigint generated always as identity primary key,
  player_id bigint not null references players(id) on delete cascade,
  fixture_id bigint not null references fixtures(id) on delete cascade,
  status text not null check (status in (
    'starter', 'questionable', 'doubtful', 'inactive',
    'expected', 'injured', 'possible', 'refuted', 'unexpected'
  )),
  source text not null,
  captured_at timestamptz not null default now()
);

create index on player_lineup_status (fixture_id, captured_at desc);
create index on player_lineup_status (player_id, captured_at desc);

alter table game_odds enable row level security;
alter table player_market_odds enable row level security;
alter table player_lineup_status enable row level security;
create policy "public read" on game_odds for select using (true);
create policy "public read" on player_market_odds for select using (true);
create policy "public read" on player_lineup_status for select using (true);
