// Generic Suspense-fallback skeleton (ported from the sibling projects) -
// shown the instant a link is clicked, while the real page's own data
// fetch is still in flight, instead of a blank white gap.
export default function SiteLoading() {
  return (
    <main className="mx-auto w-full min-w-0 max-w-5xl flex-1 p-4 sm:p-6">
      <div className="animate-pulse">
        <div className="h-7 w-56 rounded-md bg-navy-800" />
        <div className="mt-3 h-4 w-80 max-w-full rounded-md bg-navy-800/70" />
        <div className="mt-6 flex flex-wrap gap-2">
          <div className="h-8 w-16 rounded-full bg-navy-800" />
          <div className="h-8 w-16 rounded-full bg-navy-900" />
          <div className="h-8 w-16 rounded-full bg-navy-900" />
          <div className="h-8 w-16 rounded-full bg-navy-900" />
        </div>
        <div className="mt-6 space-y-2.5">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-12 rounded-xl bg-navy-900" style={{ opacity: 1 - i * 0.09 }} />
          ))}
        </div>
      </div>
    </main>
  );
}
