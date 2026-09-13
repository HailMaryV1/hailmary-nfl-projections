/**
 * fanteamTeam.ts
 * ----------------
 * Real, unauthenticated FanTeam/ScoutGG lookups for a single public entry
 * in tournament 1136503 ("NFL Regular Season 2026/27") - the TypeScript
 * side of the same discovery the Python scrapers (scripts/scrape_fanteam*)
 * already use: FanTeam's own frontend sends `bearer[white_label]=fanteam`
 * on every API call, signed in or not - not a secret, not tied to any
 * user/session, just an app identifier the API now enforces.
 *
 * Real, inherent limitation, not a bug: FanTeam's own public per-entry
 * dashboards have no ownership check at all (confirmed live 2026-09-13 -
 * a never-authenticated browser renders any entry's full roster by id).
 * There is no OAuth from FanTeam to prove an entry belongs to whoever
 * pastes its id in - "import your team" really means "look up any public
 * FanTeam entry by id", same trust model as pasting a public profile link.
 */

const TOURNAMENT_ID = 1136503;
const BASE = "https://fanteam-game.api.scoutgg.net";
const BEARER_QS = "bearer%5Bwhite_label%5D=fanteam";

async function fetchFanteamJson(url: string): Promise<unknown> {
  const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" }, cache: "no-store" });
  if (!res.ok) throw new Error(`FanTeam request failed: HTTP ${res.status}`);
  return res.json();
}

/**
 * Accepts either a bare numeric entry id or a pasted dashboard URL
 * (fanteam.com/fantasy/dashboard/{tournamentId}/{entryId}/{gw}). A URL for
 * a different tournament is rejected outright rather than silently
 * accepted - it's a real different game, not this one.
 */
export function parseFanteamEntryId(input: string): { entryId: number } | { error: string } {
  const trimmed = input.trim();
  if (/^\d+$/.test(trimmed)) return { entryId: Number(trimmed) };

  const match = trimmed.match(/fanteam\.com\/fantasy\/dashboard\/(\d+)\/(\d+)/);
  if (!match) return { error: "Paste your real FanTeam entry id, or the full dashboard URL from your FanTeam team page." };

  const [, tournamentId, entryId] = match;
  if (Number(tournamentId) !== TOURNAMENT_ID) {
    return { error: "That link isn't for the NFL Regular Season 2026/27 tournament (id 1136503) - double check you copied your NFL team's URL." };
  }
  return { entryId: Number(entryId) };
}

type FantasyTeamResponse = {
  fantasyTeam?: { id: number; name: string; tournamentId: number; totalScore: number; totalRank: number; user?: { name: string } };
  fantasyPlayers?: { realPlayerId: number; position: string; benchPosition: string; captaincy: string }[];
};

export async function validateFanteamEntry(entryId: number): Promise<{ teamName: string } | { error: string }> {
  // Unlike the tournament-wide players endpoint, /fantasy_teams/{id} real-ly
  // requires a numeric round - "editable" 401s here (confirmed live
  // 2026-09-13). Round 1 always exists for a real entry regardless of the
  // current gameweek, so it's the right round to validate against.
  let data: FantasyTeamResponse;
  try {
    data = (await fetchFanteamJson(`${BASE}/fantasy_teams/${entryId}?round=1&${BEARER_QS}`)) as FantasyTeamResponse;
  } catch {
    return { error: "Couldn't find a real FanTeam entry with that id - double check it and try again." };
  }
  const team = data.fantasyTeam;
  if (!team || team.tournamentId !== TOURNAMENT_ID) {
    return { error: "That entry isn't part of the NFL Regular Season 2026/27 tournament." };
  }
  return { teamName: team.name || team.user?.name || `Entry ${entryId}` };
}

export type FanteamRosterEntry = {
  realPlayerId: number;
  position: string;
  benchPosition: string;
  isCaptain: boolean;
};

export type FanteamTeamInfo = { teamName: string; totalScore: number; totalRank: number };

export async function loadFanteamRoster(entryId: number, gameweek: number): Promise<{ team: FanteamTeamInfo; roster: FanteamRosterEntry[] } | { error: string }> {
  let data: FantasyTeamResponse;
  try {
    data = (await fetchFanteamJson(`${BASE}/fantasy_teams/${entryId}?round=${gameweek}&${BEARER_QS}`)) as FantasyTeamResponse;
  } catch {
    return { error: "Couldn't load that FanTeam entry right now - it may have been removed, or FanTeam's real API is temporarily unavailable." };
  }
  const team = data.fantasyTeam;
  if (!team) return { error: "That FanTeam entry no longer exists." };

  const roster: FanteamRosterEntry[] = (data.fantasyPlayers ?? []).map((p) => ({
    realPlayerId: p.realPlayerId,
    position: p.position,
    benchPosition: p.benchPosition,
    isCaptain: p.captaincy === "captain",
  }));

  return {
    team: { teamName: team.name || team.user?.name || `Entry ${entryId}`, totalScore: Number(team.totalScore ?? 0), totalRank: Number(team.totalRank ?? 0) },
    roster,
  };
}
