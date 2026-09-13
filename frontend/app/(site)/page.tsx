import Link from "next/link";
import RatingsTable, { type PlayerRow } from "../RatingsTable";
import FixtureDifficultyGrid, { type TeamScheduleRow } from "./fixtures/FixtureDifficultyGrid";
import CompareView from "./compare/CompareView";
import TeamBadge from "../TeamBadge";
import BrowserFrame from "../BrowserFrame";
import Reveal from "../Reveal";
import { createPublicClient } from "@/lib/supabaseClient";
import { computeDifficultyThresholds, difficultyTier, DIFFICULTY_LABELS, type DifficultyTier } from "@/lib/fixtureDifficulty";
import { positionLabel } from "@/lib/positions";
import { buildBestTeam } from "@/lib/bestTeam";
import { loadComparePlayers } from "@/lib/comparePlayer";
import { type Position, BUDGET_CAP } from "@/lib/playbookEngine";

const LAYERS = [
  { name: "Lineup Status", description: "RotoWire starters/inactives, cross-checked live." },
  { name: "Form", description: "Recency-decayed real per-game production." },
  { name: "Fixture Quantity", description: "Real bye weeks, correctly zeroed out." },
  { name: "Fixture Quality", description: "Sharp Football's Vegas-win-total model." },
  { name: "Live Odds", description: "Spreadex player props - yards, TDs, sacks." },
];

// A single "signal" from the live model - deliberately terminal/feed-like
// (emoji glyph, one clean fact, one big number) rather than a stat-report
// tile. Ported from the sibling projects.
function IntelCard({ href, emoji, label, team, name, meta, value, valueLabel, accent }: { href: string; emoji: string; label: string; team: string; name: string; meta?: string; value: string; valueLabel?: string; accent: string }) {
  return (
    <Link
      href={href}
      className="group relative flex flex-1 flex-col overflow-hidden rounded-2xl border border-navy-800 bg-navy-900 p-4 transition-all duration-200 hover:-translate-y-1.5 hover:border-navy-600 sm:p-5"
    >
      <div className="pointer-events-none absolute -top-10 -right-10 h-28 w-28 rounded-full opacity-0 blur-2xl transition-opacity duration-300 group-hover:opacity-100" style={{ background: accent }} />
      <div className="relative flex items-center justify-between">
        <span className="text-xl leading-none">{emoji}</span>
        <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-navy-600 transition-all duration-200 group-hover:translate-x-0.5 group-hover:text-sky-300">
          <path d="M7 17L17 7M9 7h8v8" />
        </svg>
      </div>
      <p className="relative mt-3 font-[family-name:var(--font-cond)] text-[11px] font-bold tracking-[0.14em] text-navy-500 uppercase">{label}</p>
      <div className="relative mt-1 flex min-w-0 items-center gap-2">
        <TeamBadge team={team} size="sm" />
        <p className="min-w-0 truncate font-[family-name:var(--font-cond)] text-lg font-extrabold text-navy-100 uppercase sm:text-xl">{name}</p>
      </div>
      {meta && <p className="relative truncate text-xs text-navy-500">{meta}</p>}
      <p className="relative mt-3 animate-rise font-mono text-2xl font-bold tabular-nums sm:text-[28px]" style={{ color: accent }}>
        {value}
      </p>
      {valueLabel && <p className="relative mt-0.5 text-[10px] tracking-wide text-navy-500 uppercase">{valueLabel}</p>}
    </Link>
  );
}

function Chip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-navy-800 bg-navy-950/60 px-3 py-1.5 text-xs">
      <span className="text-[9px] tracking-wide text-navy-500 uppercase">{label} </span>
      <span className="font-mono font-bold text-navy-200">{value}</span>
    </div>
  );
}

// The gameweek's own #1 projected player, elevated into a genuinely bigger
// feature card. Ported from the sibling projects - real price chip kept
// (unlike EFL, NFL has real player prices).
function FeaturedPickCard({ player }: { player: { name: string; team: string; position: string; price: number; rating: number | null; ownershipPct: number | null; matchup: string | null; totalPoints: number } }) {
  return (
    <Link
      href="/"
      className="group relative flex flex-col justify-between overflow-hidden rounded-2xl border border-orange-500/20 bg-gradient-to-br from-navy-900 via-navy-900 to-orange-950/10 p-6 transition-all duration-300 hover:-translate-y-1.5 hover:border-orange-400/45 sm:p-8 lg:col-span-2"
    >
      <div className="pointer-events-none absolute -top-20 -right-20 h-72 w-72 rounded-full bg-orange-500/15 blur-[90px] transition-opacity duration-300 group-hover:opacity-140" />
      <div className="relative">
        <div className="flex items-center gap-2">
          <span className="text-2xl leading-none">🔥</span>
          <span className="font-[family-name:var(--font-cond)] text-xs font-bold tracking-[0.16em] text-orange-400 uppercase">Top Projected · This Week</span>
        </div>
        <div className="mt-4 flex flex-wrap items-end justify-between gap-6">
          <div className="flex min-w-0 items-center gap-3">
            <TeamBadge team={player.team} size="md" />
            <div className="min-w-0">
              <p className="truncate font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-50 uppercase sm:text-5xl">{player.name}</p>
              <p className="mt-1 text-sm text-navy-400">
                {player.team} · {positionLabel(player.position)} · £{player.price}m
              </p>
            </div>
          </div>
          <div className="shrink-0 text-right">
            <p className="animate-rise font-mono text-5xl leading-none font-extrabold tabular-nums text-orange-400 sm:text-6xl">{player.totalPoints.toFixed(1)}</p>
            <p className="mt-1 text-[10px] tracking-wide text-navy-500 uppercase">Projected points</p>
          </div>
        </div>
      </div>
      <div className="relative mt-6 flex flex-wrap gap-2 border-t border-navy-800/80 pt-4">
        <Chip label="Rating" value={player.rating !== null ? player.rating.toFixed(1) : "—"} />
        <Chip label="Matchup" value={player.matchup ?? "—"} />
        <Chip label="Ownership" value={player.ownershipPct !== null ? `${player.ownershipPct.toFixed(1)}%` : "—"} />
      </div>
    </Link>
  );
}

// A small, real-data "floating" card in the hero composition - deliberately
// staggered/rotated rather than stacked in a neat row. Ported from the
// sibling projects.
function HeroFloatCard({ href, team, eyebrow, title, sub, value, valueLabel, accent, className, delayMs }: { href: string; team: string; eyebrow: string; title: string; sub?: string; value: string; valueLabel: string; accent: string; className: string; delayMs: number }) {
  return (
    <Link
      href={href}
      className={`group absolute animate-rise rounded-2xl border border-navy-700/70 bg-navy-950/75 p-4 backdrop-blur-md transition-all duration-300 hover:-translate-y-1.5 ${className}`}
      style={{ animationDelay: `${delayMs}ms`, boxShadow: `0 25px 60px -20px rgba(0,0,0,0.85), 0 0 0 1px color-mix(in srgb, ${accent} 30%, transparent)` }}
    >
      <div className="flex items-center gap-2">
        <TeamBadge team={team} size="sm" />
        <span className="min-w-0 truncate font-[family-name:var(--font-cond)] text-[10px] font-bold tracking-[0.16em] uppercase" style={{ color: accent }}>
          {eyebrow}
        </span>
      </div>
      <p className="mt-2 truncate font-[family-name:var(--font-cond)] text-base font-extrabold text-navy-50 uppercase">{title}</p>
      {sub && <p className="truncate text-[11px] text-navy-500">{sub}</p>}
      <p className="mt-2 font-mono text-2xl font-extrabold tabular-nums" style={{ color: accent }}>
        {value}
      </p>
      <p className="text-[9px] tracking-wide text-navy-500 uppercase">{valueLabel}</p>
    </Link>
  );
}

function LivePulseDot({ color = "bg-emerald-400" }: { color?: string }) {
  return (
    <span className="relative flex h-2 w-2">
      <span className={`absolute inline-flex h-full w-full animate-ping rounded-full ${color} opacity-75`} />
      <span className={`relative inline-flex h-2 w-2 rounded-full ${color}`} />
    </span>
  );
}

// The divider-per-item border is sm:-only - once the row wraps onto a
// second mobile line, an unconditional border would leave a stray vertical
// line on the wrapped line's first item with nothing to divide. Ported
// from the sibling projects.
function TickerStat({ label, value, first = false }: { label: string; value: string; first?: boolean }) {
  return (
    <div className={`flex items-baseline gap-2 ${first ? "" : "sm:border-l sm:border-navy-800 sm:pl-4 md:pl-6"}`}>
      <span className="animate-rise font-[family-name:var(--font-cond)] text-xl font-extrabold tabular-nums text-navy-100 sm:text-2xl">{value}</span>
      <span className="text-[11px] tracking-wide text-navy-500 uppercase sm:text-xs">{label}</span>
    </div>
  );
}

function SectionTag({ children }: { children: React.ReactNode }) {
  return <p className="font-[family-name:var(--font-cond)] text-xs font-bold tracking-[0.16em] text-sky-400 uppercase">{children}</p>;
}

function ToolCTA({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="group mt-6 inline-flex w-fit items-center gap-2 rounded-md bg-sky-500 px-5 py-2.5 font-[family-name:var(--font-cond)] text-sm font-bold tracking-wide text-navy-950 uppercase transition-colors hover:bg-sky-300"
    >
      {label}
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="3" className="transition-transform duration-200 group-hover:translate-x-1">
        <path d="M5 12h14M13 6l6 6-6 6" />
      </svg>
    </Link>
  );
}

function SecondaryCTA({ href, label }: { href: string; label: string }) {
  return (
    <Link
      href={href}
      className="mt-6 inline-flex w-fit items-center gap-2 rounded-md border border-navy-700 px-5 py-2.5 font-[family-name:var(--font-cond)] text-sm font-bold tracking-wide text-navy-200 uppercase transition-colors hover:border-sky-500/60 hover:text-sky-300"
    >
      {label}
    </Link>
  );
}

function OpenToolBar({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="relative z-10 flex items-center justify-between border-t border-navy-800 bg-navy-950/80 px-4 py-2.5 text-xs font-semibold text-sky-300 hover:text-sky-200 hover:bg-navy-900">
      <span>{label}</span>
      <span aria-hidden>→</span>
    </Link>
  );
}

function EmptyPreview({ label }: { label: string }) {
  return <div className="flex min-h-[220px] items-center justify-center rounded-2xl border border-dashed border-navy-800 bg-navy-900/40 p-8 text-center text-sm text-navy-500">{label}</div>;
}

export default async function HomePage() {
  const supabase = createPublicClient();

  const [{ count: activePlayers }, { count: teamCount }, { data: latestVersionRow }] = await Promise.all([
    supabase.from("players").select("*", { count: "exact", head: true }).eq("is_active", true),
    supabase.from("teams").select("*", { count: "exact", head: true }),
    supabase.from("algorithm_versions").select("id").order("id", { ascending: false }).limit(1).maybeSingle(),
  ]);
  const algorithmVersionId = latestVersionRow?.id;

  const { data: gwRow } = algorithmVersionId
    ? await supabase.from("projections").select("gameweek").eq("horizon", 1).eq("algorithm_version_id", algorithmVersionId).order("gameweek", { ascending: false }).limit(1).maybeSingle()
    : { data: null };
  const gameweek = gwRow?.gameweek;

  type ProjectionRow = {
    total_points: number;
    rating: number | null;
    data_confidence: number | null;
    players: { id: number; full_name: string; position: Position; price: number; ownership_pct: number | null; team_id: number; teams: { name: string; abbr: string } | null };
  };

  // Real perf note: none of these four queries reads another's result -
  // all only depend on horizon/gameweek/algorithmVersionId, already
  // resolved above.
  const [{ data: rows, error }, { data: fixtureRows }, { data: allWinTotals }, { data: currentWeekDifficulty }] = await Promise.all([
    algorithmVersionId && gameweek
      ? supabase
          .from("projections")
          .select("total_points, rating, data_confidence, players!inner(id, full_name, position, price, ownership_pct, team_id, teams!team_id(name, abbr))")
          .eq("horizon", 1)
          .eq("gameweek", gameweek)
          .eq("algorithm_version_id", algorithmVersionId)
          .order("total_points", { ascending: false })
      : Promise.resolve({ data: [], error: null }),
    gameweek
      ? supabase.from("fixtures").select("home_team_id, away_team_id, kickoff_at, home:teams!home_team_id(abbr), away:teams!away_team_id(abbr)").eq("gameweek", gameweek)
      : Promise.resolve({ data: [] }),
    supabase.from("team_schedule_difficulty").select("opponent_win_total").not("opponent_win_total", "is", null).eq("is_bye", false),
    gameweek
      ? supabase.from("team_schedule_difficulty").select("team_id, is_home, is_bye, opponent_win_total, team:teams!team_id(abbr), opponent:teams!opponent_team_id(abbr)").eq("gameweek", gameweek)
      : Promise.resolve({ data: [] }),
  ]);
  if (error) throw new Error(`Failed to load projections: ${error.message}`);

  type FixtureJoin = { home_team_id: number; away_team_id: number; home: { abbr: string } | null; away: { abbr: string } | null };
  const opponentByTeamId = new Map<number, { opponentAbbr: string; isHome: boolean }>();
  for (const f of (fixtureRows ?? []) as unknown as FixtureJoin[]) {
    if (f.home && f.away) {
      opponentByTeamId.set(f.home_team_id, { opponentAbbr: f.away.abbr, isHome: true });
      opponentByTeamId.set(f.away_team_id, { opponentAbbr: f.home.abbr, isHome: false });
    }
  }

  const thresholds = computeDifficultyThresholds((allWinTotals ?? []).map((r) => Number(r.opponent_win_total)));
  const difficultyByTeamId = new Map<number, DifficultyTier | null>();
  type ScheduleJoin = { team_id: number; is_home: boolean | null; is_bye: boolean; opponent_win_total: number | null; team: { abbr: string } | null; opponent: { abbr: string } | null };
  const scheduleRows = (currentWeekDifficulty ?? []) as unknown as ScheduleJoin[];
  for (const row of scheduleRows) {
    difficultyByTeamId.set(row.team_id, difficultyTier(row.opponent_win_total === null ? null : Number(row.opponent_win_total), row.is_bye, thresholds));
  }

  const ratingsPlayers = ((rows ?? []) as unknown as ProjectionRow[]).map((r) => {
    const opponent = opponentByTeamId.get(r.players.team_id);
    return {
      playerId: r.players.id,
      name: r.players.full_name,
      position: r.players.position,
      price: Number(r.players.price),
      team: r.players.teams?.abbr ?? "—",
      ownershipPct: r.players.ownership_pct === null ? null : Number(r.players.ownership_pct),
      matchup: opponent ? `${opponent.isHome ? "vs" : "@"} ${opponent.opponentAbbr}` : null,
      opponentTier: difficultyByTeamId.get(r.players.team_id) ?? null,
      totalPoints: Number(r.total_points),
      rating: r.rating === null ? null : Number(r.rating),
      dataConfidence: r.data_confidence === null ? null : Number(r.data_confidence),
    };
  });

  const players: PlayerRow[] = ratingsPlayers.map((p) => ({
    playerId: p.playerId,
    name: p.name,
    position: p.position,
    price: p.price,
    team: p.team,
    opponent: p.matchup ?? "—",
    opponentTier: p.opponentTier,
    totalPoints: p.totalPoints,
    dataConfidence: p.dataConfidence,
  }));

  // "Differential" - the highest-projected real player owned by under 15%
  // of managers, excluding this week's own #1 overall projected player so
  // the card surfaces a genuinely distinct real signal. Falls back to the
  // single lowest-owned player with a real ownership figure at all if
  // nobody this week clears the bar.
  const DIFFERENTIAL_OWNERSHIP_CEILING = 15;
  const differentialCandidates = ratingsPlayers.filter((p) => p.playerId !== ratingsPlayers[0]?.playerId);
  const lowOwnedPool = differentialCandidates.filter((p) => p.ownershipPct !== null && p.ownershipPct < DIFFERENTIAL_OWNERSHIP_CEILING);
  const differential =
    lowOwnedPool.length > 0
      ? [...lowOwnedPool].sort((a, b) => b.totalPoints - a.totalPoints)[0]
      : ([...differentialCandidates].filter((p) => p.ownershipPct !== null).sort((a, b) => (a.ownershipPct ?? 0) - (b.ownershipPct ?? 0))[0] ?? null);

  // "Best Value" - real points per real £m.
  const bestValue = ratingsPlayers.filter((p) => p.price > 0).sort((a, b) => b.totalPoints / b.price - a.totalPoints / a.price)[0] ?? null;

  // "Best Matchup" - the single real team with the easiest real upcoming
  // opponent this week (lowest real Vegas win-total among non-bye teams) -
  // same real schedule-difficulty data the /fixtures tool itself uses.
  const bestMatchupRow = [...scheduleRows].filter((r) => !r.is_bye && r.opponent_win_total !== null).sort((a, b) => (a.opponent_win_total ?? 0) - (b.opponent_win_total ?? 0))[0] ?? null;
  const bestMatchup = bestMatchupRow
    ? {
        team: bestMatchupRow.team?.abbr ?? "—",
        opponent: bestMatchupRow.opponent?.abbr ?? "—",
        isHome: bestMatchupRow.is_home,
        winTotal: bestMatchupRow.opponent_win_total !== null ? Number(bestMatchupRow.opponent_win_total) : null,
        tierLabel: DIFFICULTY_LABELS[difficultyTier(bestMatchupRow.opponent_win_total, false, thresholds)],
      }
    : null;

  const previewSlice = players.slice(0, 10);

  // Best Team preview - same real solver /best-team itself uses.
  const bestTeamPool = ratingsPlayers.map((p) => ({
    id: p.playerId,
    name: p.name,
    position: p.position,
    price: p.price,
    teamId: 0,
    teamAbbr: p.team,
    tier: "any" as const,
    gw1TotalPoints: p.totalPoints,
  }));
  const { result: bestTeam } = buildBestTeam(bestTeamPool);

  // Fixture Difficulty preview - same real query/shape the /fixtures tool
  // itself uses.
  const { data: teamsForGrid } = await supabase.from("teams").select("id, name, abbr").order("name");
  const { data: scheduleForGrid } = await supabase
    .from("team_schedule_difficulty")
    .select("team_id, gameweek, is_home, is_bye, opponent_win_total, opponent:teams!opponent_team_id(abbr)")
    .order("gameweek");
  type GridRawRow = { team_id: number; gameweek: number; is_home: boolean | null; is_bye: boolean; opponent_win_total: number | null; opponent: { abbr: string } | null };
  const gridSchedule: TeamScheduleRow[] = ((scheduleForGrid ?? []) as unknown as GridRawRow[]).map((r) => ({
    teamId: r.team_id,
    gameweek: r.gameweek,
    isHome: r.is_home,
    isBye: r.is_bye,
    opponentAbbr: r.opponent?.abbr ?? null,
    opponentWinTotal: r.opponent_win_total === null ? null : Number(r.opponent_win_total),
  }));
  const gridThresholds = computeDifficultyThresholds(gridSchedule.filter((s) => s.opponentWinTotal !== null && !s.isBye).map((s) => s.opponentWinTotal as number));

  // Player Face-Off preview - a REAL completed comparison (this week's #1
  // and #2 projected players), not the tool's own empty picker screen.
  const [compareA, compareB] =
    ratingsPlayers.length >= 2 ? await (async () => { const r = await loadComparePlayers(supabase, ratingsPlayers[0].playerId, ratingsPlayers[1].playerId); return [r.playerA, r.playerB]; })() : [null, null];

  return (
    <main className="min-w-0 flex-1">
      {/* ================= HERO ================= */}
      <section className="relative isolate overflow-hidden border-b border-navy-800">
        <div className="absolute inset-0 -z-10">
          <div className="absolute inset-0 bg-gradient-to-br from-navy-950 via-navy-950 to-navy-900" />
          <div className="bg-dot-grid absolute inset-0 opacity-[0.12]" />
        </div>
        <div className="pointer-events-none absolute top-[-15%] left-[8%] -z-10 h-[380px] w-[380px] rounded-full bg-sky-500/10 blur-[130px]" />
        <div className="pointer-events-none absolute right-[-8%] bottom-[-15%] -z-10 h-[340px] w-[340px] rounded-full bg-orange-500/[0.08] blur-[120px]" />

        <div className="relative mx-auto grid max-w-6xl grid-cols-1 gap-12 px-6 py-14 sm:px-10 sm:py-20 lg:grid-cols-[1.05fr_0.95fr] lg:items-center lg:gap-8">
          <div>
            {gameweek !== null && gameweek !== undefined && (
              <div className="flex items-center gap-2">
                <LivePulseDot />
                <span className="font-mono text-[11px] font-bold tracking-[0.14em] text-emerald-400 uppercase">Live · Gameweek {gameweek}</span>
              </div>
            )}
            <p className="mt-4 font-[family-name:var(--font-cond)] text-xs font-bold tracking-[0.32em] text-sky-400 uppercase">FanTeam NFL × Hail Mary</p>
            <h1 className="mt-2 font-[family-name:var(--font-cond)] text-[2.75rem] leading-[0.98] font-extrabold text-navy-50 sm:text-6xl lg:text-[4.25rem]">
              KNOW THE SLATE
              <br />
              BEFORE KICKOFF.
            </h1>
            <p className="mt-5 max-w-md text-base text-navy-300">
              Real projected points for every FanTeam NFL Regular Season player, five layers deep - lineup status, form, fixture quantity and quality, and
              live odds. Real prices, a real £{BUDGET_CAP}M budget, real matchups.
            </p>
            <div className="flex flex-wrap items-center gap-3">
              <ToolCTA href="/" label="Explore Projections" />
              <SecondaryCTA href="/best-team" label="Build Best Team" />
            </div>
          </div>

          <div className="relative hidden h-[300px] sm:block sm:h-[340px] lg:h-[380px]">
            <svg aria-hidden viewBox="0 0 200 200" className="absolute top-1/2 right-[6%] h-[220px] w-[220px] -translate-y-1/2 text-navy-700/40 opacity-60">
              <circle cx="100" cy="100" r="94" fill="none" stroke="currentColor" strokeWidth="0.75" />
              <circle cx="100" cy="100" r="62" fill="none" stroke="currentColor" strokeWidth="0.75" />
              <circle cx="100" cy="100" r="30" fill="none" stroke="currentColor" strokeWidth="0.75" />
              <path d="M100 6 V194 M6 100 H194" stroke="currentColor" strokeWidth="0.5" />
            </svg>

            {ratingsPlayers[0] && (
              <HeroFloatCard
                href="/"
                team={ratingsPlayers[0].team}
                eyebrow="🔥 Top Projected"
                title={ratingsPlayers[0].name}
                sub={`${ratingsPlayers[0].team} · ${positionLabel(ratingsPlayers[0].position)}`}
                value={ratingsPlayers[0].totalPoints.toFixed(1)}
                valueLabel="Projected pts"
                accent="#fb923c"
                className="top-0 right-[4%] w-[220px] rotate-2 sm:w-[240px]"
                delayMs={0}
              />
            )}
            {ratingsPlayers[1] && (
              <HeroFloatCard
                href="/"
                team={ratingsPlayers[1].team}
                eyebrow="⭐ Also Rated"
                title={ratingsPlayers[1].name}
                sub={`${ratingsPlayers[1].team} · ${positionLabel(ratingsPlayers[1].position)}`}
                value={ratingsPlayers[1].totalPoints.toFixed(1)}
                valueLabel="Projected pts"
                accent="#38bdf8"
                className="top-[42%] left-0 w-[200px] -rotate-2 sm:w-[220px]"
                delayMs={120}
              />
            )}
            {bestMatchup && (
              <HeroFloatCard
                href="/fixtures"
                team={bestMatchup.team}
                eyebrow="🏟️ Best Matchup"
                title={bestMatchup.team}
                sub={`${bestMatchup.isHome ? "vs" : "@"} ${bestMatchup.opponent}${bestMatchup.winTotal !== null ? ` · ${bestMatchup.winTotal.toFixed(1)} win total` : ""}`}
                value={bestMatchup.tierLabel}
                valueLabel="Real matchup tier"
                accent="#34d399"
                className="right-[10%] bottom-0 w-[210px] rotate-1 sm:w-[230px]"
                delayMs={240}
              />
            )}
          </div>
        </div>
      </section>

      {/* ================= CREDIBILITY TICKER ================= */}
      <section className="border-b border-navy-800 bg-navy-950 px-6 py-4 sm:px-10">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-3 sm:gap-x-6">
          <TickerStat first label="Players tracked" value={activePlayers !== null ? String(activePlayers) : "—"} />
          <TickerStat label="Teams tracked" value={teamCount !== null ? String(teamCount) : "—"} />
          <TickerStat label="Projections" value={ratingsPlayers.length > 0 ? ratingsPlayers.length.toLocaleString() : "—"} />
        </div>
      </section>

      {/* ================= WHAT THE MODEL LIKES RIGHT NOW ================= */}
      {gameweek !== null && gameweek !== undefined && (
        <section className="relative overflow-hidden border-b border-navy-800 bg-navy-950/40 px-6 py-10 sm:px-10 sm:py-12">
          <div className="bg-dot-grid pointer-events-none absolute inset-0 opacity-[0.06]" />
          <Reveal className="relative mx-auto max-w-6xl">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <LivePulseDot />
                <SectionTag>Hail Mary · Gameweek {gameweek}</SectionTag>
              </div>
              <span className="font-mono text-[11px] text-navy-500">Refreshed every pipeline run</span>
            </div>
            <h2 className="mt-1.5 font-[family-name:var(--font-cond)] text-2xl font-extrabold text-navy-100 uppercase sm:text-[28px]">What the model likes right now</h2>

            <div className="mt-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
              {ratingsPlayers[0] && <FeaturedPickCard player={ratingsPlayers[0]} />}

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-1">
                {bestValue && (
                  <IntelCard href="/value-finder" emoji="💎" label="Best Value" team={bestValue.team} name={bestValue.name} meta={`£${bestValue.price}m`} value={(bestValue.totalPoints / bestValue.price).toFixed(2)} valueLabel="Pts per £m" accent="#38bdf8" />
                )}
                {differential && (
                  <IntelCard
                    href="/"
                    emoji="👀"
                    label="Differential"
                    team={differential.team}
                    name={differential.name}
                    meta={differential.ownershipPct !== null ? `${differential.ownershipPct.toFixed(1)}% owned` : "Ownership unknown"}
                    value={differential.totalPoints.toFixed(1)}
                    valueLabel="Projected pts"
                    accent="#a78bfa"
                  />
                )}
                {bestMatchup && (
                  <IntelCard
                    href="/fixtures"
                    emoji="🏟️"
                    label="Best Matchup"
                    team={bestMatchup.team}
                    name={bestMatchup.team}
                    meta={`${bestMatchup.isHome ? "vs" : "@"} ${bestMatchup.opponent}`}
                    value={bestMatchup.winTotal !== null ? bestMatchup.winTotal.toFixed(1) : "—"}
                    valueLabel="Opponent win total"
                    accent="#34d399"
                  />
                )}
              </div>
            </div>
          </Reveal>
        </section>
      )}

      {/* ================= TOOL SHOWCASE ================= */}
      <section className="relative px-6 py-14 sm:px-10 sm:py-20">
        <div className="mx-auto max-w-6xl">
          <div className="text-center">
            <SectionTag>Explore Hail Mary</SectionTag>
            <h2 className="mt-2 font-[family-name:var(--font-cond)] text-3xl font-extrabold text-navy-100 uppercase sm:text-4xl">Everything you need to attack the slate</h2>
          </div>

          {/* ---- 1. Projections ---- */}
          <Reveal className="relative mt-16 grid grid-cols-1 items-center gap-8 lg:grid-cols-2 lg:gap-12">
            <div className="relative">
              <SectionTag>Hail Mary Projections</SectionTag>
              <h3 className="mt-2 font-[family-name:var(--font-cond)] text-3xl font-extrabold text-navy-100">Every player. Every week. Every horizon.</h3>
              <p className="mt-3 max-w-md text-sm text-navy-300">
                This week, or a 2/3/5-week outlook - every real active player priced with a projected points total, real price, real value, sortable any
                way you like.
              </p>
              <ToolCTA href="/" label="Explore Projections" />
            </div>
            <div className="relative">
              {previewSlice.length > 0 ? (
                <BrowserFrame url="nfl.hailmaryfantasysports.co.uk" accent="#38bdf8" fade maxHeight="560px">
                  <div className="p-4 sm:p-5">
                    <RatingsTable players={previewSlice} horizon={1} />
                  </div>
                </BrowserFrame>
              ) : (
                <EmptyPreview label="Projections land here the moment this week's numbers are frozen." />
              )}
              <div className="-mt-px">
                <OpenToolBar href="/" label={`See all ${activePlayers ?? ""} players →`} />
              </div>
            </div>
          </Reveal>

          {/* ---- 2. Fixture Difficulty ---- */}
          <Reveal className="relative mt-20 grid grid-cols-1 items-center gap-8 lg:grid-cols-2 lg:gap-12">
            <div className="relative order-2 lg:order-1">
              {(teamsForGrid ?? []).length > 0 ? (
                <BrowserFrame url="nfl.hailmaryfantasysports.co.uk/fixtures" accent="#fb7185" fade maxHeight="420px">
                  <div className="p-4 sm:p-5">
                    <FixtureDifficultyGrid teams={teamsForGrid ?? []} schedule={gridSchedule} thresholds={gridThresholds} currentGameweek={gameweek ?? 1} />
                  </div>
                </BrowserFrame>
              ) : (
                <EmptyPreview label="Schedule difficulty lands here once real fixtures are ingested." />
              )}
              <div className="-mt-px">
                <OpenToolBar href="/fixtures" label="View full schedule →" />
              </div>
            </div>
            <div className="relative order-1 lg:order-2">
              <SectionTag>Fixture Difficulty</SectionTag>
              <h3 className="mt-2 font-[family-name:var(--font-cond)] text-3xl font-extrabold text-navy-100">Know the matchup before you set your team.</h3>
              <p className="mt-3 max-w-md text-sm text-navy-300">
                Real, market-derived opponent strength (Sharp Football Analysis&apos;s Vegas-win-total model) for every real team, every real week - rank
                the best and worst upcoming runs.
              </p>
              <ToolCTA href="/fixtures" label="View Fixture Difficulty" />
            </div>
          </Reveal>

          {/* ---- 3. Best Team ---- */}
          <Reveal className="relative mt-20 overflow-hidden rounded-3xl">
            <div className="bg-tactical-lines pointer-events-none absolute inset-0 opacity-[0.35]" />
            <div className="pointer-events-none absolute top-1/2 left-1/2 h-[420px] w-[420px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-emerald-500/[0.06] blur-[100px]" />
            <div className="relative grid grid-cols-1 items-center gap-8 p-1 lg:grid-cols-2 lg:gap-12 lg:p-6">
              <div className="relative">
                <SectionTag>Best Team</SectionTag>
                <h3 className="mt-2 font-[family-name:var(--font-cond)] text-3xl font-extrabold text-navy-100">The strongest real legal roster, right now.</h3>
                <p className="mt-3 max-w-md text-sm text-navy-300">
                  Every real active player, real prices, the real £{BUDGET_CAP}M cap and 2-per-team limit - a snapshot for this gameweek, not a season plan.
                </p>
                <ToolCTA href="/best-team" label="Build Best Team" />
              </div>
              {bestTeam ? (
                <Link href="/best-team" className="group relative block transition-transform duration-300 hover:-translate-y-1.5">
                  <BrowserFrame url="nfl.hailmaryfantasysports.co.uk/best-team" accent="#a78bfa">
                    <div className="p-3 sm:p-4">
                      <div className="mb-3 flex flex-wrap gap-3 px-1">
                        <div className="rounded-lg border border-navy-800 bg-navy-950/60 px-3 py-1.5">
                          <p className="font-[family-name:var(--font-cond)] text-base font-bold text-navy-100">{bestTeam.totalPoints.toFixed(1)} pts</p>
                          <p className="text-[9px] tracking-wide text-navy-500 uppercase">Projected total</p>
                        </div>
                        <div className="rounded-lg border border-navy-800 bg-navy-950/60 px-3 py-1.5">
                          <p className="font-[family-name:var(--font-cond)] text-base font-bold text-navy-100">£{bestTeam.totalPrice.toFixed(1)}m</p>
                          <p className="text-[9px] tracking-wide text-navy-500 uppercase">Squad price</p>
                        </div>
                      </div>
                      <ul className="divide-y divide-navy-800 rounded-xl border border-navy-800 bg-navy-900">
                        {bestTeam.rosterEntries.map(({ slot, player }) => (
                          <li key={slot} className="flex items-center justify-between gap-3 px-3 py-2">
                            <div className="flex min-w-0 items-center gap-2.5">
                              <span className="w-9 shrink-0 font-[family-name:var(--font-cond)] text-[10px] font-bold tracking-wide text-navy-500 uppercase">{slot}</span>
                              {player && <TeamBadge team={player.teamAbbr} size="sm" />}
                              <p className="min-w-0 truncate text-xs font-semibold text-navy-100">{player?.name ?? "—"}</p>
                            </div>
                            <span className="shrink-0 font-mono text-xs font-bold text-sky-300">{player ? player.gw1TotalPoints.toFixed(1) : "—"}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </BrowserFrame>
                </Link>
              ) : (
                <EmptyPreview label="Best Team appears here once this week's projections are live." />
              )}
            </div>
          </Reveal>

          {/* ---- 4. Value Finder ---- */}
          <Reveal className="relative mt-20 grid grid-cols-1 items-center gap-8 lg:grid-cols-2 lg:gap-12">
            <div className="relative order-2 lg:order-1">
              {previewSlice.length > 0 ? (
                <BrowserFrame url="nfl.hailmaryfantasysports.co.uk/value-finder" accent="#34d399" fade maxHeight="520px">
                  <div className="p-4 sm:p-5">
                    <RatingsTable players={previewSlice} horizon={1} defaultSortMode="value" />
                  </div>
                </BrowserFrame>
              ) : (
                <EmptyPreview label="Value Finder lights up as soon as this week's projections are live." />
              )}
              <div className="-mt-px">
                <OpenToolBar href="/value-finder" label="Open Value Finder →" />
              </div>
            </div>
            <div className="relative order-1 lg:order-2">
              <SectionTag>Value Finder</SectionTag>
              <h3 className="mt-2 font-[family-name:var(--font-cond)] text-3xl font-extrabold text-navy-100">Free up budget without sacrificing points.</h3>
              <p className="mt-3 max-w-md text-sm text-navy-300">
                Cheap players who reliably produce for their price, ranked by real projected points per real £m for this horizon.
              </p>
              <ToolCTA href="/value-finder" label="Find Value" />
            </div>
          </Reveal>

          {/* ---- 5. Player Face-Off ---- */}
          <Reveal className="relative mt-20 overflow-hidden rounded-3xl">
            <div className="pointer-events-none absolute top-0 left-1/4 h-72 w-72 rounded-full bg-amber-500/[0.06] blur-[100px]" />
            <div className="pointer-events-none absolute right-1/4 bottom-0 h-72 w-72 rounded-full bg-rose-500/[0.06] blur-[100px]" />
            <div className="relative p-1 lg:p-6">
              <div className="relative text-center">
                <SectionTag>Player Face-Off</SectionTag>
                <h3 className="mt-2 font-[family-name:var(--font-cond)] text-3xl font-extrabold text-navy-100">Pick any two players, head-to-head.</h3>
              </div>
              <div className="relative mt-8 flex justify-center">
                {compareA && compareB ? (
                  <Link href={`/compare?a=${compareA.id}&b=${compareB.id}`} className="group block w-full max-w-xl transition-transform duration-300 hover:-translate-y-1.5">
                    <BrowserFrame url="nfl.hailmaryfantasysports.co.uk/compare" accent="#fb7185" fade maxHeight="420px">
                      <div className="p-3 sm:p-4">
                        <CompareView playerA={compareA} playerB={compareB} />
                      </div>
                    </BrowserFrame>
                  </Link>
                ) : (
                  <EmptyPreview label="Player Face-Off comparisons appear here once this week's projections are live." />
                )}
              </div>
              <div className="mt-5 flex justify-center">
                <ToolCTA href="/compare" label="Compare Players" />
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ================= METHODOLOGY ================= */}
      <section className="relative overflow-hidden border-t border-navy-800 bg-navy-950/60 px-6 py-10 sm:px-10">
        <Reveal className="relative mx-auto max-w-6xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-md">
              <SectionTag>How it&apos;s built</SectionTag>
              <h3 className="mt-1 font-[family-name:var(--font-cond)] text-xl font-extrabold text-navy-100 uppercase">Five real layers, never one black box</h3>
              <p className="mt-1.5 text-xs text-navy-400">Every projection is a weighted blend of five independently-tracked real layers.</p>
            </div>
            <div className="grid grid-cols-5 gap-2 sm:gap-3">
              {LAYERS.map((layer, i) => (
                <div key={layer.name} className="rounded-lg border border-navy-800 bg-navy-900 px-2 py-2.5 text-center sm:px-3">
                  <p className="font-[family-name:var(--font-cond)] text-[10px] font-bold tracking-wide text-sky-400 uppercase">L{i + 1}</p>
                  <p className="mt-0.5 truncate font-[family-name:var(--font-cond)] text-[11px] font-bold text-navy-100 sm:text-xs">{layer.name}</p>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </section>

      {/* ================= FINAL CTA ================= */}
      <section className="relative overflow-hidden border-t border-navy-800 px-6 py-16 text-center sm:px-10 sm:py-20">
        <div className="pointer-events-none absolute inset-0" style={{ background: "radial-gradient(80% 120% at 50% 0%, #38bdf81a 0%, transparent 60%)" }} />
        <div className="bg-dot-grid pointer-events-none absolute inset-0 opacity-[0.08]" />
        <Reveal className="relative mx-auto max-w-2xl">
          <h2 className="font-[family-name:var(--font-cond)] text-3xl font-extrabold text-navy-100 uppercase sm:text-4xl">Ready for the next slate?</h2>
          <p className="mt-3 text-base text-navy-300">Let Hail Mary do the numbers.</p>
          <div className="mt-6 flex justify-center">
            <ToolCTA href="/" label="Explore the Projections" />
          </div>
        </Reveal>
      </section>
    </main>
  );
}
