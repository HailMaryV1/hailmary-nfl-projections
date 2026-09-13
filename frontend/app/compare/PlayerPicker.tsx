"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { positionLabel } from "@/lib/positions";

export type PlayerOption = { id: number; name: string; position: string; team: string };

function Picker({ options, selectedId, otherId, label, param }: { options: PlayerOption[]; selectedId: number | null; otherId: number | null; label: string; param: "a" | "b" }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const selected = options.find((o) => o.id === selectedId) ?? null;

  const matches = useMemo(() => {
    if (!query.trim()) return [];
    const q = query.trim().toLowerCase();
    return options.filter((o) => o.id !== otherId && o.name.toLowerCase().includes(q)).slice(0, 8);
  }, [options, query, otherId]);

  function select(id: number) {
    const url = new URL(window.location.href);
    url.searchParams.set(param, String(id));
    router.push(`${url.pathname}?${url.searchParams.toString()}`);
    setQuery("");
  }

  return (
    <div className="min-w-0 flex-1">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-navy-400">{label}</p>
      {selected ? (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-navy-800 bg-navy-900 px-3 py-2">
          <span className="truncate font-[family-name:var(--font-cond)] font-bold uppercase text-navy-100">{selected.name}</span>
          <button type="button" onClick={() => setQuery(" ")} className="shrink-0 text-xs text-sky-400 hover:underline">
            Change
          </button>
        </div>
      ) : null}
      {(!selected || query) && (
        <div className="relative">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search a player…"
            autoFocus={!selected}
            className="w-full rounded-md border border-navy-700 bg-navy-950 px-3 py-2 text-sm text-navy-100 placeholder:text-navy-500 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
          />
          {matches.length > 0 && (
            <div className="absolute z-10 mt-1 w-full rounded-md border border-navy-700 bg-navy-950 shadow-xl">
              {matches.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => select(m.id)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-navy-200 hover:bg-navy-900"
                >
                  <span className="truncate">{m.name}</span>
                  <span className="shrink-0 text-xs text-navy-500">
                    {positionLabel(m.position)} · {m.team}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PlayerPicker({ options, selectedA, selectedB }: { options: PlayerOption[]; selectedA: number | null; selectedB: number | null }) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row">
      <Picker options={options} selectedId={selectedA} otherId={selectedB} label="Player A" param="a" />
      <Picker options={options} selectedId={selectedB} otherId={selectedA} label="Player B" param="b" />
    </div>
  );
}
