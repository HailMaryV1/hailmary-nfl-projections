"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { loadReplacementCandidates, applySwap, revertSwap } from "./custom/actions";
import type { SlotKey } from "@/lib/playbookEngine";
import type { ReplacementCandidate } from "@/lib/injurySwap";

type OtherSlotInfo = { name: string; team: string };

export default function SwapPanel({
  poolId,
  gameweek,
  slot,
  outgoingName,
  outgoingPrice,
  weekCost,
  otherSlots,
  isOverridden,
  onClose,
}: {
  poolId: number;
  gameweek: number;
  slot: SlotKey;
  outgoingName: string;
  outgoingPrice: number;
  weekCost: number;
  otherSlots: OtherSlotInfo[];
  isOverridden: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [candidates, setCandidates] = useState<ReplacementCandidate[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    startTransition(async () => {
      const result = await loadReplacementCandidates(poolId, gameweek, slot, outgoingName, outgoingPrice, weekCost, otherSlots);
      if ("error" in result) setError(result.error);
      else setCandidates(result.candidates);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [poolId, gameweek, slot, outgoingName]);

  function pick(playerId: number) {
    setError(null);
    startTransition(async () => {
      const result = await applySwap(poolId, gameweek, slot, playerId, outgoingName, outgoingPrice, weekCost, otherSlots);
      if ("error" in result) setError(result.error);
      else {
        router.refresh();
        onClose();
      }
    });
  }

  function revert() {
    setError(null);
    startTransition(async () => {
      const result = await revertSwap(poolId, gameweek, slot);
      if ("error" in result) setError(result.error);
      else {
        router.refresh();
        onClose();
      }
    });
  }

  return (
    <div className="mt-2 rounded-lg border border-navy-700 bg-navy-950/70 p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-navy-200">Legal replacements from your pool, GW{gameweek}</p>
        <button type="button" onClick={onClose} className="text-xs text-navy-500 hover:text-navy-300">
          Close
        </button>
      </div>

      {error && <p className="mt-2 text-xs text-rose-400">{error}</p>}

      {pending && !candidates && !error ? (
        <p className="mt-2 text-xs text-navy-500">Checking your pool for legal replacements…</p>
      ) : candidates && candidates.length === 0 ? (
        <p className="mt-2 text-xs text-navy-500">No eligible replacement in your pool — same slot, real budget and 2-per-team room all considered.</p>
      ) : (
        <ul className="mt-2 flex flex-col gap-1.5">
          {candidates?.map((c) => (
            <li key={c.playerId} className="flex items-center justify-between gap-2 rounded-md bg-navy-900 px-2.5 py-1.5">
              <div className="min-w-0">
                <p className="truncate text-xs font-semibold text-navy-100">{c.name}</p>
                <p className="text-[10px] text-navy-500">
                  {c.team} · £{c.price.toFixed(1)}m
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <span className="font-mono text-xs font-bold text-sky-300">{c.points.toFixed(1)}p</span>
                <button
                  type="button"
                  disabled={pending}
                  onClick={() => pick(c.playerId)}
                  className="rounded-full bg-emerald-500/15 px-2.5 py-1 text-[11px] font-bold text-emerald-300 hover:bg-emerald-500/25 disabled:opacity-50"
                >
                  Switch in
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {isOverridden && (
        <button type="button" disabled={pending} onClick={revert} className="mt-3 text-xs font-semibold text-rose-400 hover:underline disabled:opacity-50">
          Revert to original pick
        </button>
      )}
    </div>
  );
}
