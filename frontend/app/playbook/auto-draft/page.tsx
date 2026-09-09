import Link from "next/link";
import SiteHeader from "../../SiteHeader";
import PlaybookBoard, { type PlanData } from "../PlaybookBoard";
import plan from "../data/auto-draft.json";

export default function AutoDraftPage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 p-4 sm:p-6">
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/playbook" className="rounded-full bg-navy-900 px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide text-navy-400 hover:bg-navy-800">
            &larr; My Playbook
          </Link>
        </div>
        <p className="mt-2 text-xs font-bold uppercase tracking-wide text-amber-400">Full-Board, No Team Bias</p>
        <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">Auto-Draft Playbook</h1>
        <p className="mt-2 max-w-2xl text-sm text-navy-300">
          No starting team list — GW1 is solved from the entire real player board, and every later week picks the single best real upgrade from the whole
          board too. Scores higher on paper than a hand-picked build, but churns far more: expect a transfer most weeks, not just when your teams&apos;
          fixtures turn.
        </p>
        <div className="mt-6">
          <PlaybookBoard plan={plan as unknown as PlanData} storageKey="playbook_auto" accentClass="text-amber-400" />
        </div>
      </main>
    </>
  );
}
