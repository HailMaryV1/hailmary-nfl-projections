import Link from "next/link";
import SiteHeader from "./SiteHeader";
import RatingsTable, { type PlayerRow } from "./RatingsTable";
import { createPublicClient } from "@/lib/supabaseClient";

const HORIZONS = [1, 2, 3, 5];
const HORIZON_LABELS: Record<number, string> = { 1: "This Week", 2: "Next 2", 3: "Next 3", 5: "Next 5" };

export default async function Home({ searchParams }: { searchParams: Promise<{ horizon?: string }> }) {
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

  // Always keyed off horizon 1's own gameweek - every horizon in a given
  // pipeline run shares the same starting gameweek (see
  // compute_projections.py), and horizon 1 is the one guaranteed to exist.
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

  const players: PlayerRow[] = ((rows ?? []) as unknown as ProjectionRow[]).map((r) => {
    const opponent = opponentByTeamId.get(r.players.team_id);
    return {
      playerId: r.players.id,
      name: r.players.full_name,
      position: r.players.position,
      price: Number(r.players.price),
      team: r.players.teams?.abbr ?? "—",
      opponent: opponent ? `${opponent.isHome ? "vs" : "@"} ${opponent.opponentAbbr}` : "—",
      totalPoints: Number(r.total_points),
      dataConfidence: r.data_confidence === null ? null : Number(r.data_confidence),
    };
  });

  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full min-w-0 max-w-5xl flex-1 p-4 sm:p-6">
        <h1 className="text-2xl font-semibold text-navy-100">Projections</h1>
        <p className="mt-1 max-w-2xl text-sm text-navy-300">
          Real Projected Points for FanTeam&apos;s NFL Regular Season 2026/27{gameweek ? `, from Gameweek ${gameweek}` : ""}.
          {horizon > 1 && " Weeks beyond the current one are a real but coarser estimate - see a player's own page for how it's built."}
        </p>

        <div className="mt-4 flex flex-wrap gap-1">
          {HORIZONS.map((h) => (
            <Link
              key={h}
              href={h === 1 ? "/" : `/?horizon=${h}`}
              className={`rounded-full px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide ${
                h === horizon ? "bg-sky-500 text-navy-950" : "bg-navy-900 text-navy-400 hover:bg-navy-800"
              }`}
            >
              {HORIZON_LABELS[h]}
            </Link>
          ))}
        </div>

        {players.length === 0 ? (
          <p className="mt-8 text-sm text-navy-400">No projections yet - run the pipeline to populate this gameweek.</p>
        ) : (
          <div className="mt-6">
            <RatingsTable players={players} horizon={horizon} />
          </div>
        )}
      </main>
    </>
  );
}
