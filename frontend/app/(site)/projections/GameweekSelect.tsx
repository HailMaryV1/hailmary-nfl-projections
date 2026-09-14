"use client";

import { useRouter } from "next/navigation";

export default function GameweekSelect({
  gameweeks,
  selected,
  defaultGameweek,
  horizon,
}: {
  gameweeks: number[];
  selected: number;
  defaultGameweek: number | null;
  horizon: number;
}) {
  const router = useRouter();

  return (
    <label className="flex items-center gap-2 text-sm text-navy-300">
      <span className="font-[family-name:var(--font-cond)] font-bold uppercase tracking-wide text-navy-500">Gameweek</span>
      <select
        value={selected}
        onChange={(e) => {
          const gw = Number(e.target.value);
          const params = new URLSearchParams();
          if (horizon !== 1) params.set("horizon", String(horizon));
          if (gw !== defaultGameweek) params.set("gameweek", String(gw));
          const qs = params.toString();
          router.push(qs ? `/projections?${qs}` : "/projections");
        }}
        className="rounded-lg border border-navy-700 bg-navy-900 px-2.5 py-1.5 text-navy-100"
      >
        {gameweeks.map((gw) => (
          <option key={gw} value={gw}>
            GW{gw}
            {gw === defaultGameweek ? " (current)" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
