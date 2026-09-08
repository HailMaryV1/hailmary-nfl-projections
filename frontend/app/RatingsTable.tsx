"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { POSITION_ORDER, positionLabel } from "@/lib/positions";

export type PlayerRow = {
  playerId: number;
  name: string;
  position: string;
  price: number;
  team: string;
  opponent: string;
  totalPoints: number;
  dataConfidence: number | null;
};

const FILTERS = ["ALL", ...POSITION_ORDER] as const;

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

  const filtered = useMemo(() => {
    return filter === "ALL" ? players : players.filter((p) => p.position === filter);
  }, [players, filter]);

  const playerHref = (playerId: number) => (horizon === 1 ? `/players/${playerId}` : `/players/${playerId}?horizon=${horizon}`);

  return (
    <div className="flex min-w-0 flex-col gap-4">
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
                  <div className="text-xs text-navy-400">
                    {p.team} {p.opponent} · £{p.price}m
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
                <td className="py-2 pr-3 text-navy-400">{p.opponent}</td>
                <td className="py-2 pr-3 text-right font-mono tabular-nums text-navy-300">£{p.price}m</td>
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
