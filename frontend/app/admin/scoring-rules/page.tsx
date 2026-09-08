import { createAuthServerClient } from "@/lib/supabaseServerClient";
import ScoringRulesForm from "./ScoringRulesForm";

export default async function ScoringRulesPage() {
  const supabase = await createAuthServerClient();
  const { data: rules, error } = await supabase.from("scoring_rules").select("id, applies_to, stat, points, notes").order("applies_to").order("stat");
  if (error) throw new Error(`Failed to load scoring rules: ${error.message}`);

  return (
    <div>
      <h1 className="text-xl font-semibold text-navy-100">Scoring Rules</h1>
      <p className="mt-1 text-sm text-navy-400">FanTeam&apos;s real point values per stat. Edits apply from the next projection run.</p>
      <div className="mt-6">
        <ScoringRulesForm rules={rules ?? []} />
      </div>
    </div>
  );
}
