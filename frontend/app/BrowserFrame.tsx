// Ported from the sibling dreamteam-projections/EFL-Projections sites.
// Premium "product shot" chrome wrapping a real, live slice of the tool
// UI - deliberately NOT a screenshot. Every child passed in is the actual
// component the real page renders, reading the same real data, so the
// preview never drifts out of date the way a static image would.
export default function BrowserFrame({
  url,
  children,
  fade = false,
  accent = "#38bdf8",
  maxHeight,
}: {
  url: string;
  children: React.ReactNode;
  fade?: boolean;
  accent?: string;
  maxHeight?: string;
}) {
  return (
    <div
      className="group relative overflow-hidden rounded-2xl border border-navy-800 bg-navy-900 shadow-[0_30px_80px_-30px_rgba(0,0,0,0.7)] transition-all duration-300 ease-out hover:-translate-y-1.5 hover:border-navy-600"
      style={{ ["--frame-accent" as string]: accent }}
    >
      <div
        className="pointer-events-none absolute -inset-px rounded-2xl opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ boxShadow: `0 0 0 1px color-mix(in srgb, ${accent} 45%, transparent), 0 30px 90px -25px color-mix(in srgb, ${accent} 45%, transparent)` }}
      />
      <div className="relative flex items-center gap-2 border-b border-navy-800 bg-navy-950/70 px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-[#ff5f57]/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#febc2e]/80" />
        <span className="h-2.5 w-2.5 rounded-full bg-[#28c840]/80" />
        <span className="ml-3 flex min-w-0 flex-1 items-center gap-1.5 truncate rounded-md bg-navy-900/80 px-3 py-1 font-mono text-[11px] text-navy-500 ring-1 ring-navy-800">
          <svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" strokeWidth="2.5" className="shrink-0 text-emerald-500">
            <path d="M12 15v2M7 10V7a5 5 0 0110 0v3M5 10h14v10H5z" />
          </svg>
          <span className="truncate">{url}</span>
        </span>
        <span className="hidden shrink-0 items-center gap-1 rounded-full bg-emerald-400/10 px-2 py-0.5 font-[family-name:var(--font-cond)] text-[10px] font-bold tracking-wide text-emerald-400 uppercase sm:flex">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Live
        </span>
      </div>
      <div className={`relative ${fade ? "overflow-hidden" : "overflow-x-auto"}`} style={maxHeight ? { maxHeight } : undefined}>
        <div className={maxHeight ? "overflow-hidden" : ""}>{children}</div>
        {fade && <div className="pointer-events-none absolute inset-x-0 bottom-0 h-24 bg-gradient-to-t from-navy-900 via-navy-900/90 to-transparent" />}
      </div>
    </div>
  );
}
