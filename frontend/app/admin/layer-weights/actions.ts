"use server";

import { revalidatePath } from "next/cache";
import { createAuthServerClient } from "@/lib/supabaseServerClient";

export async function saveLayerWeights(
  horizon: number,
  position: string,
  changes: { id: number; layer: string; oldWeight: number; newWeight: number }[]
) {
  const supabase = await createAuthServerClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("Not signed in.");

  const real = changes.filter((c) => c.newWeight !== c.oldWeight);
  for (const change of real) {
    const { error } = await supabase.from("layer_weights").update({ weight: change.newWeight, updated_at: new Date().toISOString() }).eq("id", change.id);
    if (error) throw new Error(`Failed to update ${change.layer}: ${error.message}`);

    await supabase.from("activity_log").insert({
      event_type: "layer_weight_changed",
      actor: user.email,
      summary: `${position} GW${horizon} ${change.layer} weight changed from ${change.oldWeight} to ${change.newWeight}`,
      details: { horizon, position, layer: change.layer, old_weight: change.oldWeight, new_weight: change.newWeight },
    });
  }

  revalidatePath("/admin/layer-weights");
  return { updated: real.length };
}
