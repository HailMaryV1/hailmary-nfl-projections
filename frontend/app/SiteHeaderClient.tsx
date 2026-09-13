"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

type NavIcon = (props: { className?: string }) => React.JSX.Element;

const iconProps = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };

const HomeIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <path d="M4 11.5L12 4l8 7.5" />
    <path d="M6 10v9a1 1 0 001 1h10a1 1 0 001-1v-9" />
    <path d="M10 20v-6h4v6" />
  </svg>
);
const ProjectionsIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <path d="M4 6h16M4 12h11M4 18h7" />
  </svg>
);
const FixturesIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <rect x="3.5" y="4.5" width="17" height="16" rx="2" />
    <path d="M3.5 9.5h17M8 3v3M16 3v3" />
  </svg>
);
const StatsIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <path d="M4 20V10M12 20V4M20 20v-7" />
  </svg>
);
const CompareIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <path d="M7 4v13M4 14l3 3 3-3M17 20V7M14 10l3-3 3 3" />
  </svg>
);
const BestTeamIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <path d="M12 3l8 3v5c0 5-3.5 8.5-8 10-4.5-1.5-8-5-8-10V6z" />
    <circle cx="12" cy="11" r="2.4" />
  </svg>
);
const ValueIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M9.5 15.5c0 1 1 1.8 2.5 1.8s2.5-.7 2.5-1.7c0-2.4-5-1.3-5-3.7 0-1 1-1.7 2.5-1.7s2.5.7 2.5 1.7M12 8.3v1M12 16v.9" />
  </svg>
);
const PoolIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <circle cx="12" cy="8" r="3.2" />
    <path d="M4.5 20c1-3.5 4-5.5 7.5-5.5s6.5 2 7.5 5.5" />
  </svg>
);
const MyTeamIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <rect x="3.5" y="5" width="17" height="13" rx="1.5" />
    <path d="M3.5 9.5h17M8 5v13" />
  </svg>
);
const AdminIcon: NavIcon = ({ className }) => (
  <svg {...iconProps} className={className}>
    <path d="M12 3l7 3v5c0 5-3 8.5-7 10-4-1.5-7-5-7-10V6z" />
    <path d="M9.5 12l1.8 1.8L15 10" />
  </svg>
);

type NavItem = { href: string; label: string; icon: NavIcon };

// ANALYSE (read the model's own numbers) / BUILD (use them to make a real
// squad/pick decision) - same grouping ported from the sibling
// dreamteam-projections/EFL-Projections sidebars.
const ANALYSE_LINKS: NavItem[] = [
  { href: "/projections", label: "Player Projections", icon: ProjectionsIcon },
  { href: "/fixtures", label: "Fixture Difficulty", icon: FixturesIcon },
  { href: "/player-stats", label: "Player Stats", icon: StatsIcon },
  { href: "/compare", label: "Player Face-Off", icon: CompareIcon },
];
const BUILD_LINKS: NavItem[] = [
  { href: "/best-team", label: "Best Team", icon: BestTeamIcon },
  { href: "/value-finder", label: "Value Finder", icon: ValueIcon },
  { href: "/playbook/custom", label: "My Pool", icon: PoolIcon },
  { href: "/my-team", label: "My Team", icon: MyTeamIcon },
];

function NavGroupLabel({ children }: { children: React.ReactNode }) {
  return <p className="mt-4 mb-1 px-3 font-[family-name:var(--font-cond)] text-[10px] font-bold tracking-[0.2em] text-navy-600 uppercase first:mt-1">{children}</p>;
}

// Real bug found live on the sibling projects, ported here unchanged:
// React attaches its own click handlers at the root container in the
// bubble phase, and Next's <Link> calls preventDefault() there to do
// client-side routing - a bubble-phase document listener here would
// always see the click AFTER that already happened. Capturing on
// `document` fires before any of that, so this reliably sees every real
// link click.
function useNavigationPending(): boolean {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, setPending] = useState(false);
  const routeKey = `${pathname}?${searchParams.toString()}`;
  const previousRouteKey = useRef(routeKey);

  useEffect(() => {
    if (previousRouteKey.current !== routeKey) {
      previousRouteKey.current = routeKey;
      setPending(false);
    }
  }, [routeKey]);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const anchor = (e.target as HTMLElement)?.closest("a");
      if (!anchor) return;
      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("http") || href.startsWith("#") || href.startsWith("mailto:") || anchor.target === "_blank") return;
      setPending(true);
    }
    document.addEventListener("click", handleClick, { capture: true });
    return () => document.removeEventListener("click", handleClick, { capture: true });
  }, []);

  return pending;
}

// Thin loading bar under the brand wordmark - real user request ported
// from the sibling projects: "have the page have a little load icon that
// shows something has been clicked and its processing".
function NavLoadingBar({ pending }: { pending: boolean }) {
  if (!pending) return null;
  return (
    <div aria-hidden className="absolute inset-x-0 -bottom-1.5 h-0.5 overflow-hidden rounded-full bg-navy-800">
      <div className="animate-nav-bar h-full w-1/3 rounded-full bg-sky-400" />
    </div>
  );
}

function Brand({ onClick, pending }: { onClick?: () => void; pending: boolean }) {
  return (
    <Link href="/" className="relative flex min-w-0 shrink items-center gap-2.5" onClick={onClick}>
      <span className="shrink-0 text-sm font-bold tracking-wide text-navy-100">HAIL MARY</span>
      <span className="hidden text-navy-600 sm:inline">/</span>
      <span className="truncate text-sm font-medium text-navy-300">NFL Projections</span>
      <NavLoadingBar pending={pending} />
    </Link>
  );
}

function NavLink({ href, label, icon: Icon, active, onClick }: { href: string; label: string; icon: NavIcon; active: boolean; onClick?: () => void }) {
  return (
    <Link
      href={href}
      onClick={onClick}
      className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-semibold transition-colors ${
        active ? "bg-sky-400/10 text-sky-300" : "text-navy-300 hover:bg-navy-900 hover:text-navy-100"
      }`}
    >
      <Icon className="h-5 w-5 shrink-0" />
      <span className="truncate">{label}</span>
    </Link>
  );
}

export default function SiteHeaderClient({ isAdmin }: { isAdmin: boolean }) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const pending = useNavigationPending();

  const nav = (onLinkClick?: () => void) => (
    <nav className="flex flex-col gap-1">
      <NavLink href="/" label="Home" icon={HomeIcon} active={pathname === "/"} onClick={onLinkClick} />
      <NavGroupLabel>Analyse</NavGroupLabel>
      {ANALYSE_LINKS.map((link) => (
        <NavLink key={link.href} {...link} active={pathname === link.href} onClick={onLinkClick} />
      ))}
      <NavGroupLabel>Build</NavGroupLabel>
      {BUILD_LINKS.map((link) => (
        <NavLink key={link.href} {...link} active={pathname === link.href} onClick={onLinkClick} />
      ))}
      {isAdmin && (
        <>
          <div className="my-2 border-t border-navy-800" />
          <NavLink href="/admin" label="Admin" icon={AdminIcon} active={pathname.startsWith("/admin")} onClick={onLinkClick} />
        </>
      )}
    </nav>
  );

  return (
    <>
      <div className="sticky top-0 z-30 border-b border-navy-800 bg-navy-950/90 backdrop-blur-sm sm:hidden">
        <div className="flex items-center justify-between gap-3 px-4 py-2.5">
          <Brand onClick={() => setMenuOpen(false)} pending={pending} />
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-navy-300 hover:bg-navy-900 hover:text-sky-300"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              {menuOpen ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 6h16M4 12h16M4 18h16" />}
            </svg>
          </button>
        </div>
        {menuOpen && <div className="border-t border-navy-800 p-3">{nav(() => setMenuOpen(false))}</div>}
      </div>

      <aside className="hidden w-64 shrink-0 border-r border-navy-800 bg-navy-950 p-4 sm:flex sm:flex-col">
        <div className="mb-6 px-1">
          <Brand pending={pending} />
        </div>
        {nav()}
      </aside>
    </>
  );
}
