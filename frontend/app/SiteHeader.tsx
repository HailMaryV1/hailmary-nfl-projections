import Link from "next/link";

export default function SiteHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-navy-800 bg-navy-950/90 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
        <Link href="/" className="flex min-w-0 shrink items-center gap-2.5">
          <span className="shrink-0 text-sm font-bold tracking-wide text-navy-100">HAIL MARY</span>
          <span className="hidden text-navy-600 sm:inline">/</span>
          <span className="truncate text-sm font-medium text-navy-300">NFL Projections</span>
        </Link>
        <div className="flex shrink-0 items-center gap-4">
          <Link href="/fixtures" className="text-sm text-navy-300 hover:text-sky-300">
            Fixtures
          </Link>
          <Link href="/admin" className="text-xs text-navy-500 hover:text-sky-300">
            Admin
          </Link>
        </div>
      </div>
    </header>
  );
}
