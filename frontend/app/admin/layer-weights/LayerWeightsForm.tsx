"use client";

import { useMemo, useState } from "react";
import { saveLayerWeights } from "./actions";

export type LayerWeightRow = { id: number; horizon: number; position: string; layer: string; weight: number };

const HORIZONS = [1, 2, 3, 5];
const POSITIONS = ["quarterback", "running_back", "wide_receiver", "tight_end", "defense_special"];
const POSITION_LABELS: Record<string, string> = {
  quarterback: "QB", running_back: "RB", wide_receiver: "WR", tight_end: "TE", defense_special: "D/ST",
};
const LAYER_LABELS: Record<string, string> = {
  form: "Form", fixture_quantity: "Fixture Quantity", fixture_quality: "Fixture Quality", live_odds: "Live Odds",
};

export default function LayerWeightsForm({ rows }: { rows: LayerWeightRow[] }) {
  const [horizon, setHorizon] = useState(1);
  const [position, setPosition] = useState("quarterback");
  const [values, setValues] = useState<Record<number, number>>(() => Object.fromEntries(rows.map((r) => [r.id, r.weight])));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const selected = useMemo(
    () => rows.filter((r) => r.horizon === horizon && r.position === position),
    [rows, horizon, position]
  );

  const sum = selected.reduce((total, r) => total + (values[r.id] ?? 0), 0);
  const sumIsBalanced = Math.abs(sum - 1) < 0.01;
  const dirty = selected.some((r) => values[r.id] !== r.weight);

  async function handleSave() {
    setSaving(true);
    setMessage(null);
    try {
      const changes = selected.map((r) => ({ id: r.id, layer: r.layer, oldWeight: r.weight, newWeight: values[r.id] }));
      const result = await saveLayerWeights(horizon, position, changes);
      setMessage(result.updated > 0 ? `Saved ${result.updated} change(s).` : "No changes to save.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Failed to save.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-1">
        {HORIZONS.map((h) => (
          <button
            key={h}
            type="button"
            onClick={() => setHorizon(h)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-bold uppercase tracking-wide ${
              h === horizon ? "bg-sky-500 text-navy-950" : "bg-navy-900 text-navy-400 hover:bg-navy-800"
            }`}
          >
            GW+{h}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        {POSITIONS.map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => setPosition(p)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-bold uppercase tracking-wide ${
              p === position ? "bg-navy-700 text-navy-100" : "bg-navy-900 text-navy-400 hover:bg-navy-800"
            }`}
          >
            {POSITION_LABELS[p]}
          </button>
        ))}
      </div>

      <div className="flex flex-col divide-y divide-navy-800 rounded-lg border border-navy-800 bg-navy-900 px-4">
        {selected.map((r) => (
          <div key={r.id} className="flex items-center justify-between gap-3 py-2.5">
            <span className="text-sm text-navy-200">{LAYER_LABELS[r.layer] ?? r.layer}</span>
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={values[r.id]}
              onChange={(e) => setValues((v) => ({ ...v, [r.id]: Number(e.target.value) }))}
              className="w-24 rounded-md border border-navy-700 bg-navy-950 px-2 py-1 text-right font-mono text-sm text-navy-100 focus:outline-none focus:ring-2 focus:ring-sky-400/40"
            />
          </div>
        ))}
      </div>

      <p className={`text-sm ${sumIsBalanced ? "text-emerald-400" : "text-amber-400"}`}>
        Effective split sums to {sum.toFixed(2)}{sumIsBalanced ? "" : " — layers with no data yet will renormalize over whatever remains, but this should still total 1.00"}
      </p>

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
