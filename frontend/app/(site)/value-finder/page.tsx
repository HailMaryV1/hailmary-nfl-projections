import Link from "next/link";
import RatingsTable, { type PlayerRow } from "../../RatingsTable";
import { createPublicClient } from "@/lib/supabaseClient";
import { computeDifficultyThresholds, difficultyTier } from "@/lib/fixtureDifficulty";

const HORIZONS = [1, 2, 3, 5];
const HORIZON_LABELS: Record<number, string> = { 1: "This Week", 2: "Next 2", 3: "Next 3", 5: "Next 5" };

// Real port of the direct Value Finder/Enablers concept from the sibling
// Premier League site - a dedicated destination for the same real
// points-per-£m ranking RatingsTable already supports as a sort toggle
// (see app/page.tsx), just opened straight into that view by default and
// given its own real page/nav entry.
export default async function ValueFinderPage({ searchParams }: { searchParams: Promise<{ horizon?: string }> }) {
  const { horizon: horizonParam } = await searchParams;
  const horizon = HORIZONS.includes(Number(horizonParam)) ? Number(horizonParam) : 1;

  const supabase = createPublicClient();

  const { data: latestVersionRow } = await supabase
    .from("algorithm_versions")
    .select("id")
    .order("id", { ascending: false })
    .limit(1)
    .maybeSingle();
  const algorithmVersionId = latestVersionRow?.id;

  const { data: gwRow } = algorithmVersionId
    ? await supabase
        .from("projections")
        .select("gameweek")
        .eq("horizon", 1)
        .eq("algorithm_version_id", algorithmVersionId)
        .order("gameweek", { ascending: false })
        .limit(1)
        .maybeSingle()
    : { data: null };
  const gameweek = gwRow?.gameweek;

  type ProjectionRow = {
    total_points: number;
    data_confidence: number | null;
    players: {
      id: number;
      full_name: string;
      position: string;
      price: number;
      team_id: number;
      teams: { name: string; abbr: string } | null;
    };
  };

  const { data: rows, error } = algorithmVersionId && gameweek
    ? await supabase
        .from("projections")
        .select(
          "total_points, data_confidence, players!inner(id, full_name, position, price, team_id, teams!team_id(name, abbr))"
        )
        .eq("horizon", horizon)
        .eq("gameweek", gameweek)
        .eq("algorithm_version_id", algorithmVersionId)
        .order("total_points", { ascending: false })
    : { data: [], error: null };
  if (error) throw new Error(`Failed to load projections: ${error.message}`);

  const { data: fixtureRows } = gameweek
    ? await supabase
        .from("fixtures")
        .select("home_team_id, away_team_id, kickoff_at, home:teams!home_team_id(abbr), away:teams!away_team_id(abbr)")
        .eq("gameweek", gameweek)
    : { data: [] };

  type FixtureJoin = { home_team_id: number; away_team_id: number; kickoff_at: string; home: { abbr: string } | null; away: { abbr: string } | null };
  const opponentByTeamId = new Map<number, { opponentAbbr: string; isHome: boolean; kickoffAt: string }>();
  for (const f of (fixtureRows ?? []) as unknown as FixtureJoin[]) {
    if (f.home && f.away) {
      opponentByTeamId.set(f.home_team_id, { opponentAbbr: f.away.abbr, isHome: true, kickoffAt: f.kickoff_at });
      opponentByTeamId.set(f.away_team_id, { opponentAbbr: f.home.abbr, isHome: false, kickoffAt: f.kickoff_at });
    }
  }

  const { data: allWinTotals } = await supabase
    .from("team_schedule_difficulty")
    .select("opponent_win_total")
    .not("opponent_win_total", "is", null)
    .eq("is_bye", false);
  const thresholds = computeDifficultyThresholds((allWinTotals ?? []).map((r) => Number(r.opponent_win_total)));

  const { data: currentWeekDifficulty } = gameweek
    ? await supabase
        .from("team_schedule_difficulty")
        .select("team_id, is_bye, opponent_win_total")
        .eq("gameweek", gameweek)
    : { data: [] };
  const difficultyByTeamId = new Map<number, ReturnType<typeof difficultyTier>>();
  for (const row of currentWeekDifficulty ?? []) {
    difficultyByTeamId.set(row.team_id, difficultyTier(row.opponent_win_total === null ? null : Number(row.opponent_win_total), row.is_bye, thresholds));
  }

  const players: PlayerRow[] = ((rows ?? []) as unknown as ProjectionRow[])
    .filter((r) => Number(r.players.price) > 0)
    .map((r) => {
      const opponent = opponentByTeamId.get(r.players.team_id);
      return {
        playerId: r.players.id,
        name: r.players.full_name,
        position: r.players.position,
        price: Number(r.players.price),
        team: r.players.teams?.abbr ?? "—",
        opponent: opponent ? `${opponent.isHome ? "vs" : "@"} ${opponent.opponentAbbr}` : "—",
        opponentTier: difficultyByTeamId.get(r.players.team_id) ?? null,
        totalPoints: Number(r.total_points),
        dataConfidence: r.data_confidence === null ? null : Number(r.data_confidence),
      };
    });

  return (
    <main className="mx-auto w-full min-w-0 max-w-5xl flex-1 p-4 sm:p-6">
        <p className="text-xs font-bold uppercase tracking-wide text-emerald-400">Points Per Real £m</p>
        <h1 className="text-2xl font-semibold text-navy-100">Value Finder</h1>
        <p className="mt-1 max-w-2xl text-sm text-navy-300">
          Every real active player ranked by projected points per real £m of price - cheap players who reliably produce for their price, not just the
          highest scorers overall.
        </p>

        <div className="mt-4 flex flex-wrap gap-1">
          {HORIZONS.map((h) => (
            <Link
              key={h}
              href={h === 1 ? "/value-finder" : `/value-finder?horizon=${h}`}
              className={`rounded-full px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide ${
                h === horizon ? "bg-sky-500 text-navy-950" : "bg-navy-900 text-navy-400 hover:bg-navy-800"
              }`}
            >
              {HORIZON_LABELS[h]}
            </Link>
          ))}
        </div>

        {players.length === 0 ? (
          <p className="mt-8 text-sm text-navy-400">No priced projections yet - run the pipeline to populate this gameweek.</p>
        ) : (
          <div className="mt-6">
            <RatingsTable players={players} horizon={horizon} defaultSortMode="value" />
          </div>
        )}
    </main>
  );
}
