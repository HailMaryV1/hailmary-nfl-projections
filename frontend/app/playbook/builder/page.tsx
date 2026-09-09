import SiteHeader from "../../SiteHeader";
import { createPublicClient } from "@/lib/supabaseClient";
import { createAuthServerClient } from "@/lib/supabaseServerClient";
import { POOL_SPEC, tierForPrice } from "@/lib/poolSpec";
import type { Position, Tier } from "@/lib/playbookEngine";
import PoolPicker, { type PlayerOption } from "./PoolPicker";

export default async function PoolBuilderPage() {
  const supabase = createPublicClient();

  const { data: latestVersionRow } = await supabase
    .from("algorithm_versions")
    .select("id")
    .order("id", { ascending: false })
    .limit(1)
    .maybeSingle();
  const algorithmVersionId = latestVersionRow?.id;

  const { data: rows, error } = algorithmVersionId
    ? await supabase
        .from("projections")
        .select("total_points, players!inner(id, full_name, position, price, teams!team_id(abbr))")
        .eq("horizon", 1)
        .eq("algorithm_version_id", algorithmVersionId)
        .in("players.position", ["quarterback", "running_back", "wide_receiver", "tight_end", "defense_special"])
        .order("total_points", { ascending: false })
    : { data: [], error: null };
  if (error) throw new Error(`Failed to load player pool: ${error.message}`);

  type Row = { total_points: number; players: { id: number; full_name: string; position: Position; price: number; teams: { abbr: string } | null } };
  const options: PlayerOption[] = ((rows ?? []) as unknown as Row[]).map((r) => ({
    id: r.players.id,
    name: r.players.full_name,
    position: r.players.position,
    price: Number(r.players.price),
    team: r.players.teams?.abbr ?? "—",
    points: Number(r.total_points),
    tier: tierForPrice(r.players.position, Number(r.players.price)),
  }));

  // Existing pool, if the user already has one - pre-selects it for editing.
  let existingSelection: number[] = [];
  const authClient = await createAuthServerClient();
  const {
    data: { user },
  } = await authClient.auth.getUser();
  if (user) {
    const { data: pool } = await authClient.from("custom_pools").select("id").eq("user_id", user.id).order("updated_at", { ascending: false }).limit(1).maybeSingle();
    if (pool) {
      const { data: poolPlayers } = await authClient.from("custom_pool_players").select("player_id").eq("pool_id", pool.id);
      existingSelection = (poolPlayers ?? []).map((p) => p.player_id as number);
    }
  }

  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full min-w-0 max-w-5xl flex-1 p-4 sm:p-6">
        <p className="text-xs font-bold uppercase tracking-wide text-emerald-400">Build Your Own Playbook</p>
        <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">Pool Builder</h1>
        <p className="mt-2 max-w-2xl text-sm text-navy-300">
          Pick 28 players across real price brackets — the brackets are sized so a legal £140M squad always exists, no matter how you spend your premium
          picks. We&apos;ll then work out the best real week-by-week rotation from exactly this pool, same as the two built-in playbooks.
        </p>
        <div className="mt-6">
          <PoolPicker options={options} spec={POOL_SPEC} existingSelection={existingSelection} signedIn={!!user} />
        </div>
      </main>
    </>
  );
}

export type { Position, Tier };
