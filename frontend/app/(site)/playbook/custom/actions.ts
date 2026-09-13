"use server";

import { revalidatePath } from "next/cache";
import { createAuthServerClient } from "@/lib/supabaseServerClient";
import { type SlotKey } from "@/lib/playbookEngine";
import { isLegalReplacement, findReplacementCandidates, type ReplacementCandidate } from "@/lib/injurySwap";

type OtherSlotInfo = { name: string; team: string };

async function assertOwnPool(poolId: number) {
  const supabase = await createAuthServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { supabase: null, error: "Not signed in." } as const;

  const { data: pool } = await supabase.from("custom_pools").select("id").eq("id", poolId).eq("user_id", user.id).maybeSingle();
  if (!pool) return { supabase: null, error: "Pool not found." } as const;

  return { supabase, error: null } as const;
}

export async function loadReplacementCandidates(
  poolId: number,
  gameweek: number,
  slot: SlotKey,
  outgoingName: string,
  outgoingPrice: number,
  weekCost: number,
  otherSlots: OtherSlotInfo[]
): Promise<{ candidates: ReplacementCandidate[] } | { error: string }> {
  const { supabase, error } = await assertOwnPool(poolId);
  if (!supabase) return { error: error! };

  const candidates = await findReplacementCandidates(supabase, poolId, gameweek, slot, outgoingName, outgoingPrice, weekCost, otherSlots);
  return { candidates };
}

export async function applySwap(
  poolId: number,
  gameweek: number,
  slot: SlotKey,
  newPlayerId: number,
  outgoingName: string,
  outgoingPrice: number,
  weekCost: number,
  otherSlots: OtherSlotInfo[]
): Promise<{ ok: true } | { error: string }> {
  const { supabase, error } = await assertOwnPool(poolId);
  if (!supabase) return { error: error! };

  const legal = await isLegalReplacement(supabase, poolId, gameweek, slot, newPlayerId, outgoingName, outgoingPrice, weekCost, otherSlots);
  if (!legal) return { error: "That player is no longer a legal replacement (budget, 2-per-team cap, or pool membership has changed)." };

  const { error: upsertError } = await supabase
    .from("custom_playbook_overrides")
    .upsert({ pool_id: poolId, gameweek, slot, player_id: newPlayerId, reason: "Manual swap - real injury/lineup concern" }, { onConflict: "pool_id,gameweek,slot" });
  if (upsertError) return { error: `Failed to save swap: ${upsertError.message}` };

  revalidatePath("/playbook/custom");
  return { ok: true };
}

export async function revertSwap(poolId: number, gameweek: number, slot: SlotKey): Promise<{ ok: true } | { error: string }> {
  const { supabase, error } = await assertOwnPool(poolId);
  if (!supabase) return { error: error! };

  const { error: deleteError } = await supabase.from("custom_playbook_overrides").delete().eq("pool_id", poolId).eq("gameweek", gameweek).eq("slot", slot);
  if (deleteError) return { error: `Failed to revert swap: ${deleteError.message}` };

  revalidatePath("/playbook/custom");
  return { ok: true };
}
