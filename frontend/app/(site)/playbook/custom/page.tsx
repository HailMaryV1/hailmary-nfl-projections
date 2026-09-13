import Link from "next/link";
import { createAuthServerClient } from "@/lib/supabaseServerClient";
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

  return (
    <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/playbook/builder" className="rounded-full bg-navy-900 px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide text-navy-400 hover:bg-navy-800">
            Edit pool
          </Link>
        </div>
        <p className="mt-2 text-xs font-bold uppercase tracking-wide text-emerald-400">Built From Your Own Pool</p>
        <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">Your Playbook</h1>

        {!playbook ? (
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
              <PlaybookBoard plan={playbook.plan as unknown as PlanData} storageKey="playbook_custom" accentClass="text-emerald-400" />
            </div>
          </>
        )}
    </main>
  );
}
