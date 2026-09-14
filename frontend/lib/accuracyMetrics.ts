// Real, pure statistics helpers for the Accuracy page - kept separate from
// data-fetching/rendering so the actual arithmetic behind every number on
// that page can be read in one place. Nothing here touches
// predictions_and_actuals directly - every function takes already-fetched
// real rows and returns a derived number.
//
// Ported verbatim from the sibling EFL-Projections repo's own
// lib/accuracyMetrics.ts (itself ported from dreamteam-projections). This
// project's predictions_and_actuals (migration 0009) is the same simple
// shape EFL's is - no minutes-band/fixture-load segmentation or baseline
// comparison here either, for the same reason: no real per-match minutes
// field on player_stats to build them from honestly.

export type PointsPair = { predicted: number; actual: number };

export function mae(items: PointsPair[]): number | null {
  if (items.length === 0) return null;
  return items.reduce((sum, i) => sum + Math.abs(i.actual - i.predicted), 0) / items.length;
}

export function medianAbsoluteError(items: PointsPair[]): number | null {
  if (items.length === 0) return null;
  const sorted = items.map((i) => Math.abs(i.actual - i.predicted)).sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

export function rmse(items: PointsPair[]): number | null {
  if (items.length === 0) return null;
  const meanSquare = items.reduce((sum, i) => sum + (i.actual - i.predicted) ** 2, 0) / items.length;
  return Math.sqrt(meanSquare);
}

// predicted - actual, so positive = the model over-projects on average,
// negative = it under-projects. Same convention as the sibling projects'
// own accuracyMetrics.ts, kept identical so a number carried over between
// products' docs/conversations means the same thing.
export function bias(items: PointsPair[]): number | null {
  if (items.length === 0) return null;
  return items.reduce((sum, i) => sum + (i.predicted - i.actual), 0) / items.length;
}

export type ErrorBuckets = { within1: number; within2: number; within3: number; within5: number; beyond5: number; n: number };

export function errorBuckets(items: PointsPair[]): ErrorBuckets | null {
  if (items.length === 0) return null;
  const errors = items.map((i) => Math.abs(i.actual - i.predicted));
  const pct = (count: number) => (count / errors.length) * 100;
  return {
    within1: pct(errors.filter((e) => e <= 1).length),
    within2: pct(errors.filter((e) => e <= 2).length),
    within3: pct(errors.filter((e) => e <= 3).length),
    within5: pct(errors.filter((e) => e <= 5).length),
    beyond5: pct(errors.filter((e) => e > 5).length),
    n: errors.length,
  };
}

export type Segment = { label: string; n: number; mae: number | null; bias: number | null };

export function buildSegment(label: string, items: PointsPair[]): Segment {
  return { label, n: items.length, mae: mae(items), bias: bias(items) };
}

// Below this, a segment's own MAE/bias is still shown (never hidden - same
// "don't hide the data, give context" instruction the sibling projects'
// own Accuracy page was built under) but flagged as a small sample rather
// than presented with the same confidence as a well-sampled segment.
export const SMALL_SAMPLE_THRESHOLD = 30;
