import { solveInitialSquad, SLOT_ORDER, type PoolPlayer, type Position, type Roster } from "@/lib/playbookEngine";

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
//
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

function candidatesForPosition(allPlayers: PoolPlayer[], position: Position): PoolPlayer[] {
  const { points, value, cheapest } = POOL_LIMITS[position];
  const players = allPlayers.filter((p) => p.position === position && p.price > 0);
  const byPoints = [...players].sort((a, b) => b.gw1TotalPoints - a.gw1TotalPoints).slice(0, points);
  const byValue = [...players].sort((a, b) => b.gw1TotalPoints / b.price - a.gw1TotalPoints / a.price).slice(0, value);
  const byCheapest = [...players].sort((a, b) => a.price - b.price).slice(0, cheapest);
  const seen = new Map<number, PoolPlayer>();
  for (const p of [...byPoints, ...byValue, ...byCheapest]) seen.set(p.id, p);
  return [...seen.values()];
}

export type BestTeamResult = {
  rosterEntries: { slot: (typeof SLOT_ORDER)[number]; player: PoolPlayer | null }[];
  totalPoints: number;
  totalPrice: number;
};

/** Shared by /best-team and the homepage showcase - see POOL_LIMITS above
 * for why this doesn't just call solveInitialSquad() on the full pool. */
export function buildBestTeam(allPlayers: PoolPlayer[]): { result: BestTeamResult | null; error: string | null } {
  const prunedPool = (Object.keys(POOL_LIMITS) as Position[]).flatMap((pos) => candidatesForPosition(allPlayers, pos));
  if (prunedPool.length === 0) return { result: null, error: null };

  let roster: Roster;
  try {
    roster = solveInitialSquad(prunedPool);
  } catch (e) {
    return { result: null, error: e instanceof Error ? e.message : "Could not build a legal squad from this gameweek's projections." };
  }

  const byName = new Map(prunedPool.map((p) => [p.name, p]));
  const rosterEntries = SLOT_ORDER.map((slot) => ({ slot, player: byName.get(roster[slot]) ?? null }));
  const totalPoints = rosterEntries.reduce((sum, r) => sum + (r.player?.gw1TotalPoints ?? 0), 0);
  const totalPrice = rosterEntries.reduce((sum, r) => sum + (r.player?.price ?? 0), 0);
  return { result: { rosterEntries, totalPoints, totalPrice }, error: null };
}
