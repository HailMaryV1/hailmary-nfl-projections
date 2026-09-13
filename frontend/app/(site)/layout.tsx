import SiteHeader from "../SiteHeader";

// Real perf fix (ported from the sibling dreamteam-projections/EFL-
// Projections sites): SiteHeader does a real supabase.auth.getUser() call
// - rendering it per-page meant every one of these public pages re-ran
// that check on its own navigation. Hoisted into this shared route-group
// layout instead, so it renders once and survives client-side navigation
// between pages.
export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-1 flex-col sm:flex-row">
      <SiteHeader />
      {children}
    </div>
  );
}
