import { createAuthServerClient } from "@/lib/supabaseServerClient";
import LayerWeightsForm from "./LayerWeightsForm";

export default async function LayerWeightsPage() {
  const supabase = await createAuthServerClient();
  const { data: rows, error } = await supabase.from("layer_weights").select("id, horizon, position, layer, weight");
  if (error) throw new Error(`Failed to load layer weights: ${error.message}`);

  return (
    <div>
      <h1 className="text-xl font-semibold text-navy-100">Layer Weights</h1>
      <p className="mt-1 text-sm text-navy-400">
        How much each layer counts toward a position&apos;s rating, per horizon. Lineup Status isn&apos;t listed here -
        it gates the total rather than blending with these four.
      </p>
      <div className="mt-6">
        <LayerWeightsForm rows={rows ?? []} />
      </div>
    </div>
  );
}
