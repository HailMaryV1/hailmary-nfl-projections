"use server";

import { revalidatePath } from "next/cache";
import { createAuthServerClient } from "@/lib/supabaseServerClient";

export async function saveScoringRules(changes: { id: number; applies_to: string; stat: string; oldPoints: number; newPoints: number }[]) {
  const supabase = await createAuthServerClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) throw new Error("Not signed in.");

  const real = changes.filter((c) => c.newPoints !== c.oldPoints);
  for (const change of real) {
    const { error } = await supabase.from("scoring_rules").update({ points: change.newPoints }).eq("id", change.id);
    if (error) throw new Error(`Failed to update ${change.stat}: ${error.message}`);

    await supabase.from("activity_log").insert({
      event_type: "scoring_rule_changed",
      actor: user.email,
      summary: `${change.applies_to}/${change.stat} changed from ${change.oldPoints} to ${change.newPoints}`,
      details: { applies_to: change.applies_to, stat: change.stat, old_points: change.oldPoints, new_points: change.newPoints },
    });
  }

  revalidatePath("/admin/scoring-rules");
  return { updated: real.length };
}
