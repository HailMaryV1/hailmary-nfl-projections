"use client";

import { useMemo, useState } from "react";

type SlotInfo = { name: string; team: string; price: number; pts: number | null };
type Move = { slot: string; old: string; new: string; reason: string; pts: number };
type WeekRecord = {
  gw: number;
  is_wildcard: boolean;
  roster: Record<string, SlotInfo>;
  dst: SlotInfo;
  moves: Move[];
  transfers_used: number;
  transfers_available: number | null;
  extra_paid: number;
  banked_after: number;
  cost: number;
  team_counts: Record<string, number>;
  week_points: number;
  running_total: number;
};
export type PlanData = { total_points: number; extra_transfer_weeks: number[]; weeks: WeekRecord[] };

const SLOT_ORDER = ["QB", "RB1", "RB2", "WR1", "WR2", "WR3", "TE", "FLEX"] as const;
// DST isn't in SLOT_ORDER (it's rendered from week.dst in its own board row/
// card, same as the two fixed-DST playbooks), but a custom pool's DST is a
// real rotating slot, so its moves can appear in the move log - these two
// entries just make that render with a real label/colour instead of a bare
// "DST" fallback.
const SLOT_LABEL: Record<string, string> = { QB: "QB", RB1: "RB", RB2: "RB", WR1: "WR", WR2: "WR", WR3: "WR", TE: "TE", FLEX: "FLEX", DST: "DST" };
const SLOT_ACCENT: Record<string, string> = {
  QB: "var(--color-pos-qb)", RB1: "var(--color-pos-rb)", RB2: "var(--color-pos-rb)",
  WR1: "var(--color-pos-wr)", WR2: "var(--color-pos-wr)", WR3: "var(--color-pos-wr)",
  TE: "var(--color-pos-te)", FLEX: "var(--color-pos-dst)", DST: "var(--color-pos-dst)",
};
const BUDGET_CAP = 140.0;

function lastName(full: string) {
  const parts = full.split(" ");
  return parts.length > 1 ? parts.slice(-1)[0] : full;
}
function fmt1(n: number | null | undefined) {
  return n === null || n === undefined ? "-" : n.toFixed(1);
}

function useTeamColors(plan: PlanData) {
  return useMemo(() => {
    const teams = new Set<string>();
    plan.weeks.forEach((w) => {
      SLOT_ORDER.forEach((s) => teams.add(w.roster[s].team));
      teams.add(w.dst.team);
    });
    const list = [...teams].sort();
    const map: Record<string, string> = {};
    list.forEach((t, i) => {
      map[t] = `hsl(${Math.round((360 / list.length) * i)}, 62%, 58%)`;
    });
    return map;
  }, [plan]);
}

export default function PlaybookBoard({ plan, storageKey, accentClass }: { plan: PlanData; storageKey: string; accentClass: string }) {
  const [selectedGw, setSelectedGw] = useState(plan.weeks[0].gw);
  const teamColor = useTeamColors(plan);
  const week = plan.weeks.find((w) => w.gw === selectedGw)!;
  const wildcardWeek = plan.weeks.find((w) => w.is_wildcard);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap gap-2.5">
        <StatTile label="Total pts" value={fmt1(plan.total_points)} />
        <StatTile label="Wildcard GW" value={wildcardWeek ? `GW${wildcardWeek.gw}` : "unused"} />
        <StatTile label="Paid transfers" value={plan.extra_transfer_weeks.length ? plan.extra_transfer_weeks.map((g) => `GW${g}`).join(", ") : "none"} />
        <StatTile label="Budget cap" value="£140M" />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-navy-400">
        <LegendDot color="var(--color-pos-qb)" label="outlined card = new to that slot this week" outline />
        <LegendDot color="#a78bfa" label="wildcard week — unlimited free transfers" />
        <span>italic/faded = real bye that week</span>
        <span className="text-navy-500">click any GW column for that week&apos;s reasoning</span>
      </div>

      <div className="overflow-x-auto rounded-xl border border-navy-800 bg-navy-900">
        <table className="w-full min-w-[1100px] border-collapse text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 border-b border-r border-navy-800 bg-navy-900 px-3 py-2 text-left font-[family-name:var(--font-cond)] text-sm font-bold text-navy-400">
                Slot
              </th>
              {plan.weeks.map((w) => (
                <th
                  key={w.gw}
                  onClick={() => setSelectedGw(w.gw)}
                  className={`min-w-[62px] cursor-pointer border-b border-navy-800 px-1 py-2 text-center font-mono text-xs font-semibold ${
                    w.is_wildcard ? "bg-[#a78bfa]/15 text-[#c4b5fd]" : w.gw === selectedGw ? "bg-sky-500/15 text-sky-300" : "text-navy-400 hover:text-navy-200"
                  }`}
                >
                  GW{w.gw}
                  {w.extra_paid > 0 && <span className="mt-0.5 block text-[10px] text-rose-400">-8</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SLOT_ORDER.map((slot) => (
              <tr key={slot}>
                <td className="sticky left-0 z-10 whitespace-nowrap border-b border-r border-navy-800 bg-navy-900 px-3 py-2 font-[family-name:var(--font-cond)] text-sm font-bold text-navy-400">
                  {SLOT_LABEL[slot]}
                </td>
                {plan.weeks.map((w, i) => {
                  const info = w.roster[slot];
                  const prev = i > 0 ? plan.weeks[i - 1].roster[slot].name : null;
                  const isNew = prev !== null && prev !== info.name;
                  const isBye = info.pts === 0;
                  const tint = teamColor[info.team] ?? "#888";
                  return (
                    <td key={w.gw} className={`border-b border-navy-800 p-[3px] align-top ${w.gw === selectedGw ? "bg-sky-500/10" : ""}`}>
                      <div
                        className={`min-h-[46px] rounded-md border px-1.5 py-1 ${isNew ? "border-sky-400" : "border-transparent"} ${isBye ? "italic opacity-55" : ""}`}
                        style={{ background: `${tint}22` }}
                      >
                        <div className="truncate text-[11px] font-semibold" style={{ color: tint }}>
                          {info.team}
                        </div>
                        <div className="truncate text-[11px] font-semibold text-navy-100">{lastName(info.name)}</div>
                        <div className="mt-0.5 font-mono text-[10px] text-navy-400">
                          {isBye ? "BYE" : `£${info.price.toFixed(1)}m · ${fmt1(info.pts)}p`}
                        </div>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <td className="sticky left-0 z-10 whitespace-nowrap border-t-2 border-navy-700 bg-navy-900 px-3 py-2 font-[family-name:var(--font-cond)] text-sm font-bold text-navy-400">
                DST
              </td>
              {plan.weeks.map((w) => {
                const info = w.dst;
                const isBye = info.pts === 0;
                const tint = teamColor[info.team] ?? "#888";
                return (
                  <td key={w.gw} className={`border-t-2 border-navy-700 p-[3px] align-top ${w.gw === selectedGw ? "bg-sky-500/10" : ""}`}>
                    <div className={`min-h-[46px] rounded-md border border-transparent px-1.5 py-1 ${isBye ? "italic opacity-55" : ""}`} style={{ background: `${tint}22` }}>
                      <div className="truncate text-[11px] font-semibold" style={{ color: tint }}>
                        {info.team}
                      </div>
                      <div className="truncate text-[11px] font-semibold text-navy-100">D/ST</div>
                      <div className="mt-0.5 font-mono text-[10px] text-navy-400">
                        {isBye ? "BYE (fixed all season)" : `£${info.price.toFixed(1)}m · ${fmt1(info.pts)}p`}
                      </div>
                    </div>
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>

      <DetailPanel week={week} storageKey={storageKey} accentClass={accentClass} teamColor={teamColor} />
    </div>
  );
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-[108px] rounded-lg border border-navy-800 bg-navy-900 px-3.5 py-2">
      <div className="font-mono text-xl font-semibold tabular-nums text-navy-100">{value}</div>
      <div className="mt-0.5 text-[11px] uppercase tracking-wide text-navy-500">{label}</div>
    </div>
  );
}

function LegendDot({ color, label, outline }: { color: string; label: string; outline?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="inline-block h-2.5 w-2.5 rounded-sm" style={outline ? { border: `2px solid ${color}` } : { background: color }} />
      {label}
    </span>
  );
}

function DetailPanel({
  week, storageKey, accentClass, teamColor,
}: { week: WeekRecord; storageKey: string; accentClass: string; teamColor: Record<string, string> }) {
  const [done, setDone] = useState(() => {
    try {
      return localStorage.getItem(`${storageKey}_done_${week.gw}`) === "1";
    } catch {
      return false;
    }
  });

  const teamCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    SLOT_ORDER.forEach((s) => {
      const t = week.roster[s].team;
      counts[t] = (counts[t] || 0) + 1;
    });
    counts[week.dst.team] = (counts[week.dst.team] || 0) + 1;
    return Object.entries(counts).sort((a, b) => b[1] - a[1]);
  }, [week]);

  return (
    <div className="rounded-xl border border-navy-800 bg-navy-900 p-5 sm:p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h2 className="font-[family-name:var(--font-cond)] text-2xl font-extrabold text-navy-100">Gameweek {week.gw}</h2>
        {week.is_wildcard ? (
          <span className="rounded-full bg-[#a78bfa]/15 px-2.5 py-1 font-[family-name:var(--font-cond)] text-xs font-bold uppercase tracking-wide text-[#c4b5fd]">
            Wildcard week
          </span>
        ) : week.moves.length ? (
          <span className="rounded-full bg-emerald-500/15 px-2.5 py-1 font-[family-name:var(--font-cond)] text-xs font-bold uppercase tracking-wide text-emerald-300">
            {week.moves.length} move{week.moves.length > 1 ? "s" : ""}
          </span>
        ) : (
          <span className="rounded-full bg-navy-800 px-2.5 py-1 font-[family-name:var(--font-cond)] text-xs font-bold uppercase tracking-wide text-navy-400">
            No changes
          </span>
        )}
        <label className="flex items-center gap-1.5 text-xs text-navy-400">
          <input
            type="checkbox"
            checked={done}
            onChange={(e) => {
              setDone(e.target.checked);
              try {
                localStorage.setItem(`${storageKey}_done_${week.gw}`, e.target.checked ? "1" : "0");
              } catch {}
            }}
            className="h-4 w-4 accent-emerald-500"
          />
          Mark this week done
        </label>
      </div>

      <div className="mt-3.5 flex flex-wrap gap-x-5 gap-y-1.5 rounded-lg bg-navy-950/50 p-3.5 text-xs text-navy-400">
        <Metric label="Transfers used">
          {week.transfers_used}
          {week.transfers_available !== null ? ` / ${week.transfers_available} available` : week.is_wildcard ? " (unlimited)" : ""}
        </Metric>
        <Metric label="Extra paid" warn={week.extra_paid > 0}>
          {week.extra_paid ? `-${week.extra_paid * 8}pts` : "none"}
        </Metric>
        <Metric label="Banked after">{week.banked_after}</Metric>
        <Metric label="Squad cost">£{week.cost.toFixed(1)}m / £{BUDGET_CAP.toFixed(1)}m</Metric>
        <Metric label="Week points">{fmt1(week.week_points)}</Metric>
        <Metric label="Running total">{fmt1(week.running_total)}</Metric>
      </div>

      <SectionLabel>Teams to target this week</SectionLabel>
      <div className="flex flex-wrap gap-2">
        {teamCounts.map(([team, ct]) => (
          <span key={team} className="flex items-center gap-1.5 rounded-full border border-navy-700 px-3 py-1.5 font-mono text-xs font-semibold text-navy-200">
            <span className="h-2 w-2 rounded-full" style={{ background: teamColor[team] }} />
            {team} <span className="text-navy-500">×{ct}</span>
          </span>
        ))}
      </div>

      <SectionLabel>What changed and why</SectionLabel>
      {week.moves.length ? (
        <div className="flex flex-col gap-1.5">
          {week.moves.map((m, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2.5 rounded-lg bg-navy-950/50 px-3 py-2 text-[13px]">
              <span className="rounded border border-navy-700 bg-navy-900 px-1.5 py-0.5 font-mono text-[10.5px] text-navy-400">{SLOT_LABEL[m.slot] || m.slot}</span>
              <span className="text-navy-200">
                {lastName(m.old)} <span className="text-navy-500">&rarr;</span> <b className="text-navy-100">{lastName(m.new)}</b>
              </span>
              <span className="ml-auto text-xs text-navy-500">{m.reason}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="py-1.5 text-[13px] italic text-navy-500">Hold the squad as-is this week — no swap cleared the real point-gain bar.</p>
      )}

      <SectionLabel>Full roster this week</SectionLabel>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
        {SLOT_ORDER.map((slot) => {
          const info = week.roster[slot];
          const changed = week.moves.some((m) => m.slot === slot);
          return (
            <div key={slot} className={`rounded-lg border bg-navy-950/50 p-2.5 ${changed ? `border-current ${accentClass}` : "border-navy-800"}`}>
              <div className="font-[family-name:var(--font-cond)] text-[11px] font-bold uppercase tracking-wide" style={{ color: SLOT_ACCENT[slot] }}>
                {SLOT_LABEL[slot]}
              </div>
              <div className="mt-0.5 truncate text-sm font-semibold text-navy-100">{info.name}</div>
              <div className="text-[11.5px] text-navy-400">{info.team}</div>
              <div className="mt-1.5 flex justify-between font-mono text-xs text-navy-400">
                <span>£{info.price.toFixed(1)}m</span>
                <b className="text-navy-100">{info.pts === 0 ? "BYE" : `${fmt1(info.pts)}p`}</b>
              </div>
            </div>
          );
        })}
        <div className="rounded-lg border border-navy-800 bg-navy-950/50 p-2.5">
          <div className="font-[family-name:var(--font-cond)] text-[11px] font-bold uppercase tracking-wide text-navy-500">DST</div>
          <div className="mt-0.5 truncate text-sm font-semibold text-navy-100">{week.dst.name}</div>
          <div className="text-[11.5px] text-navy-400">{week.dst.team}</div>
          <div className="mt-1.5 flex justify-between font-mono text-xs text-navy-400">
            <span>£{week.dst.price.toFixed(1)}m</span>
            <b className="text-navy-100">{week.dst.pts === 0 ? "BYE" : `${fmt1(week.dst.pts)}p`}</b>
          </div>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, children, warn }: { label: string; children: React.ReactNode; warn?: boolean }) {
  return (
    <div>
      {label} <b className={`font-mono font-semibold ${warn ? "text-rose-400" : "text-navy-100"}`}>{children}</b>
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <h3 className="mb-2 mt-5 font-[family-name:var(--font-cond)] text-[13px] font-bold uppercase tracking-wide text-navy-500">{children}</h3>;
}
