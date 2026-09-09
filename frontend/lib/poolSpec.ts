import type { Position, Tier } from "./playbookEngine";

export type TierSpec = { tier: Tier; label: string; min: number; max: number; count: number };

/**
 * Real, fixed price-bracket structure for a custom pool: exactly these
 * counts from exactly these real £ brackets, for every position. Not
 * cosmetic - the worst-case floor (every mandatory cheap-tier pick used
 * at once across all 9 real weekly slots) comes to roughly £70m against
 * the real £140M cap, so a legal squad always exists regardless of how
 * the premium tier is spent. Re-derive the real floor from current
 * horizon-1 prices any time these numbers are revisited.
 */
export const POOL_SPEC: Record<Position, { label: string; tiers: TierSpec[] }> = {
  quarterback: {
    label: "QB",
    tiers: [
      { tier: "premium", label: "Premium (£17m+)", min: 17, max: Infinity, count: 2 },
      { tier: "value", label: "Under £17m", min: 0, max: 17, count: 2 },
    ],
  },
  running_back: {
    label: "RB",
    tiers: [
      { tier: "premium", label: "Premium (£17m+)", min: 17, max: Infinity, count: 4 },
      { tier: "mid", label: "Mid (£10m–£16.9m)", min: 10, max: 17, count: 2 },
      { tier: "value", label: "Value (under £10m)", min: 0, max: 10, count: 2 },
    ],
  },
  wide_receiver: {
    label: "WR",
    tiers: [
      { tier: "premium", label: "Premium (£17m+)", min: 17, max: Infinity, count: 4 },
      { tier: "mid", label: "Mid (£10m–£16.9m)", min: 10, max: 17, count: 2 },
      { tier: "value", label: "Value (under £10m)", min: 0, max: 10, count: 2 },
    ],
  },
  tight_end: {
    label: "TE",
    tiers: [
      { tier: "premium", label: "Premium (£15m+)", min: 15, max: Infinity, count: 1 },
      { tier: "mid", label: "Mid (£10m–£14.9m)", min: 10, max: 15, count: 2 },
      { tier: "value", label: "Value (under £10m)", min: 0, max: 10, count: 1 },
    ],
  },
  defense_special: {
    label: "DST",
    tiers: [{ tier: "any", label: "Any", min: 0, max: Infinity, count: 4 }],
  },
};

export const POOL_TOTAL = Object.values(POOL_SPEC).reduce(
  (sum, pos) => sum + pos.tiers.reduce((s, t) => s + t.count, 0),
  0
);

export function tierForPrice(position: Position, price: number): Tier {
  const spec = POOL_SPEC[position];
  const match = spec.tiers.find((t) => price >= t.min && price < t.max) ?? spec.tiers[spec.tiers.length - 1];
  return match.tier;
}
