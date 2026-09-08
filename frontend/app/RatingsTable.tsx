"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { POSITION_ORDER, positionLabel } from "@/lib/positions";
import { DIFFICULTY_COLORS, type DifficultyTier } from "@/lib/fixtureDifficulty";

export type PlayerRow = {
  playerId: number;
  name: string;
  position: string;
  price: number;
  team: string;
  opponent: string;
  opponentTier: DifficultyTier | null;
  totalPoints: number;
  dataConfidence: number | null;
};

const FILTERS = ["ALL", ...POSITION_ORDER] as const;
const SORT_MODES = ["points", "value"] as const;
type SortMode = (typeof SORT_MODES)[number];

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

function OppTag({ opponent, tier }: { opponent: string; tier: DifficultyTier | null }) {
  if (!tier) return <span className="text-navy-400">{opponent}</span>;
  const colors = DIFFICULTY_COLORS[tier];
  return (
    <span className="inline-block rounded px-1.5 py-0.5 font-mono text-xs font-semibold" style={{ backgroundColor: colors.bg, color: colors.text }}>
      {opponent}
    </span>
  );
}

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

export default function RatingsTable({ players, horizon }: { players: PlayerRow[]; horizon: number }) {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("ALL");
  const [team, setTeam] = useState<string>("ALL");
  const [sortMode, setSortMode] = useState<SortMode>("points");

  const teams = useMemo(() => [...new Set(players.map((p) => p.team))].sort(), [players]);

  const filtered = useMemo(() => {
    let list = filter === "ALL" ? players : players.filter((p) => p.position === filter);
    if (team !== "ALL") list = list.filter((p) => p.team === team);
    const withValue = list.map((p) => ({ ...p, value: p.price > 0 ? p.totalPoints / p.price : 0 }));
    return withValue.sort((a, b) => (sortMode === "points" ? b.totalPoints - a.totalPoints : b.value - a.value));
  }, [players, filter, team, sortMode]);

  const playerHref = (playerId: number) => (horizon === 1 ? `/players/${playerId}` : `/players/${playerId}?horizon=${horizon}`);

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

        <select
          value={team}
          onChange={(e) => setTeam(e.target.value)}
          className="rounded-md border border-navy-700 bg-navy-950 px-2.5 py-1.5 text-sm text-navy-200 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
        >
          <option value="ALL">All Teams</option>
          {teams.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

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
              Sort: {mode === "points" ? "Points" : "Value"}
            </button>
          ))}
        </div>
      </div>

      {/* Mobile card list - the table below overflows badly under sm:,
          same reason every other list view in the Hail Mary portfolio
          gets a separate card layout rather than a scrollable table. */}
      <ul className="flex flex-col divide-y divide-navy-800 sm:hidden">
        {filtered.map((p, i) => (
          <li key={p.playerId}>
            <Link href={playerHref(p.playerId)} className="flex items-center justify-between gap-3 py-2.5">
              <div className="flex min-w-0 items-center gap-2">
                <span className="w-5 shrink-0 text-right font-mono text-xs text-navy-500">{i + 1}</span>
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5">
                    <PositionTag position={p.position} />
                    <span className="truncate text-sm font-medium text-navy-100">{p.name}</span>
                  </div>
                  <div className="flex items-center gap-1 text-xs text-navy-400">
                    <span>{p.team}</span>
                    <OppTag opponent={p.opponent} tier={p.opponentTier} />
                    <span>
                      · £{p.price}m · {p.value.toFixed(1)}pts/£m
                    </span>
                  </div>
                </div>
              </div>
              <span className="shrink-0 font-mono text-sm font-semibold tabular-nums text-sky-300">{p.totalPoints.toFixed(1)}</span>
            </Link>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full min-w-0 border-collapse text-sm">
          <thead>
            <tr className="border-b border-navy-800 text-left text-xs uppercase tracking-wide text-navy-500">
              <th className="py-2 pr-3 font-medium">#</th>
              <th className="py-2 pr-3 font-medium">Player</th>
              <th className="py-2 pr-3 font-medium">Team</th>
              <th className="py-2 pr-3 font-medium">Opp</th>
              <th className="py-2 pr-3 text-right font-medium">Price</th>
              <th className="py-2 pr-3 text-right font-medium">Value</th>
              <th className="py-2 pr-3 text-right font-medium">{horizon === 1 ? "Proj Pts" : `Proj Pts (${horizon}wk)`}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p, i) => (
              <tr key={p.playerId} className="border-b border-navy-900 hover:bg-navy-900/60">
                <td className="py-2 pr-3 font-mono text-xs text-navy-500">{i + 1}</td>
                <td className="py-2 pr-3">
                  <Link href={playerHref(p.playerId)} className="flex items-center gap-2">
                    <PositionTag position={p.position} />
                    <span className="font-medium text-navy-100 hover:text-sky-300">{p.name}</span>
                  </Link>
                </td>
                <td className="py-2 pr-3 text-navy-300">{p.team}</td>
                <td className="py-2 pr-3">
                  <OppTag opponent={p.opponent} tier={p.opponentTier} />
                </td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-navy-300">£{p.price}m</td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-navy-400">{p.value.toFixed(1)}</td>
                <td
                  className="py-2 pr-3 text-right font-mono font-semibold tabular-nums text-sky-300"
                  title={p.dataConfidence !== null && p.dataConfidence < 0.3 ? "Limited real data available for this projection yet" : undefined}
                >
                  {p.totalPoints.toFixed(1)}
                  {p.dataConfidence !== null && p.dataConfidence < 0.3 ? <span className="ml-0.5 text-navy-500">~</span> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
