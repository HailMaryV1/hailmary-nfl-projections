import { createPublicClient } from "@/lib/supabaseClient";
import { computeDifficultyThresholds, difficultyTier, type DifficultyTier } from "@/lib/fixtureDifficulty";

const HORIZONS = [1, 2, 3, 5] as const;
const UPCOMING_FIXTURES_COUNT = 6; // same window as app/players/[id]/page.tsx

// Real player_stats columns this tool ever shows, grouped by the position
// that actually produces them - see supabase/migrations/0003_player_stats.sql
// for the full real column list (a few offense-wide columns, e.g.
// passing_attempts/passing_completions/rushing_attempts/return_tds/
// fumbles_lost/two_point_conversions, aren't part of any position's
// headline read here and are left out, not fabricated).
type StatKey =
  | "passing_yards"
  | "passing_tds"
  | "interceptions_thrown"
  | "rushing_yards"
  | "rushing_tds"
  | "receptions"
  | "receiving_yards"
  | "receiving_tds"
  | "sacks"
  | "def_interceptions"
  | "fumble_recoveries"
  | "safeties"
  | "blocked_kicks"
  | "def_special_tds"
  | "points_allowed";

const STAT_LABELS: Record<StatKey, string> = {
  passing_yards: "Passing Yards",
  passing_tds: "Passing TDs",
  interceptions_thrown: "INTs Thrown",
  rushing_yards: "Rushing Yards",
  rushing_tds: "Rushing TDs",
  receptions: "Receptions",
  receiving_yards: "Receiving Yards",
  receiving_tds: "Receiving TDs",
  sacks: "Sacks",
  def_interceptions: "INTs",
  fumble_recoveries: "Fumble Recoveries",
  safeties: "Safeties",
  blocked_kicks: "Blocked Kicks",
  def_special_tds: "Defensive/ST TDs",
  points_allowed: "Points Allowed",
};

// A quarterback's rushing total is real and tracked (rushing_yards is an
// offense-wide column) but only worth a headline row for the real rushing
// QBs - see POSITION_STAT_KEYS below for where this list is filtered
// further per-player, not just per-position.
const POSITION_STAT_KEYS: Record<string, StatKey[]> = {
  quarterback: ["passing_yards", "passing_tds", "interceptions_thrown", "rushing_yards"],
  running_back: ["rushing_yards", "rushing_tds", "receptions", "receiving_yards", "receiving_tds"],
  wide_receiver: ["receptions", "receiving_yards", "receiving_tds"],
  tight_end: ["receptions", "receiving_yards", "receiving_tds"],
  defense_special: ["sacks", "def_interceptions", "fumble_recoveries", "safeties", "blocked_kicks", "def_special_tds", "points_allowed"],
};

// Two players share a stat group when their real position tracks the exact
// same stat set (wide_receiver and tight_end do) - CompareView renders a
// shared side-by-side row per stat for players in the same group, and two
// independent stat lists for a cross-group (e.g. QB vs WR) comparison.
export function statGroup(position: string): string {
  if (position === "wide_receiver" || position === "tight_end") return "receiver";
  return position;
}

export type StatLine = { key: StatKey; label: string; value: number };

export type ComparePlayer = {
  id: number;
  name: string;
  position: string;
  team: { name: string; abbr: string };
  price: number;
  ownershipPct: number | null;
  pointsByHorizon: Record<number, number | null>;
  // Real season-to-date totals from player_stats. Both null on this specific
  // player when no real row exists yet for the current season - genuinely
  // the state of the whole table right now, week 1 of a brand-new season
  // (see compute_projections.py's own note: "player_stats (none exist yet -
  // the season hasn't been played)"). Never defaulted to 0.
  seasonPointsSoFar: number | null;
  gamesPlayed: number | null;
  statLines: StatLine[];
  upcomingFixtures: { gameweek: number; opponentAbbr: string | null; isHome: boolean | null; isBye: boolean; tier: DifficultyTier }[];
};

type SupabaseClient = ReturnType<typeof createPublicClient>;

type PlayerRow = {
  id: number;
  full_name: string;
  position: string;
  price: number;
  ownership_pct: number | null;
  team_id: number;
  teams: { name: string; abbr: string } | null;
};

type StatsRow = {
  player_id: number;
  season: string;
  gameweek: number | null;
  total_points: number | null;
  passing_yards: number | null;
  passing_tds: number | null;
  interceptions_thrown: number | null;
  rushing_yards: number | null;
  rushing_tds: number | null;
  receptions: number | null;
  receiving_yards: number | null;
  receiving_tds: number | null;
  sacks: number | null;
  def_interceptions: number | null;
  fumble_recoveries: number | null;
  safeties: number | null;
  blocked_kicks: number | null;
  def_special_tds: number | null;
  points_allowed: number | null;
};

const STATS_COLUMNS =
  "player_id, season, gameweek, total_points, passing_yards, passing_tds, interceptions_thrown, rushing_yards, rushing_tds, receptions, receiving_yards, receiving_tds, sacks, def_interceptions, fumble_recoveries, safeties, blocked_kicks, def_special_tds, points_allowed";

function sumColumn(rows: StatsRow[], key: keyof StatsRow): number | null {
  const present = rows.filter((r) => r[key] !== null && r[key] !== undefined);
  if (present.length === 0) return null;
  return present.reduce((acc, r) => acc + Number(r[key]), 0);
}

// Real aggregation decision (verified live against the actual DB, not
// assumed): player_stats has no reliably-populated season-aggregate row
// (gameweek is null) to lean on - as of this build the whole table is
// genuinely empty (see the ComparePlayer doc comment above). This function
// still handles both real shapes an ingest script could produce: a single
// season-aggregate row, or a set of per-gameweek rows to sum - so whichever
// way real data lands later, this keeps working without a code change.
function aggregateSeasonStats(allRows: StatsRow[], playerId: number): { totals: StatsRow | null; gamesPlayed: number | null } {
  const rows = allRows.filter((r) => r.player_id === playerId);
  if (rows.length === 0) return { totals: null, gamesPlayed: null };

  const latestSeason = rows.reduce((max, r) => (r.season > max ? r.season : max), rows[0].season);
  const seasonRows = rows.filter((r) => r.season === latestSeason);

  const aggregateRow = seasonRows.find((r) => r.gameweek === null);
  if (aggregateRow) {
    // A real season-aggregate row doesn't itself say how many real games
    // it covers - games played is left null (never guessed) rather than
    // assumed from the gameweek count.
    return { totals: aggregateRow, gamesPlayed: null };
  }

  const perGameRows = seasonRows.filter((r) => r.gameweek !== null);
  if (perGameRows.length === 0) return { totals: null, gamesPlayed: null };

  const keys: (keyof StatsRow)[] = [
    "total_points",
    "passing_yards",
    "passing_tds",
    "interceptions_thrown",
    "rushing_yards",
    "rushing_tds",
    "receptions",
    "receiving_yards",
    "receiving_tds",
    "sacks",
    "def_interceptions",
    "fumble_recoveries",
    "safeties",
    "blocked_kicks",
    "def_special_tds",
    "points_allowed",
  ];
  const summed = {} as StatsRow;
  for (const key of keys) {
    (summed as unknown as Record<string, number | null>)[key] = sumColumn(perGameRows, key);
  }
  summed.player_id = playerId;
  summed.season = latestSeason;
  summed.gameweek = null;

  return { totals: summed, gamesPlayed: perGameRows.length };
}

function buildStatLines(position: string, totals: StatsRow | null): StatLine[] {
  if (!totals) return [];
  const keys = POSITION_STAT_KEYS[position] ?? [];
  const lines: StatLine[] = [];
  for (const key of keys) {
    const raw = totals[key];
    if (raw === null || raw === undefined) continue; // untracked/unmeasured for this player - left out, never shown as 0
    const value = Number(raw);
    if (position === "quarterback" && key === "rushing_yards" && value <= 0) continue; // only a headline row for QBs who actually carry the ball
    lines.push({ key, label: STAT_LABELS[key], value });
  }
  return lines;
}

// One joint loader (rather than one call per player, as the EFL sibling
// does) because every heavy lookup here - the current algorithm version,
// the current gameweek, and the difficulty thresholds - is real shared
// state for the whole league, not something to compute twice.
export async function loadComparePlayers(
  supabase: SupabaseClient,
  idA: number,
  idB: number
): Promise<{ playerA: ComparePlayer | null; playerB: ComparePlayer | null }> {
  const ids = [idA, idB];

  // Sequential, plainly-typed awaits throughout this loader rather than
  // Promise.all over mixed query-builder shapes (a `.in()` list query next
  // to a `.maybeSingle()` lookup) - Supabase's builder generics don't
  // preserve well through Promise.all's tuple inference, and the two extra
  // round trips this costs are negligible next to a page load.
  const { data: playerRows } = await supabase
    .from("players")
    .select("id, full_name, position, price, ownership_pct, team_id, teams!team_id(name, abbr)")
    .in("id", ids);

  const players = (playerRows ?? []) as unknown as PlayerRow[];
  const playerById = new Map(players.map((p) => [p.id, p]));
  if (!playerById.get(idA) || !playerById.get(idB)) {
    return { playerA: null, playerB: null };
  }

  const { data: latestVersionRow } = await supabase.from("algorithm_versions").select("id").order("id", { ascending: false }).limit(1).maybeSingle();
  const algorithmVersionId = latestVersionRow?.id as number | undefined;

  // Same "horizon 1's own gameweek" convention as app/page.tsx - every
  // horizon in one pipeline run shares the same starting gameweek.
  const gwResult = algorithmVersionId
    ? await supabase
        .from("projections")
        .select("gameweek")
        .eq("horizon", 1)
        .eq("algorithm_version_id", algorithmVersionId)
        .order("gameweek", { ascending: false })
        .limit(1)
        .maybeSingle()
    : null;
  const currentGameweek = gwResult?.data?.gameweek as number | undefined;

  const projResult =
    algorithmVersionId && currentGameweek
      ? await supabase
          .from("projections")
          .select("player_id, horizon, total_points")
          .in("player_id", ids)
          .eq("algorithm_version_id", algorithmVersionId)
          .eq("gameweek", currentGameweek)
          .in("horizon", HORIZONS as unknown as number[])
      : null;
  const projRows = (projResult?.data ?? []) as { player_id: number; horizon: number; total_points: number }[];

  const { data: statsRows } = await supabase.from("player_stats").select(STATS_COLUMNS).in("player_id", ids).order("season", { ascending: false });

  const { data: allWinTotals } = await supabase.from("team_schedule_difficulty").select("opponent_win_total").not("opponent_win_total", "is", null).eq("is_bye", false);
  const thresholds = computeDifficultyThresholds((allWinTotals ?? []).map((r) => Number(r.opponent_win_total)));

  const teamIds = [...new Set(players.map((p) => p.team_id))];
  const scheduleResult = currentGameweek
    ? await supabase
        .from("team_schedule_difficulty")
        .select("team_id, gameweek, is_home, is_bye, opponent_win_total, opponent:teams!opponent_team_id(abbr)")
        .in("team_id", teamIds)
        .gte("gameweek", currentGameweek)
        .lt("gameweek", currentGameweek + UPCOMING_FIXTURES_COUNT)
        .order("gameweek")
    : null;
  const scheduleRows = scheduleResult?.data ?? [];

  type ScheduleJoin = { team_id: number; gameweek: number; is_home: boolean | null; is_bye: boolean; opponent_win_total: number | null; opponent: { abbr: string } | null };
  const scheduleByTeam = new Map<number, ScheduleJoin[]>();
  for (const row of (scheduleRows ?? []) as unknown as ScheduleJoin[]) {
    const list = scheduleByTeam.get(row.team_id) ?? [];
    list.push(row);
    scheduleByTeam.set(row.team_id, list);
  }

  const statsAll = (statsRows ?? []) as unknown as StatsRow[];
  const projAll = (projRows ?? []) as { player_id: number; horizon: number; total_points: number }[];

  function buildPlayer(id: number): ComparePlayer | null {
    const p = playerById.get(id);
    if (!p) return null;

    const pointsByHorizon: Record<number, number | null> = { 1: null, 2: null, 3: null, 5: null };
    for (const row of projAll.filter((r) => r.player_id === id)) {
      pointsByHorizon[row.horizon] = Number(row.total_points);
    }

    const { totals, gamesPlayed } = aggregateSeasonStats(statsAll, id);

    const fixtures = (scheduleByTeam.get(p.team_id) ?? []).map((row) => ({
      gameweek: row.gameweek,
      opponentAbbr: row.opponent?.abbr ?? null,
      isHome: row.is_home,
      isBye: row.is_bye,
      tier: difficultyTier(row.opponent_win_total === null ? null : Number(row.opponent_win_total), row.is_bye, thresholds),
    }));

    return {
      id: p.id,
      name: p.full_name,
      position: p.position,
      team: { name: p.teams?.name ?? "—", abbr: p.teams?.abbr ?? "—" },
      price: Number(p.price),
      ownershipPct: p.ownership_pct === null ? null : Number(p.ownership_pct),
      pointsByHorizon,
      seasonPointsSoFar: totals?.total_points === null || totals?.total_points === undefined ? null : Number(totals.total_points),
      gamesPlayed,
      statLines: buildStatLines(p.position, totals),
      upcomingFixtures: fixtures,
    };
  }

  return { playerA: buildPlayer(idA), playerB: buildPlayer(idB) };
}
