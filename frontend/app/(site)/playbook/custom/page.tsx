import Link from "next/link";
import { createAuthServerClient } from "@/lib/supabaseServerClient";
import { createPublicClient } from "@/lib/supabaseClient";
import { applyPlanOverrides, findInjuryFlags, type OverrideRow, type OverrideSlotInfo } from "@/lib/injurySwap";
import { SLOT_ORDER } from "@/lib/playbookEngine";
import PlaybookBoard, { type PlanData } from "../PlaybookBoard";

export default async function CustomPlaybookPage() {
  const supabase = await createAuthServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    // The proxy already gates this route, but keep this readable on its
    // own in case that ever changes.
    return (
      <main className="mx-auto w-full max-w-3xl flex-1 p-6">
        <p className="text-sm text-navy-300">Sign in to see your playbook.</p>
      </main>
    );
  }

  const { data: pool } = await supabase.from("custom_pools").select("id, name").eq("user_id", user.id).order("updated_at", { ascending: false }).limit(1).maybeSingle();

  const { data: playbook } = pool
    ? await supabase.from("custom_playbooks").select("plan, total_points, computed_at").eq("pool_id", pool.id).order("computed_at", { ascending: false }).limit(1).maybeSingle()
    : { data: null };

  let plan = playbook ? (playbook.plan as unknown as PlanData) : null;
  let currentGameweek: number | null = null;
  let injuryFlags: Record<string, { status: string }> = {};

  if (pool && plan) {
    const publicClient = createPublicClient();
    const { data: latestVersionRow } = await publicClient.from("algorithm_versions").select("id").order("id", { ascending: false }).limit(1).maybeSingle();
    const algorithmVersionId = latestVersionRow?.id;
    const { data: gwRow } = algorithmVersionId
      ? await publicClient.from("projections").select("gameweek").eq("horizon", 1).eq("algorithm_version_id", algorithmVersionId).order("gameweek", { ascending: false }).limit(1).maybeSingle()
      : { data: null };
    currentGameweek = gwRow?.gameweek ?? null;

    const { data: overrideRows } = await supabase.from("custom_playbook_overrides").select("gameweek, slot, player_id, reason").eq("pool_id", pool.id);
    const overrides = (overrideRows ?? []) as OverrideRow[];

    if (overrides.length > 0) {
      const gameweeks = [...new Set(overrides.map((o) => o.gameweek))];
      const playerIds = [...new Set(overrides.map((o) => o.player_id))];
      const { data: replacementRows } = algorithmVersionId
        ? await publicClient
            .from("projections")
            .select("gameweek, total_points, players!inner(id, full_name, price, teams!team_id(abbr))")
            .eq("horizon", 1)
            .eq("algorithm_version_id", algorithmVersionId)
            .in("gameweek", gameweeks)
            .in("players.id", playerIds)
        : { data: [] };

      type ReplacementRow = { gameweek: number; total_points: number; players: { id: number; full_name: string; price: number; teams: { abbr: string } | null } };
      const infoByPlayerGw = new Map<string, OverrideSlotInfo>();
      for (const r of (replacementRows ?? []) as unknown as ReplacementRow[]) {
        infoByPlayerGw.set(`${r.gameweek}:${r.players.id}`, { name: r.players.full_name, team: r.players.teams?.abbr ?? "—", price: Number(r.players.price), pts: Number(r.total_points) });
      }
      const replacementInfo = new Map<string, OverrideSlotInfo>();
      for (const ov of overrides) {
        const info = infoByPlayerGw.get(`${ov.gameweek}:${ov.player_id}`);
        if (info) replacementInfo.set(`${ov.gameweek}:${ov.slot}`, info);
      }

      plan = applyPlanOverrides(plan, overrides, replacementInfo);
    }

    if (currentGameweek) {
      const currentWeek = plan.weeks.find((w) => w.gw === currentGameweek);
      if (currentWeek) {
        const names = [...SLOT_ORDER.filter((s) => s !== "DST").map((s) => currentWeek.roster[s].name), currentWeek.dst.name];
        injuryFlags = await findInjuryFlags(publicClient, names, currentGameweek);
      }
    }
  }

  return (
    <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/playbook/builder" className="rounded-full bg-navy-900 px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide text-navy-400 hover:bg-navy-800">
            Edit pool
          </Link>
        </div>
        <p className="mt-2 text-xs font-bold uppercase tracking-wide text-emerald-400">Built From Your Own Pool</p>
        <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">Your Playbook</h1>

        {!playbook || !plan ? (
          <p className="mt-8 rounded-lg bg-navy-900 p-6 text-center text-sm text-navy-400 ring-1 ring-navy-800">
            You haven&apos;t built a playbook yet.{" "}
            <Link href="/playbook/builder" className="text-sky-400 hover:underline">
              Pick your 28 players
            </Link>{" "}
            to get started.
          </p>
        ) : (
          <>
            <p className="mt-2 max-w-2xl text-sm text-navy-300">
              Computed {new Date(playbook.computed_at).toLocaleString()} from your own 28-player pool — the same real week-by-week engine as the other two
              playbooks, restricted to just your picks. DST rotates properly here too, since your pool only has 4 real options to choose from each week.
            </p>
            <div className="mt-6">
              <PlaybookBoard
                plan={plan}
                storageKey="playbook_custom"
                accentClass="text-emerald-400"
                poolId={pool!.id}
                currentGameweek={currentGameweek ?? undefined}
                injuryFlags={injuryFlags}
              />
            </div>
          </>
        )}
    </main>
  );
}
