"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import type { Position, Tier } from "@/lib/playbookEngine";
import type { POOL_SPEC as PoolSpecType } from "@/lib/poolSpec";
import { POSITION_ORDER, positionLabel, POSITION_COLOR_VAR } from "@/lib/positions";
import { buildPool } from "./actions";

export type PlayerOption = { id: number; name: string; position: Position; price: number; team: string; points: number; tier: Tier };

export default function PoolPicker({
  options, spec, existingSelection, signedIn,
}: { options: PlayerOption[]; spec: typeof PoolSpecType; existingSelection: number[]; signedIn: boolean }) {
  const router = useRouter();
  const [selected, setSelected] = useState<Set<number>>(new Set(existingSelection));
  const [pending, startTransition] = useTransition();
  const [buildError, setBuildError] = useState<string | null>(null);

  const byId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options]);

  const grouped = useMemo(() => {
    const out: Record<Position, Record<string, PlayerOption[]>> = {} as Record<Position, Record<string, PlayerOption[]>>;
    for (const pos of POSITION_ORDER as Position[]) out[pos] = {};
    for (const opt of options) {
      out[opt.position][opt.tier] = out[opt.position][opt.tier] ?? [];
      out[opt.position][opt.tier].push(opt);
    }
    for (const pos of Object.keys(out) as Position[]) {
      for (const tier of Object.keys(out[pos])) out[pos][tier].sort((a, b) => b.price - a.price);
    }
    return out;
  }, [options]);

  const countInTier = (position: Position, tier: Tier) =>
    (grouped[position]?.[tier] ?? []).filter((o) => selected.has(o.id)).length;

  function toggle(opt: PlayerOption, tierCount: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(opt.id)) {
        next.delete(opt.id);
      } else {
        if (countInTier(opt.position, opt.tier) >= tierCount) return prev; // tier full
        next.add(opt.id);
      }
      return next;
    });
  }

  const total = selected.size;
  const totalNeeded = Object.values(spec).reduce((s, p) => s + p.tiers.reduce((a, t) => a + t.count, 0), 0);
  const allTiersComplete = (Object.keys(spec) as Position[]).every((pos) =>
    spec[pos].tiers.every((t) => countInTier(pos, t.tier) === t.count)
  );

  function handleBuild() {
    setBuildError(null);
    const selections = [...selected].map((id) => {
      const o = byId.get(id)!;
      return { playerId: o.id, position: o.position, tier: o.tier };
    });
    startTransition(async () => {
      const result = await buildPool(selections);
      if ("error" in result) {
        setBuildError(result.error);
      } else {
        router.push("/playbook/custom");
      }
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="sticky top-[52px] z-20 flex flex-wrap items-center gap-3 rounded-xl border border-navy-800 bg-navy-900/95 p-4 backdrop-blur-sm">
        <div className="font-mono text-lg font-semibold tabular-nums text-navy-100">
          {total} / {totalNeeded} <span className="text-sm font-normal text-navy-500">selected</span>
        </div>
        <div className="flex flex-1 flex-wrap gap-2">
          {(POSITION_ORDER as Position[]).map((pos) => {
            const need = spec[pos].tiers.reduce((s, t) => s + t.count, 0);
            const have = spec[pos].tiers.reduce((s, t) => s + countInTier(pos, t.tier), 0);
            return (
              <span
                key={pos}
                className={`rounded-full px-2.5 py-1 font-mono text-xs font-semibold ${have === need ? "bg-emerald-500/15 text-emerald-300" : "bg-navy-800 text-navy-400"}`}
              >
                {positionLabel(pos)} {have}/{need}
              </span>
            );
          })}
        </div>
        <button
          onClick={handleBuild}
          disabled={!allTiersComplete || pending}
          className="rounded-full bg-emerald-500 px-5 py-2 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide text-navy-950 disabled:cursor-not-allowed disabled:bg-navy-800 disabled:text-navy-500"
        >
          {pending ? "Building…" : "Save & Build Playbook"}
        </button>
      </div>
      {buildError && <p className="rounded-lg bg-rose-950/40 p-3 text-sm text-rose-300 ring-1 ring-rose-800">{buildError}</p>}

      {(POSITION_ORDER as Position[]).map((pos) => (
        <section key={pos}>
          <h2
            className="mb-3 font-[family-name:var(--font-cond)] text-2xl font-extrabold"
            style={{ color: `var(${POSITION_COLOR_VAR[pos]})` }}
          >
            {positionLabel(pos)}
          </h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {spec[pos].tiers.map((t) => (
              <div key={t.tier} className="rounded-xl border border-navy-800 bg-navy-900 p-3.5">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-navy-200">{t.label}</h3>
                  <span
                    className={`font-mono text-xs font-semibold ${countInTier(pos, t.tier) === t.count ? "text-emerald-400" : "text-navy-500"}`}
                  >
                    {countInTier(pos, t.tier)}/{t.count}
                  </span>
                </div>
                <ul className="flex max-h-72 flex-col gap-1 overflow-y-auto pr-1">
                  {(grouped[pos]?.[t.tier] ?? []).map((opt) => {
                    const checked = selected.has(opt.id);
                    const tierFull = countInTier(pos, t.tier) >= t.count;
                    return (
                      <li key={opt.id}>
                        <label
                          className={`flex items-center gap-2 rounded-md px-2 py-1.5 text-sm ${
                            checked ? "bg-emerald-500/10" : tierFull ? "cursor-not-allowed opacity-40" : "hover:bg-navy-800"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            disabled={!checked && tierFull}
                            onChange={() => toggle(opt, t.count)}
                            className="h-4 w-4 accent-emerald-500"
                          />
                          <span className="min-w-0 flex-1 truncate text-navy-100">{opt.name}</span>
                          <span className="shrink-0 text-xs text-navy-500">{opt.team}</span>
                          <span className="shrink-0 font-mono text-xs tabular-nums text-navy-300">£{opt.price.toFixed(1)}m</span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
