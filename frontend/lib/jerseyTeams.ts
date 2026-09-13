// The 32 real teams with real jersey art in public/jerseys/{ABBR}.png -
// see scripts/slice_jerseys.py. Kept as an explicit set (not "just try the
// image") so a stray/placeholder value like "—" falls back to TeamBadge's
// generated-color chip instead of requesting a jersey that doesn't exist.
export const JERSEY_TEAMS = new Set([
  "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
  "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
  "LV", "LAC", "LAR", "MIA", "MIN", "NE", "NO", "NYG",
  "NYJ", "PHI", "PIT", "SF", "SEA", "TB", "TEN", "WAS",
]);
