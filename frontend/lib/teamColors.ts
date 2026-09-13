// Real, honestly-documented per-team display color - hashed from the
// team's own abbreviation so the same team always gets the same color
// wherever it's shown. This is NOT a real official team brand color -
// this project's `teams` table has no color/logo data at all (confirmed
// via supabase/migrations/0001_teams_and_players.sql). PlaybookBoard.tsx
// already solved this exact problem once, with a real-but-list-relative
// hue rotation (`useTeamColors()`, `hsl(360/n * i, 62%, 58%)`) scoped to
// whatever teams appear in one week's roster. This is the same idea made
// globally stable (hashed, not position-in-a-list-based) so a single team
// shown in isolation - a homepage hero card, with no other teams around
// it to rotate against - still always resolves to the same color.
export function teamColorHue(abbr: string): number {
  let hash = 0;
  for (let i = 0; i < abbr.length; i++) {
    hash = (hash * 31 + abbr.charCodeAt(i)) >>> 0;
  }
  return hash % 360;
}

export function teamColor(abbr: string): string {
  return `hsl(${teamColorHue(abbr)}, 62%, 58%)`;
}
