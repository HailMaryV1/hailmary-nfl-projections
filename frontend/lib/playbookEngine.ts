/**
 * playbookEngine.ts
 * --------------------
 * TypeScript port of scripts/plan_optimal_playbook.py's real 18-week
 * squad-planning algorithm, restricted to a fixed user-chosen pool of
 * players (28: 4 QB / 8 RB / 8 WR / 4 TE / 4 DST, picked across real
 * price tiers so a legal <=£140M squad always exists - see the migration
 * that created custom_pools for the real worst-case-floor arithmetic).
 *
 * Ported to TypeScript (not called out to the Python scripts) so this can
 * run live, server-side, in the same request that built the pool - a few
 * hundred milliseconds for a 28-player/18-week run, well inside a normal
 * request. Every real number this produces (fixture-adjusted points,
 * budget, transfers) uses the exact same methodology as the two built-in
 * playbooks: a player's real GW1 (horizon=1) total_points has that week's
 * real fixture-quality multiplier baked in; dividing it back out recovers
 * a real "fixture-neutral" baseline, which is then re-multiplied by the
 * same real fixture_quality_multiplier() for whatever gameweek is being
 * evaluated. A team's real bye week zeroes that week outright.
 *
 * Real, deliberate difference from the two built-in playbooks: DST is a
 * full rotating slot here (forced-bye and discretionary-upgrade logic
 * both apply to it), not held fixed all season - the user's pool only
 * has 4 real DST options, small enough that rotating properly costs
 * nothing and is simply more correct.
 *
 * Unlike scripts/plan_optimal_playbook.py's full-board version, there is
 * NO fallback outside the pool when a slot gets stuck (no legal
 * replacement) - reaching outside the user's own 28 players would defeat
 * the entire point of a custom pool. A stuck slot is reported plainly
 * (scores 0 that week) so the person can see exactly where their pool
 * ran out of road.
 */

export const BUDGET_CAP = 140.0;
export const MAX_PER_TEAM = 2;
export const FREE_TRANSFERS_PER_GW = 2;
export const BANK_CAP = 34;
export const EXTRA_TRANSFER_COST = 8;
export const UPGRADE_THRESHOLD = 2.0;
export const SEASON_LENGTH = 18;

export type Position = "quarterback" | "running_back" | "wide_receiver" | "tight_end" | "defense_special";
export type Tier = "premium" | "mid" | "value" | "any";

export type PoolPlayer = {
  id: number;
  name: string;
  position: Position;
  price: number;
  teamId: number;
  teamAbbr: string;
  tier: Tier;
  gw1TotalPoints: number;
};

export type ScheduleRow = { gameweek: number; isBye: boolean; opponentWinTotal: number | null };
/** teamId -> gameweek -> row */
export type ScheduleByTeam = Map<number, Map<number, ScheduleRow>>;

const SLOT_KEYS = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX", "DST"] as const;
export type SlotKey = (typeof SLOT_KEYS)[number];

const SLOT_POSITIONS: Record<SlotKey, Position[]> = {
  QB: ["quarterback"],
  RB1: ["running_back"],
  RB2: ["running_back"],
  WR1: ["wide_receiver"],
  WR2: ["wide_receiver"],
  WR3: ["wide_receiver"],
  TE: ["tight_end"],
  FLEX: ["running_back", "wide_receiver", "tight_end"],
  DST: ["defense_special"],
};

export function fixtureQualityMultiplier(opponentWinTotal: number, leagueMean: number, leagueStd: number, k = 0.15): number {
  if (leagueStd <= 0) return 1.0;
  const z = (opponentWinTotal - leagueMean) / leagueStd;
  const multiplier = 1 - k * z;
  return Math.max(0.7, Math.min(1.3, multiplier));
}

function neutralBaseline(gw1TotalPoints: number, teamId: number, schedule: ScheduleByTeam, leagueMean: number, leagueStd: number): number {
  const gw1Row = schedule.get(teamId)?.get(1);
  const gw1Wt = gw1Row?.opponentWinTotal ?? leagueMean;
  const gw1Mult = fixtureQualityMultiplier(gw1Wt, leagueMean, leagueStd);
  return gw1Mult ? gw1TotalPoints / gw1Mult : gw1TotalPoints;
}

function estimateForGw(base: number, teamId: number, gw: number, schedule: ScheduleByTeam, leagueMean: number, leagueStd: number): number | null {
  const row = schedule.get(teamId)?.get(gw);
  if (!row) return null;
  if (row.isBye) return 0.0;
  const wt = row.opponentWinTotal ?? leagueMean;
  return Math.round(base * fixtureQualityMultiplier(wt, leagueMean, leagueStd) * 10) / 10;
}

/** name -> gw -> points (0 on a real bye, null if no schedule data) */
export type EstimateMap = Map<string, Map<number, number | null>>;

export function buildEstimates(pool: PoolPlayer[], schedule: ScheduleByTeam, leagueMean: number, leagueStd: number): EstimateMap {
  const est: EstimateMap = new Map();
  for (const p of pool) {
    const base = neutralBaseline(p.gw1TotalPoints, p.teamId, schedule, leagueMean, leagueStd);
    const perGw = new Map<number, number | null>();
    for (let gw = 1; gw <= SEASON_LENGTH; gw++) {
      perGw.set(gw, estimateForGw(base, p.teamId, gw, schedule, leagueMean, leagueStd));
    }
    est.set(p.name, perGw);
  }
  return est;
}

type Roster = Record<SlotKey, string>; // slot -> player name

function squadCost(roster: Roster, byName: Map<string, PoolPlayer>): number {
  return SLOT_KEYS.reduce((sum, slot) => sum + byName.get(roster[slot])!.price, 0);
}

function teamCounts(roster: Roster, byName: Map<string, PoolPlayer>): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const slot of SLOT_KEYS) {
    const abbr = byName.get(roster[slot])!.teamAbbr;
    counts[abbr] = (counts[abbr] ?? 0) + 1;
  }
  return counts;
}

function validAfterSwap(roster: Roster, byName: Map<string, PoolPlayer>, slot: SlotKey, candidateName: string): boolean {
  const trial: Roster = { ...roster, [slot]: candidateName };
  const names = new Set(SLOT_KEYS.map((s) => trial[s]));
  if (names.size < SLOT_KEYS.length) return false; // duplicate player across slots
  if (squadCost(trial, byName) > BUDGET_CAP + 1e-9) return false;
  const counts = teamCounts(trial, byName);
  if (Object.values(counts).some((c) => c > MAX_PER_TEAM)) return false;
  return true;
}

/** Real fantasy-optimizer heuristic: best-slot-ignoring-budget, then
 * repeatedly downgrade whichever swap loses the fewest real points per
 * pound saved until under the real budget cap. Pool-only - the pool's
 * own tier structure guarantees a legal squad exists. */
export function solveInitialSquad(pool: PoolPlayer[]): Roster {
  const byName = new Map(pool.map((p) => [p.name, p]));
  const byPosition = new Map<Position, PoolPlayer[]>();
  for (const p of pool) {
    const list = byPosition.get(p.position) ?? [];
    list.push(p);
    byPosition.set(p.position, list);
  }
  for (const list of byPosition.values()) list.sort((a, b) => b.gw1TotalPoints - a.gw1TotalPoints);

  const used = new Set<string>();
  const counts: Record<string, number> = {};
  const roster = {} as Roster;

  function pickBest(candidates: PoolPlayer[]): PoolPlayer {
    const pick = candidates.find((p) => !used.has(p.name) && (counts[p.teamAbbr] ?? 0) < MAX_PER_TEAM);
    if (!pick) throw new Error("Pool exhausted while building the initial squad - this should not happen with a real 28-player pool.");
    return pick;
  }

  for (const slot of SLOT_KEYS) {
    if (slot === "FLEX") continue;
    const positions = SLOT_POSITIONS[slot];
    const pick = pickBest(byPosition.get(positions[0]) ?? []);
    roster[slot] = pick.name;
    used.add(pick.name);
    counts[pick.teamAbbr] = (counts[pick.teamAbbr] ?? 0) + 1;
  }
  const flexPool = [...(byPosition.get("running_back") ?? []), ...(byPosition.get("wide_receiver") ?? []), ...(byPosition.get("tight_end") ?? [])].sort(
    (a, b) => b.gw1TotalPoints - a.gw1TotalPoints
  );
  const flexPick = pickBest(flexPool);
  roster.FLEX = flexPick.name;
  used.add(flexPick.name);
  counts[flexPick.teamAbbr] = (counts[flexPick.teamAbbr] ?? 0) + 1;

  function slotPool(slot: SlotKey): PoolPlayer[] {
    return slot === "FLEX" ? flexPool : byPosition.get(SLOT_POSITIONS[slot][0]) ?? [];
  }

  let cost = squadCost(roster, byName);
  let guard = 0;
  while (cost > BUDGET_CAP + 1e-9) {
    if (++guard > 200) throw new Error("Could not reach budget even with the pool's cheapest options - this should not happen given the tier guarantee.");
    let best: { ratio: number; slot: SlotKey; candidate: PoolPlayer } | null = null;
    for (const slot of SLOT_KEYS) {
      const current = byName.get(roster[slot])!;
      for (const cand of slotPool(slot)) {
        if (cand.name === current.name || used.has(cand.name) || cand.price >= current.price) continue;
        if (!validAfterSwap(roster, byName, slot, cand.name)) continue;
        const loss = current.gw1TotalPoints - cand.gw1TotalPoints;
        const saved = current.price - cand.price;
        const ratio = loss / saved;
        if (!best || ratio < best.ratio) best = { ratio, slot, candidate: cand };
      }
    }
    if (!best) throw new Error("No legal downgrade found - the pool cannot reach £140M even using its cheapest tier picks.");
    const old = roster[best.slot];
    used.delete(old);
    used.add(best.candidate.name);
    roster[best.slot] = best.candidate.name;
    cost = squadCost(roster, byName);
  }

  return roster;
}

function poolAlternative(
  slot: SlotKey, roster: Roster, byName: Map<string, PoolPlayer>, pool: PoolPlayer[], est: EstimateMap, gw: number, exclude: Set<string>
): { pts: number; name: string } | null {
  const positions = SLOT_POSITIONS[slot];
  const current = roster[slot];
  let best: { pts: number; name: string } | null = null;
  for (const p of pool) {
    if (!positions.includes(p.position) || p.name === current || exclude.has(p.name)) continue;
    const pts = est.get(p.name)?.get(gw);
    if (pts === null || pts === undefined) continue;
    if (!validAfterSwap(roster, byName, slot, p.name)) continue;
    if (!best || pts > best.pts) best = { pts, name: p.name };
  }
  return best;
}

export type Move = { slot: SlotKey; oldName: string; newName: string; reason: string; pts: number };
export type WeekResult = {
  gw: number;
  isWildcard: boolean;
  roster: Roster;
  moves: Move[];
  transfersUsed: number;
  transfersAvailable: number | null;
  extraPaid: number;
  bankedAfter: number;
  cost: number;
  teamCounts: Record<string, number>;
  weekPoints: number;
  runningTotal: number;
};

export function runScenario(pool: PoolPlayer[], est: EstimateMap, initialRoster: Roster, wildcardGw: number | null) {
  const byName = new Map(pool.map((p) => [p.name, p]));
  let roster: Roster = { ...initialRoster };
  let banked = 0;
  let totalPoints = 0;
  const weeks: WeekResult[] = [];

  for (let gw = 1; gw <= SEASON_LENGTH; gw++) {
    const moves: Move[] = [];
    const exclude = new Set<string>();
    const isWildcard = gw === wildcardGw;

    let available: number;
    if (gw === 1) available = 0;
    else if (isWildcard) available = 10_000;
    else available = Math.min(BANK_CAP, banked) + FREE_TRANSFERS_PER_GW;

    let used = 0;

    if (gw > 1) {
      for (const slot of SLOT_KEYS) {
        const name = roster[slot];
        if (est.get(name)?.get(gw) === 0) {
          const alt = poolAlternative(slot, roster, byName, pool, est, gw, exclude);
          if (alt) {
            moves.push({ slot, oldName: name, newName: alt.name, reason: "real bye - forced out", pts: alt.pts });
            roster[slot] = alt.name;
            exclude.add(alt.name);
            used += 1;
          } else {
            moves.push({ slot, oldName: name, newName: name, reason: "STUCK - real bye, no legal replacement in your pool (scores 0 this week)", pts: 0 });
          }
        }
      }

      const threshold = isWildcard ? 0 : UPGRADE_THRESHOLD;
      while (used < available) {
        let best: { gain: number; slot: SlotKey; name: string; pts: number } | null = null;
        for (const slot of SLOT_KEYS) {
          const currentPts = est.get(roster[slot])?.get(gw) ?? 0;
          const alt = poolAlternative(slot, roster, byName, pool, est, gw, exclude);
          if (!alt) continue;
          const gain = alt.pts - currentPts;
          if (gain > threshold && (!best || gain > best.gain)) best = { gain, slot, name: alt.name, pts: alt.pts };
        }
        if (!best) break;
        const reason = isWildcard ? "Wildcard - free reshuffle" : `real upgrade (+${best.gain.toFixed(1)}pts)`;
        moves.push({ slot: best.slot, oldName: roster[best.slot], newName: best.name, reason, pts: best.pts });
        roster[best.slot] = best.name;
        exclude.add(best.name);
        used += 1;
      }
    }

    const extra = isWildcard ? 0 : gw > 1 ? Math.max(0, used - available) : 0;
    banked = isWildcard ? 0 : gw > 1 ? Math.min(BANK_CAP, Math.max(0, available - used)) : 0;

    let weekPoints = 0;
    for (const slot of SLOT_KEYS) weekPoints += est.get(roster[slot])?.get(gw) ?? 0;
    weekPoints -= extra * EXTRA_TRANSFER_COST;
    totalPoints += weekPoints;

    weeks.push({
      gw, isWildcard, roster: { ...roster }, moves,
      transfersUsed: used, transfersAvailable: gw > 1 && !isWildcard ? available : null,
      extraPaid: extra, bankedAfter: banked,
      cost: squadCost(roster, byName), teamCounts: teamCounts(roster, byName),
      weekPoints, runningTotal: totalPoints,
    });
  }

  return { totalPoints, weeks };
}

export function findBestWildcardWeek(pool: PoolPlayer[], est: EstimateMap, initialRoster: Roster) {
  const baseline = runScenario(pool, est, initialRoster, null);
  let best = { gw: null as number | null, total: baseline.totalPoints, gain: 0 };
  for (let gw = 2; gw <= SEASON_LENGTH; gw++) {
    const { totalPoints } = runScenario(pool, est, initialRoster, gw);
    if (totalPoints - baseline.totalPoints > best.gain) {
      best = { gw, total: totalPoints, gain: totalPoints - baseline.totalPoints };
    }
  }
  return { baselineTotal: baseline.totalPoints, ...best };
}

export const SLOT_ORDER = SLOT_KEYS;
