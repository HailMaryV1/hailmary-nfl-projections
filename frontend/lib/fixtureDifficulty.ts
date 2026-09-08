// Real, self-calibrating difficulty tiers - quartile boundaries computed
// fresh from whatever real opponent_win_total values are currently in
// team_schedule_difficulty (Sharp Football Analysis's real Vegas-win-total
// model), not a hardcoded scale. A team in the toughest real quarter of
// the league is "Difficult", easiest quarter is "Easy".
export type DifficultyTier = "difficult" | "tough" | "okay" | "easy" | "bye";

export const DIFFICULTY_LABELS: Record<DifficultyTier, string> = {
  difficult: "Difficult",
  tough: "Tough",
  okay: "Okay",
  easy: "Easy",
  bye: "Bye",
};

// Real hex values (not Tailwind tokens) so these can be used as inline
// backgrounds on small fixture tiles without fighting text contrast.
export const DIFFICULTY_COLORS: Record<DifficultyTier, { bg: string; text: string }> = {
  difficult: { bg: "#7f1d1d", text: "#fecaca" },
  tough: { bg: "#7c2d12", text: "#fed7aa" },
  okay: { bg: "#713f12", text: "#fef08a" },
  easy: { bg: "#1e3a5f", text: "#bfdbfe" },
  bye: { bg: "#1e293b", text: "#64748b" },
};

export type DifficultyThresholds = { p25: number; p50: number; p75: number };

export function computeDifficultyThresholds(winTotals: number[]): DifficultyThresholds {
  const sorted = [...winTotals].sort((a, b) => a - b);
  const pct = (p: number) => sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(p * sorted.length)))];
  return { p25: pct(0.25), p50: pct(0.5), p75: pct(0.75) };
}

export function difficultyTier(winTotal: number | null, isBye: boolean, thresholds: DifficultyThresholds): DifficultyTier {
  if (isBye) return "bye";
  if (winTotal === null) return "okay"; // real gap in the source data (see docs) - a neutral tier, never guessed harder/easier
  if (winTotal >= thresholds.p75) return "difficult";
  if (winTotal >= thresholds.p50) return "tough";
  if (winTotal >= thresholds.p25) return "okay";
  return "easy";
}
