"use client";

import { useState } from "react";
import { saveScoringRules } from "./actions";

export type ScoringRule = { id: number; applies_to: string; stat: string; points: number; notes: string | null };

export default function ScoringRulesForm({ rules }: { rules: ScoringRule[] }) {
  const [values, setValues] = useState<Record<number, number>>(() => Object.fromEntries(rules.map((r) => [r.id, r.points])));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const dirty = rules.some((r) => values[r.id] !== r.points);

  async function handleSave() {
    setSaving(true);
    setMessage(null);
    try {
      const changes = rules.map((r) => ({ id: r.id, applies_to: r.applies_to, stat: r.stat, oldPoints: r.points, newPoints: values[r.id] }));
      const result = await saveScoringRules(changes);
      setMessage(result.updated > 0 ? `Saved ${result.updated} change(s).` : "No changes to save.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  const groups = ["offense", "defense_special"];

  return (
    <div className="flex flex-col gap-6">
      {groups.map((group) => (
        <div key={group}>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-navy-400">{group === "offense" ? "Offense" : "Defense / Special Teams"}</h2>
          <div className="mt-2 flex flex-col divide-y divide-navy-800">
            {rules
              .filter((r) => r.applies_to === group)
              .map((r) => (
                <div key={r.id} className="flex items-center justify-between gap-3 py-2">
                  <div>
                    <div className="text-sm text-navy-200">{r.stat.replace(/_/g, " ")}</div>
                    {r.notes && <div className="text-xs text-navy-500">{r.notes}</div>}
                  </div>
                  <input
                    type="number"
                    step="0.01"
                    value={values[r.id]}
                    onChange={(e) => setValues((v) => ({ ...v, [r.id]: Number(e.target.value) }))}
                    className="w-24 rounded-md border border-navy-700 bg-navy-950 px-2 py-1 text-right font-mono text-sm text-navy-100 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
                  />
                </div>
              ))}
          </div>
        </div>
      ))}

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || saving}
          className="rounded-md bg-sky-500 px-4 py-2 text-sm font-semibold text-navy-950 hover:bg-sky-400 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
        {message && <span className="text-sm text-navy-400">{message}</span>}
      </div>
    </div>
  );
}
