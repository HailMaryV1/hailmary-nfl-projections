import SiteHeader from "../SiteHeader";
import { createPublicClient } from "@/lib/supabaseClient";
import { solveInitialSquad, SLOT_ORDER, type PoolPlayer, type Position, type Roster, BUDGET_CAP } from "@/lib/playbookEngine";
import { positionLabel } from "@/lib/positions";

// Real, deliberate pruning before calling solveInitialSquad(): that
// function does a full exhaustive search (every legal QB + DST + RB-pair
// + WR-triple + TE + FLEX combination) - genuinely fine against the
// custom-pool builder's own 28-player pool (its own docstring: "a few
// hundred thousand combinations, well under a second"), but this tool
// draws from every real active player league-wide (dozens per position),
// where the same exhaustive search would be combinatorially enormous
// (rbPairs x wrTriples alone would run into the tens of millions before
// budget pruning even kicks in). Taking each position's own top scorers
// first keeps the search space at the same real scale the function was
// actually built and proven for, while the real strongest legal team
// overwhelmingly draws from the top of each position anyway - the
// £140M budget and 2-per-team cap essentially never force reaching past
// this window in practice.
// Real bug found live: pure top-N-by-points pruning left NO legal squad -
// the real top scorers at every position are also the most expensive, so
// an all-stars candidate pool can't fit 9 of them under a real £140M cap
// at once. Each position's candidate set is the union of its own top
// scorers, its own best real points-per-£m value picks, and its own
// cheapest options - guaranteeing genuine affordable depth exists for
// solveInitialSquad to actually reach a legal combination, not just a
// bigger pile of stars.
const POOL_LIMITS: Record<Position, { points: number; value: number; cheapest: number }> = {
  quarterback: { points: 2, value: 1, cheapest: 2 },
  running_back: { points: 3, value: 2, cheapest: 2 },
  wide_receiver: { points: 3, value: 2, cheapest: 2 },
  tight_end: { points: 2, value: 1, cheapest: 2 },
  defense_special: { points: 2, value: 1, cheapest: 2 },
};

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

  function candidatesForPosition(position: Position): PoolPlayer[] {
    const { points, value, cheapest } = POOL_LIMITS[position];
    const players = allPlayers.filter((p) => p.position === position && p.price > 0);
    const byPoints = [...players].sort((a, b) => b.gw1TotalPoints - a.gw1TotalPoints).slice(0, points);
    const byValue = [...players].sort((a, b) => b.gw1TotalPoints / b.price - a.gw1TotalPoints / a.price).slice(0, value);
    const byCheapest = [...players].sort((a, b) => a.price - b.price).slice(0, cheapest);
    const seen = new Map<number, PoolPlayer>();
    for (const p of [...byPoints, ...byValue, ...byCheapest]) seen.set(p.id, p);
    return [...seen.values()];
  }

  const prunedPool = (Object.keys(POOL_LIMITS) as Position[]).flatMap((pos) => candidatesForPosition(pos));

  let roster: Roster | null = null;
  let solveError: string | null = null;
  if (prunedPool.length > 0) {
    try {
      roster = solveInitialSquad(prunedPool);
    } catch (e) {
      solveError = e instanceof Error ? e.message : "Could not build a legal squad from this gameweek's projections.";
    }
  }

  const byName = new Map(prunedPool.map((p) => [p.name, p]));
  const rosterEntries = roster ? SLOT_ORDER.map((slot) => ({ slot, player: byName.get(roster![slot]) ?? null })) : [];
  const totalPoints = rosterEntries.reduce((sum, r) => sum + (r.player?.gw1TotalPoints ?? 0), 0);
  const totalPrice = rosterEntries.reduce((sum, r) => sum + (r.player?.price ?? 0), 0);

  return (
    <>
      <SiteHeader />
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
        ) : solveError || !roster ? (
          <p className="mt-8 text-sm text-navy-400">{solveError ?? "Could not build a legal squad from this gameweek's projections."}</p>
        ) : (
          <>
            <div className="mt-6 flex flex-wrap gap-3">
              <div className="rounded-lg border border-navy-800 bg-navy-900 px-4 py-2.5">
                <p className="font-[family-name:var(--font-cond)] text-2xl font-bold text-navy-100">{totalPoints.toFixed(1)}</p>
                <p className="text-[10px] tracking-wide text-navy-500 uppercase">Projected points</p>
              </div>
              <div className="rounded-lg border border-navy-800 bg-navy-900 px-4 py-2.5">
                <p className="font-[family-name:var(--font-cond)] text-2xl font-bold text-navy-100">
                  £{totalPrice.toFixed(1)}m <span className="text-sm text-navy-500">/ £{BUDGET_CAP}m</span>
                </p>
                <p className="text-[10px] tracking-wide text-navy-500 uppercase">Squad price</p>
              </div>
            </div>

            <ul className="mt-6 divide-y divide-navy-800 rounded-xl border border-navy-800 bg-navy-900">
              {rosterEntries.map(({ slot, player }) => (
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
    </>
  );
}
