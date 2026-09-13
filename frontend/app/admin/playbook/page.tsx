import Link from "next/link";
import PlaybookBoard, { type PlanData } from "../../playbook/PlaybookBoard";
import plan from "./data/hand-picked.json";

// Real user decision 2026-09-13: this is the site owner's own personal
// season plan - "mean nothing to anybody else" - so it lives under /admin
// now, not in public nav next to /playbook/custom (the real any-signed-in-
// customer feature). SiteHeader is rendered once by admin/layout.tsx, not
// here.
export default function PlaybookPage() {
  return (
    <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/admin/playbook/auto-draft" className="rounded-full bg-navy-900 px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide text-navy-400 hover:bg-navy-800">
          Auto-Draft &rarr;
        </Link>
      </div>
      <p className="mt-2 text-xs font-bold uppercase tracking-wide text-sky-400">18-Week Fixture Rotation Strategy</p>
      <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">My Playbook</h1>
      <p className="mt-2 max-w-2xl text-sm text-navy-300">
        Built around real teams you picked (Chargers, Chiefs, Lions, Rams, 49ers, Packers, Ravens), rotated on real fixture difficulty and doubled up on
        back-to-back favourable runs.
      </p>
      <div className="mt-6">
        <PlaybookBoard plan={plan as unknown as PlanData} storageKey="playbook_hand" accentClass="text-sky-400" />
      </div>
    </main>
  );
}
