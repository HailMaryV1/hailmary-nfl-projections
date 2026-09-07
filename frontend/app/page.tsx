export default function Home() {
  return (
    <main className="mx-auto flex w-full min-w-0 max-w-2xl flex-1 flex-col items-start justify-center gap-3 p-6">
      <p className="font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide text-sky-400">
        Hail Mary
      </p>
      <h1 className="text-3xl font-semibold text-navy-100">NFL Projections</h1>
      <p className="max-w-md text-sm text-navy-300">
        Real projections for FanTeam&apos;s NFL Regular Season 2026/27 tournament, built from a five-layer model.
        Coming soon.
      </p>
    </main>
  );
}
