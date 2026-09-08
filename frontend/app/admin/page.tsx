import Link from "next/link";
import { createAuthServerClient } from "@/lib/supabaseServerClient";

export default async function AdminHome() {
  const supabase = await createAuthServerClient();

  const { data: activity } = await supabase
    .from("activity_log")
    .select("event_type, summary, created_at")
    .order("created_at", { ascending: false })
    .limit(15);

  const { data: latestVersion } = await supabase
    .from("algorithm_versions")
    .select("revision, created_at, note")
    .order("revision", { ascending: false })
    .limit(1)
    .maybeSingle();

  return (
    <div>
      <h1 className="text-xl font-semibold text-navy-100">Admin</h1>
      <p className="mt-1 text-sm text-navy-400">
        Changes here take effect the next time <code className="text-navy-300">compute_projections.py</code> runs -
        {" "}editing a weight doesn&apos;t recompute existing projections retroactively.
      </p>

      <div className="mt-4 flex flex-wrap gap-3">
        <Link href="/admin/scoring-rules" className="rounded-lg border border-navy-800 bg-navy-900 px-4 py-3 text-sm text-navy-200 hover:border-sky-500/50">
          Scoring Rules →
        </Link>
        <Link href="/admin/layer-weights" className="rounded-lg border border-navy-800 bg-navy-900 px-4 py-3 text-sm text-navy-200 hover:border-sky-500/50">
          Layer Weights →
        </Link>
      </div>

      {latestVersion && (
        <p className="mt-4 text-xs text-navy-500">
          Current algorithm version: revision {latestVersion.revision} ({new Date(latestVersion.created_at).toLocaleString("en-GB")})
        </p>
      )}

      <h2 className="mt-8 text-sm font-semibold uppercase tracking-wide text-navy-400">Recent activity</h2>
      <ul className="mt-3 flex flex-col divide-y divide-navy-800 text-sm">
        {(activity ?? []).map((row, i) => (
          <li key={i} className="flex items-center justify-between gap-3 py-2">
            <span className="text-navy-200">{row.summary ?? row.event_type}</span>
            <span className="shrink-0 text-xs text-navy-500">{new Date(row.created_at).toLocaleString("en-GB")}</span>
          </li>
        ))}
        {(!activity || activity.length === 0) && <li className="py-2 text-navy-500">No activity recorded yet.</li>}
      </ul>
    </div>
  );
}
