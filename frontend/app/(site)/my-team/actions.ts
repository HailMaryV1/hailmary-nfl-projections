"use server";

import { revalidatePath } from "next/cache";
import { createAuthServerClient } from "@/lib/supabaseServerClient";
import { parseFanteamEntryId, validateFanteamEntry } from "@/lib/fanteamTeam";

export async function connectFanteamTeam(input: string): Promise<{ ok: true } | { error: string }> {
  const supabase = await createAuthServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: "Not signed in." };

  const parsed = parseFanteamEntryId(input);
  if ("error" in parsed) return { error: parsed.error };

  const validated = await validateFanteamEntry(parsed.entryId);
  if ("error" in validated) return { error: validated.error };

  const { error } = await supabase
    .from("user_fanteam_teams")
    .upsert({ user_id: user.id, fanteam_entry_id: parsed.entryId, team_name: validated.teamName, connected_at: new Date().toISOString() }, { onConflict: "user_id" });
  if (error) return { error: `Failed to save your team: ${error.message}` };

  revalidatePath("/my-team");
  return { ok: true };
}

export async function disconnectFanteamTeam(): Promise<{ ok: true } | { error: string }> {
  const supabase = await createAuthServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) return { error: "Not signed in." };

  const { error } = await supabase.from("user_fanteam_teams").delete().eq("user_id", user.id);
  if (error) return { error: `Failed to disconnect: ${error.message}` };

  revalidatePath("/my-team");
  return { ok: true };
}
