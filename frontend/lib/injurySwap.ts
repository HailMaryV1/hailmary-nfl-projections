/**
 * injurySwap.ts
 * --------------------
 * Single-gameweek "swap an injured/inactive player out, for a legal
 * replacement from the same 28-player pool" feature on My Pool
 * (/playbook/custom) - deliberately narrower than the season planner:
 * it never touches custom_pool_players or recomputes custom_playbooks,
 * it only ever targets the real current gameweek, and every candidate
 * comes from the user's own pool (same boundary "My Pool" already
 * respects everywhere else) using the exact same budget/2-per-team
 * legality rules as playbookEngine.ts (addCount/overCap, reused, not
 * reimplemented).
 */

import type { SupabaseClient } from "@supabase/supabase-js";
import { type SlotKey, type Position, SLOT_POSITIONS, addCount, overCap, BUDGET_CAP } from "@/lib/playbookEngine";

const CONCERNING_STATUSES = new Set(["inactive", "doubtful", "injured", "questionable"]);

export type InjuryFlag = { status: string };

/**
 * Resolves each real roster player's team fixture for `gameweek` and
 * checks player_lineup_status (RotoWire/FanTeam real statuses) for a
 * concerning entry. Keyed by player name, matching the name-keyed
 * convention playbookEngine.ts already uses throughout for pool players.
 */
export async function findInjuryFlags(supabase: SupabaseClient, playerNames: string[], gameweek: number): Promise<Record<string, InjuryFlag>> {
  if (playerNames.length === 0) return {};

  const { data: playerRows } = await supabase.from("players").select("id, full_name, team_id").in("full_name", playerNames);
  if (!playerRows || playerRows.length === 0) return {};

  const teamIds = [...new Set(playerRows.map((p) => p.team_id))];
  const { data: fixtureRows } = await supabase.from("fixtures").select("id, home_team_id, away_team_id").eq("gameweek", gameweek).or(`home_team_id.in.(${teamIds.join(",")}),away_team_id.in.(${teamIds.join(",")})`);

  const fixtureIdByTeam = new Map<number, number>();
  for (const f of fixtureRows ?? []) {
    if (teamIds.includes(f.home_team_id)) fixtureIdByTeam.set(f.home_team_id, f.id);
    if (teamIds.includes(f.away_team_id)) fixtureIdByTeam.set(f.away_team_id, f.id);
  }

  const fixtureIds = [...new Set([...fixtureIdByTeam.values()])];
  if (fixtureIds.length === 0) return {};

  const playerIds = playerRows.map((p) => p.id);
  const { data: statusRows } = await supabase
    .from("player_lineup_status")
    .select("player_id, fixture_id, status, captured_at")
    .in("player_id", playerIds)
    .in("fixture_id", fixtureIds)
    .order("captured_at", { ascending: false });

  // Latest real status per player - statusRows is already newest-first, so
  // the first row seen per player_id is the one to keep.
  const latestByPlayer = new Map<number, string>();
  for (const row of statusRows ?? []) {
    if (!latestByPlayer.has(row.player_id)) latestByPlayer.set(row.player_id, row.status);
  }

  const nameById = new Map(playerRows.map((p) => [p.id, p.full_name as string]));
  const flags: Record<string, InjuryFlag> = {};
  for (const [playerId, status] of latestByPlayer) {
    if (!CONCERNING_STATUSES.has(status)) continue;
    const name = nameById.get(playerId);
    if (name) flags[name] = { status };
  }
  return flags;
}

export type ReplacementCandidate = { playerId: number; name: string; team: string; price: number; points: number };

type OtherSlotInfo = { name: string; team: string };

async function loadEligibleCandidates(
  supabase: SupabaseClient,
  poolId: number,
  gameweek: number,
  slot: SlotKey,
  outgoingName: string,
  outgoingPrice: number,
  weekCost: number,
  otherSlots: OtherSlotInfo[]
): Promise<ReplacementCandidate[]> {
  const { data: poolRows } = await supabase
    .from("custom_pool_players")
    .select("players!inner(id, full_name, position, price, team_id, teams!team_id(abbr))")
    .eq("pool_id", poolId);
  if (!poolRows || poolRows.length === 0) return [];

  type Row = { players: { id: number; full_name: string; position: Position; price: number; team_id: number; teams: { abbr: string } | null } };
  const eligiblePositions = SLOT_POSITIONS[slot];
  const excludeNames = new Set([outgoingName, ...otherSlots.map((s) => s.name)]);
  const poolPlayers = ((poolRows ?? []) as unknown as Row[])
    .map((r) => r.players)
    .filter((p) => eligiblePositions.includes(p.position) && !excludeNames.has(p.full_name));
  if (poolPlayers.length === 0) return [];

  const { data: latestVersionRow } = await supabase.from("algorithm_versions").select("id").order("id", { ascending: false }).limit(1).maybeSingle();
  const algorithmVersionId = latestVersionRow?.id;
  if (!algorithmVersionId) return [];

  const { data: projectionRows } = await supabase
    .from("projections")
    .select("total_points, player_id")
    .eq("horizon", 1)
    .eq("gameweek", gameweek)
    .eq("algorithm_version_id", algorithmVersionId)
    .in("player_id", poolPlayers.map((p) => p.id));
  const pointsByPlayerId = new Map((projectionRows ?? []).map((r) => [r.player_id, Number(r.total_points)]));

  const baseCounts = otherSlots.reduce((counts, s) => addCount(counts, s.team), {} as Record<string, number>);
  const budgetHeadroom = BUDGET_CAP - weekCost + outgoingPrice;

  const candidates: ReplacementCandidate[] = [];
  for (const p of poolPlayers) {
    const points = pointsByPlayerId.get(p.id);
    if (points === undefined) continue; // no real current projection this gameweek - can't rank it honestly
    const team = p.teams?.abbr ?? "—";
    if (overCap(addCount(baseCounts, team))) continue;
    if (p.price > budgetHeadroom + 1e-9) continue;
    candidates.push({ playerId: p.id, name: p.full_name, team, price: Number(p.price), points });
  }
  return candidates.sort((a, b) => b.points - a.points);
}

/** Top 5 real legal replacements, for the UI. */
export async function findReplacementCandidates(
  supabase: SupabaseClient,
  poolId: number,
  gameweek: number,
  slot: SlotKey,
  outgoingName: string,
  outgoingPrice: number,
  weekCost: number,
  otherSlots: OtherSlotInfo[]
): Promise<ReplacementCandidate[]> {
  const all = await loadEligibleCandidates(supabase, poolId, gameweek, slot, outgoingName, outgoingPrice, weekCost, otherSlots);
  return all.slice(0, 5);
}

/** Re-validates a specific candidate server-side before writing the override - never trusts the client's own legality check. */
export async function isLegalReplacement(
  supabase: SupabaseClient,
  poolId: number,
  gameweek: number,
  slot: SlotKey,
  newPlayerId: number,
  outgoingName: string,
  outgoingPrice: number,
  weekCost: number,
  otherSlots: OtherSlotInfo[]
): Promise<boolean> {
  const all = await loadEligibleCandidates(supabase, poolId, gameweek, slot, outgoingName, outgoingPrice, weekCost, otherSlots);
  return all.some((c) => c.playerId === newPlayerId);
}

export type OverrideRow = { gameweek: number; slot: string; player_id: number; reason: string | null };
export type OverrideSlotInfo = { name: string; team: string; price: number; pts: number | null };
type OverrideMove = { slot: string; old: string; new: string; reason: string; pts: number };
type OverrideWeekRecord = {
  gw: number;
  roster: Record<string, OverrideSlotInfo>;
  dst: OverrideSlotInfo;
  moves: OverrideMove[];
  cost: number;
  week_points: number;
  running_total: number;
};
export type OverridablePlan = { total_points: number; weeks: OverrideWeekRecord[] };

/**
 * Merges saved single-week overrides onto the season plan for rendering -
 * never mutates custom_playbooks.plan itself. Cascades each override's
 * real points delta into every later week's running_total (a cumulative
 * sum), since the rest of that later week's roster/points are otherwise
 * unaffected by a single-week swap.
 */
export function applyPlanOverrides<T extends OverridablePlan>(plan: T, overrides: OverrideRow[], replacementInfo: Map<string, OverrideSlotInfo>): T {
  if (overrides.length === 0) return plan;

  const overridesByGw = new Map<number, OverrideRow[]>();
  for (const ov of overrides) {
    if (!overridesByGw.has(ov.gameweek)) overridesByGw.set(ov.gameweek, []);
    overridesByGw.get(ov.gameweek)!.push(ov);
  }

  let runningDelta = 0;
  const weeks = plan.weeks.map((w) => {
    const week: OverrideWeekRecord = { ...w, roster: { ...w.roster }, dst: { ...w.dst }, moves: [...w.moves] };
    for (const ov of overridesByGw.get(week.gw) ?? []) {
      const incoming = replacementInfo.get(`${ov.gameweek}:${ov.slot}`);
      if (!incoming) continue; // real current data for this player/gw failed to load - leave the saved plan as-is
      const outgoing = ov.slot === "DST" ? week.dst : week.roster[ov.slot];
      const ptsDelta = (incoming.pts ?? 0) - (outgoing.pts ?? 0);
      if (ov.slot === "DST") week.dst = incoming;
      else week.roster[ov.slot] = incoming;
      week.cost = week.cost - outgoing.price + incoming.price;
      week.week_points += ptsDelta;
      week.moves = [...week.moves, { slot: ov.slot, old: outgoing.name, new: incoming.name, reason: ov.reason ?? "Manual swap - real injury/lineup concern", pts: incoming.pts ?? 0 }];
      runningDelta += ptsDelta;
    }
    week.running_total += runningDelta;
    return week;
  });

  return { ...plan, total_points: plan.total_points + runningDelta, weeks } as T;
}
