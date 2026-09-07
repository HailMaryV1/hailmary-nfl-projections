export const POSITION_LABELS: Record<string, string> = {
  quarterback: "QB",
  running_back: "RB",
  wide_receiver: "WR",
  tight_end: "TE",
  defense_special: "D/ST",
};

export const POSITION_COLOR_VAR: Record<string, string> = {
  quarterback: "--color-pos-qb",
  running_back: "--color-pos-rb",
  wide_receiver: "--color-pos-wr",
  tight_end: "--color-pos-te",
  defense_special: "--color-pos-dst",
};

export const POSITION_ORDER = ["quarterback", "running_back", "wide_receiver", "tight_end", "defense_special"];

export function positionLabel(position: string): string {
  return POSITION_LABELS[position] ?? position;
}
