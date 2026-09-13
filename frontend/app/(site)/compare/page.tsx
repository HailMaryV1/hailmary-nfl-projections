import { createPublicClient } from "@/lib/supabaseClient";
import { loadComparePlayers } from "@/lib/comparePlayer";
import PlayerPicker, { type PlayerOption } from "./PlayerPicker";
import CompareView from "./CompareView";

export default async function ComparePage({ searchParams }: { searchParams: Promise<{ a?: string; b?: string }> }) {
  const { a, b } = await searchParams;
  const supabase = createPublicClient();

  type Row = { id: number; full_name: string; position: string; teams: { abbr: string } | null };
  const { data: rows, error } = await supabase
    .from("players")
    .select("id, full_name, position, teams!team_id(abbr)")
    .eq("is_active", true)
    .not("position", "is", null)
    .order("full_name")
    .order("id"); // tiebreak for duplicate names, same fix best-squad/playbook pages use
  if (error) throw new Error(`Failed to load players: ${error.message}`);

  const options: PlayerOption[] = ((rows ?? []) as unknown as Row[]).map((r) => ({
    id: r.id,
    name: r.full_name,
    position: r.position,
    team: r.teams?.abbr ?? "—",
  }));

  const idA = a ? Number(a) : null;
  const idB = b ? Number(b) : null;

  let playerA = null;
  let playerB = null;
  if (idA && idB) {
    ({ playerA, playerB } = await loadComparePlayers(supabase, idA, idB));
  }

  return (
    <main className="mx-auto w-full min-w-0 max-w-4xl flex-1 p-4 sm:p-6">
        <p className="text-xs font-bold uppercase tracking-wide text-sky-400">Head-to-Head</p>
        <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">Player Face-Off</h1>
        <p className="mt-2 max-w-2xl text-sm text-navy-300">
          Pick two players - real projected points across every horizon, real season stats, real ownership, and each
          one&apos;s real upcoming fixture run, side by side.
        </p>

        <div className="mt-6">
          <PlayerPicker options={options} selectedA={idA} selectedB={idB} />
        </div>

        {playerA && playerB && (
          <div className="mt-8">
            <CompareView playerA={playerA} playerB={playerB} />
          </div>
        )}
        {(idA || idB) && (!playerA || !playerB) && <p className="mt-8 text-sm text-navy-400">Pick a second player to compare.</p>}
    </main>
  );
}
