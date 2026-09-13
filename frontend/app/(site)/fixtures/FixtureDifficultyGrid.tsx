"use client";

import { useMemo, useState } from "react";
import { DIFFICULTY_COLORS, difficultyTier, type DifficultyThresholds } from "@/lib/fixtureDifficulty";

export type TeamScheduleRow = {
  teamId: number;
  gameweek: number;
  isHome: boolean | null;
  isBye: boolean;
  opponentAbbr: string | null;
  opponentWinTotal: number | null;
};

type Team = { id: number; name: string; abbr: string };

const WINDOW_OPTIONS = [4, 6, 8, 18] as const;
const WINDOW_LABELS: Record<number, string> = { 4: "Next 4", 6: "Next 6", 8: "Next 8", 18: "Rest of Season" };

export default function FixtureDifficultyGrid({
  teams,
  schedule,
  thresholds,
  currentGameweek,
}: {
  teams: Team[];
  schedule: TeamScheduleRow[];
  thresholds: DifficultyThresholds;
  currentGameweek: number;
}) {
  const [windowLength, setWindowLength] = useState<(typeof WINDOW_OPTIONS)[number]>(4);
  const [sortDirection, setSortDirection] = useState<"easiest" | "hardest">("easiest");

  const scheduleByTeam = useMemo(() => {
    const map = new Map<number, Map<number, TeamScheduleRow>>();
    for (const row of schedule) {
      if (!map.has(row.teamId)) map.set(row.teamId, new Map());
      map.get(row.teamId)!.set(row.gameweek, row);
    }
    return map;
  }, [schedule]);

  const endGw = Math.min(currentGameweek + windowLength - 1, 18);
  const gameweeks = useMemo(() => {
    const list: number[] = [];
    for (let gw = currentGameweek; gw <= endGw; gw++) list.push(gw);
    return list;
  }, [currentGameweek, endGw]);

  const rows = useMemo(() => {
    return teams
      .map((team) => {
        const teamSchedule = scheduleByTeam.get(team.id);
        const cells = gameweeks.map((gw) => teamSchedule?.get(gw) ?? null);
        const realGames = cells.filter((c) => c && !c.isBye && c.opponentWinTotal !== null);
        const avgWinTotal = realGames.length
          ? realGames.reduce((sum, c) => sum + (c!.opponentWinTotal as number), 0) / realGames.length
          : null;
        return { team, cells, avgWinTotal, realGameCount: realGames.length };
      })
      .sort((a, b) => {
        if (a.avgWinTotal === null) return 1;
        if (b.avgWinTotal === null) return -1;
        return sortDirection === "easiest" ? a.avgWinTotal - b.avgWinTotal : b.avgWinTotal - a.avgWinTotal;
      });
  }, [teams, scheduleByTeam, gameweeks, sortDirection]);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex flex-wrap gap-1">
          {WINDOW_OPTIONS.map((w) => (
            <button
              key={w}
              type="button"
              onClick={() => setWindowLength(w)}
              className={`rounded-full px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide ${
                w === windowLength ? "bg-sky-500 text-navy-950" : "bg-navy-900 text-navy-400 hover:bg-navy-800"
              }`}
            >
              {WINDOW_LABELS[w]}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setSortDirection((d) => (d === "easiest" ? "hardest" : "easiest"))}
          className="rounded-md border border-navy-700 px-3 py-1.5 text-xs text-navy-300 hover:border-sky-500/50 hover:text-sky-300"
        >
          Sorted: {sortDirection === "easiest" ? "Easiest run first" : "Hardest run first"} (click to flip)
        </button>
      </div>

      <div className="flex items-center gap-3 text-xs text-navy-400">
        <span>Legend:</span>
        {(["easy", "okay", "tough", "difficult"] as const).map((tier) => (
          <span key={tier} className="flex items-center gap-1">
            <span className="h-3 w-3 rounded-sm" style={{ backgroundColor: DIFFICULTY_COLORS[tier].bg }} />
            {tier === "easy" ? "Easy" : tier === "okay" ? "Okay" : tier === "tough" ? "Tough" : "Difficult"}
          </span>
        ))}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-0 border-collapse text-sm">
          <thead>
            <tr className="border-b border-navy-800 text-left text-xs uppercase tracking-wide text-navy-500">
              <th className="sticky left-0 bg-navy-950 py-2 pr-3 font-medium">Team</th>
              {gameweeks.map((gw) => (
                <th key={gw} className="px-1 py-2 text-center font-medium">
                  GW{gw}
                </th>
              ))}
              <th className="py-2 pl-3 text-center font-medium">Avg</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ team, cells, avgWinTotal }) => (
              <tr key={team.id} className="border-b border-navy-900">
                <td className="sticky left-0 whitespace-nowrap bg-navy-950 py-1.5 pr-3 font-medium text-navy-200">{team.abbr}</td>
                {cells.map((cell, i) => {
                  if (!cell) {
                    return <td key={i} className="px-1 py-1.5 text-center text-navy-700">-</td>;
                  }
                  const tier = difficultyTier(cell.opponentWinTotal, cell.isBye, thresholds);
                  const colors = DIFFICULTY_COLORS[tier];
                  return (
                    <td key={i} className="px-1 py-1.5 text-center">
                      <span
                        className="inline-flex min-w-[2.5rem] items-center justify-center rounded px-1.5 py-0.5 font-mono text-xs font-semibold"
                        style={{ backgroundColor: colors.bg, color: colors.text }}
                        title={cell.isBye ? "Bye week" : `${cell.isHome ? "vs" : "@"} ${cell.opponentAbbr}`}
                      >
                        {cell.isBye ? "BYE" : `${cell.isHome ? "" : "@"}${cell.opponentAbbr}`}
                      </span>
                    </td>
                  );
                })}
                <td className="py-1.5 pl-3 text-center font-mono text-xs text-navy-400">
                  {avgWinTotal !== null ? avgWinTotal.toFixed(1) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
