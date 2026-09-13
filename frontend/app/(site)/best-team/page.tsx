import { createPublicClient } from "@/lib/supabaseClient";
import { type PoolPlayer, type Position, BUDGET_CAP } from "@/lib/playbookEngine";
import { buildBestTeam } from "@/lib/bestTeam";
import { positionLabel } from "@/lib/positions";

export default async function BestTeamPage() {
  const supabase = createPublicClient();

  const { data: latestVersionRow } = await supabase.from("algorithm_versions").select("id").order("id", { ascending: false }).limit(1).maybeSingle();
  const algorithmVersionId = latestVersionRow?.id;

  const { data: gwRow } = algorithmVersionId
    ? await supabase.from("projections").select("gameweek").eq("horizon", 1).eq("algorithm_version_id", algorithmVersionId).order("gameweek", { ascending: false }).limit(1).maybeSingle()
    : { data: null };
  const gameweek = gwRow?.gameweek;

  type ProjectionRow = {
    total_points: number;
    players: { id: number; full_name: string; position: Position; price: number; team_id: number; teams: { name: string; abbr: string } | null };
  };

  const { data: rows, error } = algorithmVersionId && gameweek
    ? await supabase
        .from("projections")
        .select("total_points, players!inner(id, full_name, position, price, team_id, teams!team_id(name, abbr))")
        .eq("horizon", 1)
        .eq("gameweek", gameweek)
        .eq("algorithm_version_id", algorithmVersionId)
    : { data: [], error: null };
  if (error) throw new Error(`Failed to load projections: ${error.message}`);

  const allPlayers: PoolPlayer[] = ((rows ?? []) as unknown as ProjectionRow[]).map((r) => ({
    id: r.players.id,
    name: r.players.full_name,
    position: r.players.position,
    price: Number(r.players.price),
    teamId: r.players.team_id,
    teamAbbr: r.players.teams?.abbr ?? "—",
    tier: "any", // unused by solveInitialSquad's own search - only meaningful to the custom-pool builder's tier grouping.
    gw1TotalPoints: Number(r.total_points),
  }));

  const { result, error: solveError } = buildBestTeam(allPlayers);

  return (
    <main className="mx-auto w-full min-w-0 max-w-3xl flex-1 p-4 sm:p-6">
        <p className="text-xs font-bold uppercase tracking-wide text-sky-400">Single-Gameweek Optimal Roster</p>
        <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">Best Team</h1>
        <p className="mt-2 max-w-2xl text-sm text-navy-300">
          The strongest real legal roster this gameweek allows{gameweek ? `, for Gameweek ${gameweek}` : ""} - every real active player, real prices, the
          real £{BUDGET_CAP}M cap and 2-per-team limit. A snapshot for right now, not a season plan - see My Pool for an 18-week strategy built around your
          own picks.
        </p>

        {allPlayers.length === 0 ? (
          <p className="mt-8 text-sm text-navy-400">No projections yet - run the pipeline to populate this gameweek.</p>
        ) : solveError || !result ? (
          <p className="mt-8 text-sm text-navy-400">{solveError ?? "Could not build a legal squad from this gameweek's projections."}</p>
        ) : (
          <>
            <div className="mt-6 flex flex-wrap gap-3">
              <div className="rounded-lg border border-navy-800 bg-navy-900 px-4 py-2.5">
                <p className="font-[family-name:var(--font-cond)] text-2xl font-bold text-navy-100">{result.totalPoints.toFixed(1)}</p>
                <p className="text-[10px] tracking-wide text-navy-500 uppercase">Projected points</p>
              </div>
              <div className="rounded-lg border border-navy-800 bg-navy-900 px-4 py-2.5">
                <p className="font-[family-name:var(--font-cond)] text-2xl font-bold text-navy-100">
                  £{result.totalPrice.toFixed(1)}m <span className="text-sm text-navy-500">/ £{BUDGET_CAP}m</span>
                </p>
                <p className="text-[10px] tracking-wide text-navy-500 uppercase">Squad price</p>
              </div>
            </div>

            <ul className="mt-6 divide-y divide-navy-800 rounded-xl border border-navy-800 bg-navy-900">
              {result.rosterEntries.map(({ slot, player }) => (
                <li key={slot} className="flex items-center justify-between gap-3 px-4 py-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="w-12 shrink-0 font-[family-name:var(--font-cond)] text-xs font-bold tracking-wide text-navy-500 uppercase">{slot}</span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-navy-100">{player?.name ?? "—"}</p>
                      <p className="text-xs text-navy-500">
                        {player ? `${player.teamAbbr} · ${positionLabel(player.position)} · £${player.price}m` : "—"}
                      </p>
                    </div>
                  </div>
                  <span className="shrink-0 font-mono text-sm font-bold text-sky-300">{player ? player.gw1TotalPoints.toFixed(1) : "—"}</span>
                </li>
              ))}
            </ul>
          </>
        )}
    </main>
  );
}
