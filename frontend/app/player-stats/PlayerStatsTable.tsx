"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { POSITION_ORDER, positionLabel } from "@/lib/positions";

// Real per-player, season-to-date totals - summed server-side (see
// page.tsx) from every real per-gameweek player_stats row, because this
// table (unlike Dream Team's sibling player_stats) has no season-aggregate
// (gameweek is null) row convention: as of 2026-09-13 the whole table is
// verified empty (real query against the live DB, zero rows), so there is
// no aggregate row to trust even if one existed. `gamesPlayed` is the real
// count of gameweek rows found for this player - it's what tells the UI
// whether a stat of 0 is a real recorded zero or "no real data yet",
// which is why every stat cell is gated on it rather than always printing
// a number.
export type PlayerStatRow = {
  playerId: number;
  name: string;
  position: string;
  team: string;
  gamesPlayed: number;
  totalPoints: number;
  stats: {
    passing_attempts: number;
    passing_completions: number;
    passing_yards: number;
    passing_tds: number;
    interceptions_thrown: number;
    rushing_attempts: number;
    rushing_yards: number;
    rushing_tds: number;
    receptions: number;
    receiving_yards: number;
    receiving_tds: number;
    return_tds: number;
    fumbles_lost: number;
    two_point_conversions: number;
    sacks: number;
    def_interceptions: number;
    fumble_recoveries: number;
    safeties: number;
    blocked_kicks: number;
    def_special_tds: number;
    points_allowed: number;
  };
};

type StatKey = keyof PlayerStatRow["stats"];
type StatColumn = { key: StatKey; label: string };

// Position-appropriate real stats, same reasoning players/[id]/page.tsx
// already applies to its own "Per-stat breakdown" (only show what a
// position can actually produce) - a QB's meaningful columns aren't a
// WR's, and defense_special is scored as one real per-team unit, not per
// individual defender (see 0003_player_stats.sql).
const POSITION_COLUMNS: Record<string, StatColumn[]> = {
  quarterback: [
    { key: "passing_yards", label: "Pass Yds" },
    { key: "passing_tds", label: "Pass TD" },
    { key: "interceptions_thrown", label: "INT" },
    { key: "rushing_yards", label: "Rush Yds" },
  ],
  running_back: [
    { key: "rushing_yards", label: "Rush Yds" },
    { key: "rushing_tds", label: "Rush TD" },
    { key: "receptions", label: "Rec" },
    { key: "receiving_yards", label: "Rec Yds" },
    { key: "receiving_tds", label: "Rec TD" },
  ],
  wide_receiver: [
    { key: "receptions", label: "Rec" },
    { key: "receiving_yards", label: "Rec Yds" },
    { key: "receiving_tds", label: "Rec TD" },
  ],
  tight_end: [
    { key: "receptions", label: "Rec" },
    { key: "receiving_yards", label: "Rec Yds" },
    { key: "receiving_tds", label: "Rec TD" },
  ],
  defense_special: [
    { key: "sacks", label: "Sacks" },
    { key: "def_interceptions", label: "INT" },
    { key: "fumble_recoveries", label: "FR" },
    { key: "safeties", label: "Saf" },
    { key: "blocked_kicks", label: "BLK" },
    { key: "def_special_tds", label: "TD" },
    { key: "points_allowed", label: "Pts Allow" },
  ],
};

// The "ALL" view's column set: every real column any position uses, deduped
// in position order, so it reads left-to-right roughly QB -> RB -> WR/TE ->
// D/ST. Positions that can't produce a given stat show "-" in that cell
// (e.g. a WR's Pass Yds), same discipline the task called for over
// building a different table per position.
const ALL_COLUMNS: StatColumn[] = (() => {
  const seen = new Set<StatKey>();
  const cols: StatColumn[] = [];
  for (const pos of POSITION_ORDER) {
    for (const c of POSITION_COLUMNS[pos] ?? []) {
      if (!seen.has(c.key)) {
        seen.add(c.key);
        cols.push(c);
      }
    }
  }
  return cols;
})();

const FILTERS = ["ALL", ...POSITION_ORDER] as const;
const SORT_MODES = ["points", "yards"] as const;
type SortMode = (typeof SORT_MODES)[number];

function positionColorVar(position: string): string {
  const map: Record<string, string> = {
    quarterback: "--color-pos-qb",
    running_back: "--color-pos-rb",
    wide_receiver: "--color-pos-wr",
    tight_end: "--color-pos-te",
    defense_special: "--color-pos-dst",
  };
  return map[position] ?? "--color-navy-300";
}

// Same small pill as RatingsTable.tsx's PositionTag - not exported from
// there, so replicated here rather than reaching into another module's
// internals.
function PositionTag({ position }: { position: string }) {
  return (
    <span
      className="rounded px-1.5 py-0.5 font-[family-name:var(--font-cond)] text-xs font-bold uppercase tracking-wide"
      style={{ color: `var(${positionColorVar(position)})`, backgroundColor: `color-mix(in srgb, var(${positionColorVar(position)}) 16%, transparent)` }}
    >
      {positionLabel(position)}
    </span>
  );
}

function totalYards(stats: PlayerStatRow["stats"]): number {
  return stats.passing_yards + stats.rushing_yards + stats.receiving_yards;
}

function statCell(row: PlayerStatRow, key: StatKey): string {
  if (row.gamesPlayed === 0) return "—"; // no real games recorded yet - a printed 0 would assert a real result that doesn't exist
  const value = row.stats[key];
  return key === "sacks" ? value.toFixed(1) : String(value);
}

export default function PlayerStatsTable({ players }: { players: PlayerStatRow[] }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("ALL");
  const [sortMode, setSortMode] = useState<SortMode>("points");

  const filtered = useMemo(() => {
    const list = filter === "ALL" ? players : players.filter((p) => p.position === filter);
    return [...list].sort((a, b) =>
      sortMode === "points" ? b.totalPoints - a.totalPoints : totalYards(b.stats) - totalYards(a.stats)
    );
  }, [players, filter, sortMode]);

  const columns = filter === "ALL" ? ALL_COLUMNS : POSITION_COLUMNS[filter] ?? [];

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`rounded-full px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide ${
                f === filter ? "bg-sky-500 text-navy-950" : "bg-navy-900 text-navy-400 hover:bg-navy-800"
              }`}
            >
              {f === "ALL" ? "All" : positionLabel(f)}
            </button>
          ))}
        </div>

        <div className="flex gap-1 rounded-md bg-navy-900 p-0.5">
          {SORT_MODES.map((mode) => (
            <button
              key={mode}
              type="button"
              onClick={() => setSortMode(mode)}
              className={`rounded px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
                sortMode === mode ? "bg-navy-700 text-navy-100" : "text-navy-400 hover:text-navy-200"
              }`}
            >
              Sort: {mode === "points" ? "Points" : "Yards"}
            </button>
          ))}
        </div>
      </div>

      {/* Mobile card list - same reason RatingsTable.tsx's mobile list
          exists (the table overflows badly under sm:), except each card
          always shows the player's OWN position-appropriate stats rather
          than the filter-selected column set, since a QB card showing
          Sacks/Pts Allowed would be meaningless. */}
      <ul className="flex flex-col divide-y divide-navy-800 sm:hidden">
        {filtered.map((p, i) => {
          const ownColumns = POSITION_COLUMNS[p.position] ?? [];
          return (
            <li key={p.playerId}>
              <Link href={`/players/${p.playerId}`} className="flex items-center justify-between gap-3 py-2.5">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="w-5 shrink-0 text-right font-mono text-xs text-navy-500">{i + 1}</span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <PositionTag position={p.position} />
                      <span className="truncate text-sm font-medium text-navy-100">{p.name}</span>
                    </div>
                    <div className="text-xs text-navy-400">
                      {p.team} · GP {p.gamesPlayed}
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2.5 text-xs text-navy-300">
                      {ownColumns.map((c) => (
                        <span key={c.key}>
                          {c.label} {statCell(p, c.key)}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
                <span className="shrink-0 font-mono text-sm font-semibold tabular-nums text-sky-300">
                  {p.gamesPlayed === 0 ? "—" : p.totalPoints.toFixed(1)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>

      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full min-w-0 border-collapse text-sm">
          <thead>
            <tr className="border-b border-navy-800 text-left text-xs uppercase tracking-wide text-navy-500">
              <th className="py-2 pr-3 font-medium">#</th>
              <th className="py-2 pr-3 font-medium">Player</th>
              <th className="py-2 pr-3 font-medium">Team</th>
              <th className="py-2 pr-3 text-right font-medium">GP</th>
              {columns.map((c) => (
                <th key={c.key} className="py-2 pr-3 text-right font-medium">
                  {c.label}
                </th>
              ))}
              <th className="py-2 pr-3 text-right font-medium">Total Pts</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p, i) => (
              <tr key={p.playerId} className="border-b border-navy-900 hover:bg-navy-900/60">
                <td className="py-2 pr-3 font-mono text-xs text-navy-500">{i + 1}</td>
                <td className="py-2 pr-3">
                  <Link href={`/players/${p.playerId}`} className="flex items-center gap-2">
                    <PositionTag position={p.position} />
                    <span className="font-medium text-navy-100 hover:text-sky-300">{p.name}</span>
                  </Link>
                </td>
                <td className="py-2 pr-3 text-navy-300">{p.team}</td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-navy-400">{p.gamesPlayed}</td>
                {columns.map((c) => {
                  // A column not in this row's own position set (only
                  // possible in the ALL view) can't be a real stat for
                  // this player at all, distinct from "0 real games yet".
                  const applicable = (POSITION_COLUMNS[p.position] ?? []).some((oc) => oc.key === c.key);
                  return (
                    <td key={c.key} className="py-2 pr-3 text-right font-mono tabular-nums text-navy-300">
                      {applicable ? statCell(p, c.key) : "—"}
                    </td>
                  );
                })}
                <td className="py-2 pr-3 text-right font-mono font-semibold tabular-nums text-sky-300">
                  {p.gamesPlayed === 0 ? "—" : p.totalPoints.toFixed(1)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
