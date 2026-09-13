"use server";

import { revalidatePath } from "next/cache";
import { createAuthServerClient } from "@/lib/supabaseServerClient";
import { createPublicClient } from "@/lib/supabaseClient";
import { POOL_SPEC } from "@/lib/poolSpec";
import {
  type PoolPlayer, type Position, type Tier, type ScheduleByTeam,
  buildEstimates, solveInitialSquad, findBestWildcardWeek, runScenario, SLOT_ORDER,
} from "@/lib/playbookEngine";

type Selection = { playerId: number; position: Position; tier: Tier };

export async function buildPool(selections: Selection[]): Promise<{ ok: true } | { error: string }> {
  const authClient = await createAuthServerClient();
  const {
    data: { user },
  } = await authClient.auth.getUser();
  if (!user) return { error: "Not signed in." };

  // Never trust the client's counts - re-validate the exact real tier
  // structure server-side (see poolSpec.ts for why these exact counts
  // guarantee a legal squad exists).
  for (const pos of Object.keys(POOL_SPEC) as Position[]) {
    for (const t of POOL_SPEC[pos].tiers) {
      const have = selections.filter((s) => s.position === pos && s.tier === t.tier).length;
      if (have !== t.count) {
        return { error: `${POOL_SPEC[pos].label} ${t.label}: need exactly ${t.count}, got ${have}.` };
      }
    }
  }
  const ids = selections.map((s) => s.playerId);
  if (new Set(ids).size !== ids.length) return { error: "Duplicate player in selection." };

  const publicClient = createPublicClient();

  const { data: latestVersionRow } = await publicClient.from("algorithm_versions").select("id").order("id", { ascending: false }).limit(1).maybeSingle();
  const algorithmVersionId = latestVersionRow?.id;
  if (!algorithmVersionId) return { error: "No projections available yet." };

  const { data: rows, error: playersError } = await publicClient
    .from("projections")
    .select("total_points, players!inner(id, full_name, position, price, team_id, teams!team_id(abbr))")
    .eq("horizon", 1)
    .eq("algorithm_version_id", algorithmVersionId)
    .in("players.id", ids);
  if (playersError) return { error: `Failed to load real player data: ${playersError.message}` };

  type Row = {
    total_points: number;
    players: { id: number; full_name: string; position: Position; price: number; team_id: number; teams: { abbr: string } | null };
  };
  const tierByPlayerId = new Map(selections.map((s) => [s.playerId, s.tier]));
  const pool: PoolPlayer[] = ((rows ?? []) as unknown as Row[]).map((r) => ({
    id: r.players.id,
    name: r.players.full_name,
    position: r.players.position,
    price: Number(r.players.price),
    teamId: r.players.team_id,
    teamAbbr: r.players.teams?.abbr ?? "—",
    tier: tierByPlayerId.get(r.players.id) ?? "any",
    gw1TotalPoints: Number(r.total_points),
  }));
  if (pool.length !== 28) return { error: `Expected 28 real players, found ${pool.length} - one or more picks may be missing a current projection.` };

  const { data: winTotalRows } = await publicClient.from("team_schedule_difficulty").select("opponent_win_total").not("opponent_win_total", "is", null).eq("is_bye", false);
  const winTotals = (winTotalRows ?? []).map((r) => Number(r.opponent_win_total));
  const leagueMean = winTotals.reduce((a, b) => a + b, 0) / winTotals.length;
  const leagueStd = Math.sqrt(winTotals.reduce((s, v) => s + (v - leagueMean) ** 2, 0) / winTotals.length);

  const teamIds = [...new Set(pool.map((p) => p.teamId))];
  const { data: scheduleRows } = await publicClient
    .from("team_schedule_difficulty")
    .select("team_id, gameweek, is_bye, opponent_win_total")
    .in("team_id", teamIds)
    .lte("gameweek", 18);
  const schedule: ScheduleByTeam = new Map();
  for (const r of scheduleRows ?? []) {
    if (!schedule.has(r.team_id)) schedule.set(r.team_id, new Map());
    schedule.get(r.team_id)!.set(r.gameweek, { gameweek: r.gameweek, isBye: r.is_bye, opponentWinTotal: r.opponent_win_total === null ? null : Number(r.opponent_win_total) });
  }

  const est = buildEstimates(pool, schedule, leagueMean, leagueStd);

  let initialRoster;
  try {
    initialRoster = solveInitialSquad(pool);
  } catch (e) {
    return { error: `Could not build a legal starting squad from this pool: ${(e as Error).message}` };
  }

  const { gw: wildcardGw, total: totalPoints } = findBestWildcardWeek(pool, est, initialRoster);
  const { weeks } = runScenario(pool, est, initialRoster, wildcardGw);

  const byName = new Map(pool.map((p) => [p.name, p]));
  const planWeeks = weeks.map((w) => {
    const roster: Record<string, { name: string; team: string; price: number; pts: number | null }> = {};
    for (const slot of SLOT_ORDER) {
      if (slot === "DST") continue;
      const p = byName.get(w.roster[slot])!;
      roster[slot] = { name: p.name, team: p.teamAbbr, price: p.price, pts: est.get(p.name)?.get(w.gw) ?? null };
    }
    const dstPlayer = byName.get(w.roster.DST)!;
    return {
      gw: w.gw,
      is_wildcard: w.isWildcard,
      roster,
      dst: { name: dstPlayer.name, team: dstPlayer.teamAbbr, price: dstPlayer.price, pts: est.get(dstPlayer.name)?.get(w.gw) ?? null },
      moves: w.moves.map((m) => ({ slot: m.slot, old: m.oldName, new: m.newName, reason: m.reason, pts: m.pts })),
      transfers_used: w.transfersUsed,
      transfers_available: w.transfersAvailable,
      extra_paid: w.extraPaid,
      banked_after: w.bankedAfter,
      cost: w.cost,
      team_counts: w.teamCounts,
      week_points: w.weekPoints,
      running_total: w.runningTotal,
    };
  });
  const extraTransferWeeks = weeks.filter((w) => w.extraPaid > 0).map((w) => w.gw);
  const plan = { total_points: totalPoints, extra_transfer_weeks: extraTransferWeeks, weeks: planWeeks };

  // Get-or-create this user's pool (one pool per user for now - a real
  // "multiple named pools" feature is a later, separate decision).
  const { data: existingPool } = await authClient.from("custom_pools").select("id").eq("user_id", user.id).order("updated_at", { ascending: false }).limit(1).maybeSingle();

  let poolId: number;
  if (existingPool) {
    poolId = existingPool.id;
    const { error: touchError } = await authClient.from("custom_pools").update({ updated_at: new Date().toISOString() }).eq("id", poolId);
    if (touchError) return { error: `Failed to update pool: ${touchError.message}` };
    const { error: deleteError } = await authClient.from("custom_pool_players").delete().eq("pool_id", poolId);
    if (deleteError) return { error: `Failed to clear old pool players: ${deleteError.message}` };
  } else {
    const { data: created, error: createError } = await authClient.from("custom_pools").insert({ user_id: user.id }).select("id").single();
    if (createError || !created) return { error: `Failed to create pool: ${createError?.message}` };
    poolId = created.id;
  }

  const { error: insertPlayersError } = await authClient
    .from("custom_pool_players")
    .insert(selections.map((s) => ({ pool_id: poolId, player_id: s.playerId, position: s.position, tier: s.tier })));
  if (insertPlayersError) return { error: `Failed to save pool players: ${insertPlayersError.message}` };

  const { error: insertPlaybookError } = await authClient.from("custom_playbooks").insert({
    pool_id: poolId,
    algorithm_version_id: algorithmVersionId,
    total_points: totalPoints,
    wildcard_gameweek: wildcardGw,
    extra_transfer_weeks: extraTransferWeeks,
    plan,
  });
  if (insertPlaybookError) return { error: `Failed to save playbook: ${insertPlaybookError.message}` };

  revalidatePath("/playbook/builder");
  revalidatePath("/playbook/custom");
  return { ok: true };
}
