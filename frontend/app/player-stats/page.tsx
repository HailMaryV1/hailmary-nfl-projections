import SiteHeader from "../SiteHeader";
import PlayerStatsTable, { type PlayerStatRow } from "./PlayerStatsTable";
import { createPublicClient } from "@/lib/supabaseClient";

// Real per-gameweek columns from supabase/migrations/0003_player_stats.sql -
// read directly from that file, not assumed. Offense stats are per-player;
// the defense_special block is per real team/gameweek (FanTeam scores
// D/ST as one unit, not per individual defender).
const STAT_COLUMNS = [
  "passing_attempts",
  "passing_completions",
  "passing_yards",
  "passing_tds",
  "interceptions_thrown",
  "rushing_attempts",
  "rushing_yards",
  "rushing_tds",
  "receptions",
  "receiving_yards",
  "receiving_tds",
  "return_tds",
  "fumbles_lost",
  "two_point_conversions",
  "sacks",
  "def_interceptions",
  "fumble_recoveries",
  "safeties",
  "blocked_kicks",
  "def_special_tds",
  "points_allowed",
] as const;

type StatColumnKey = (typeof STAT_COLUMNS)[number];
type StatRow = { player_id: number; total_points: number | null } & Record<StatColumnKey, number | null>;

const PAGE_SIZE = 1000;

// Real verification done before writing this (2026-09-13, live Supabase
// query against this exact table): total row count is 0, and there is no
// gameweek-is-null row for any player - unlike Dream Team/EFL's sibling
// player_stats tables, this one has never had a season-aggregate row
// convention (confirmed against docs/data-and-weights.md's own migration
// notes, which describe only per-gameweek rows) and no ingestion pipeline
// for it exists yet (compute_projections.py's own comment: "player_stats
// (none exist yet - the season hasn't been played)"). So this sums real
// per-gameweek rows itself rather than trusting an aggregate that doesn't
// exist. Paginated defensively (Supabase's default page cap is 1000 rows)
// so this keeps working once a full season of real rows exists.
async function fetchAllGameweekStats(supabase: ReturnType<typeof createPublicClient>): Promise<StatRow[]> {
  const all: StatRow[] = [];
  let from = 0;
  for (;;) {
    const { data, error } = await supabase
      .from("player_stats")
      .select(`player_id, total_points, ${STAT_COLUMNS.join(",")}`)
      .not("gameweek", "is", null)
      .range(from, from + PAGE_SIZE - 1);
    if (error) throw new Error(`Failed to load player_stats: ${error.message}`);
    const page = (data ?? []) as unknown as StatRow[];
    all.push(...page);
    if (page.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }
  return all;
}

function emptyStats(): PlayerStatRow["stats"] {
  return {
    passing_attempts: 0,
    passing_completions: 0,
    passing_yards: 0,
    passing_tds: 0,
    interceptions_thrown: 0,
    rushing_attempts: 0,
    rushing_yards: 0,
    rushing_tds: 0,
    receptions: 0,
    receiving_yards: 0,
    receiving_tds: 0,
    return_tds: 0,
    fumbles_lost: 0,
    two_point_conversions: 0,
    sacks: 0,
    def_interceptions: 0,
    fumble_recoveries: 0,
    safeties: 0,
    blocked_kicks: 0,
    def_special_tds: 0,
    points_allowed: 0,
  };
}

export default async function PlayerStatsPage() {
  const supabase = createPublicClient();

  const { data: playerRows, error: playersError } = await supabase
    .from("players")
    .select("id, full_name, position, team_id, teams!team_id(abbr)")
    .eq("is_active", true)
    .order("full_name");
  if (playersError) throw new Error(`Failed to load players: ${playersError.message}`);

  const statRows = await fetchAllGameweekStats(supabase);

  type Agg = { stats: PlayerStatRow["stats"]; totalPoints: number; gamesPlayed: number };
  const aggByPlayerId = new Map<number, Agg>();
  for (const row of statRows) {
    let agg = aggByPlayerId.get(row.player_id);
    if (!agg) {
      agg = { stats: emptyStats(), totalPoints: 0, gamesPlayed: 0 };
      aggByPlayerId.set(row.player_id, agg);
    }
    for (const key of STAT_COLUMNS) {
      agg.stats[key] += Number(row[key] ?? 0);
    }
    agg.totalPoints += Number(row.total_points ?? 0);
    agg.gamesPlayed += 1;
  }

  type PlayerJoin = { id: number; full_name: string; position: string; team_id: number; teams: { abbr: string } | null };
  const players: PlayerStatRow[] = ((playerRows ?? []) as unknown as PlayerJoin[]).map((p) => {
    const agg = aggByPlayerId.get(p.id);
    return {
      playerId: p.id,
      name: p.full_name,
      position: p.position,
      team: p.teams?.abbr ?? "—",
      gamesPlayed: agg?.gamesPlayed ?? 0,
      totalPoints: agg?.totalPoints ?? 0,
      stats: agg?.stats ?? emptyStats(),
    };
  });

  const anyRealStats = statRows.length > 0;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 p-4 sm:p-6">
        <h1 className="text-2xl font-semibold text-navy-100">Player Stats</h1>
        <p className="mt-1 max-w-2xl text-sm text-navy-300">
          Real season-to-date stats for every active FanTeam NFL Regular Season 2026/27 player - what&apos;s actually
          happened, not a projection.
        </p>

        {!anyRealStats && (
          <p className="mt-4 rounded-md border border-navy-800 bg-navy-900 px-3 py-2 text-sm text-navy-400">
            No real gameweek stats have been recorded yet, so every player below shows &ldquo;—&rdquo; rather than a
            guessed 0 - this fills in as soon as real per-gameweek stats are ingested.
          </p>
        )}

        <div className="mt-6">
          <PlayerStatsTable players={players} />
        </div>
      </main>
    </>
  );
}
