import { createAuthServerClient } from "@/lib/supabaseServerClient";
import { createPublicClient } from "@/lib/supabaseClient";
import { loadFanteamRoster } from "@/lib/fanteamTeam";
import { positionLabel } from "@/lib/positions";
import TeamBadge from "../../TeamBadge";
import ConnectTeamForm from "./ConnectTeamForm";
import DisconnectButton from "./DisconnectButton";
import RosterPitch from "./RosterPitch";

type RosterPlayer = {
  realPlayerId: number;
  fanteamPosition: string;
  benchPosition: string;
  isCaptain: boolean;
  player: {
    name: string;
    position: string;
    price: number;
    team: string;
    opponent: string;
    projectedPoints: number | null;
    seasonPoints: number;
    seasonGames: number;
  } | null;
};

export default async function MyTeamPage() {
  const supabase = await createAuthServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return (
      <main className="mx-auto w-full max-w-3xl flex-1 p-6">
        <p className="text-sm text-navy-300">Sign in to import your FanTeam team.</p>
      </main>
    );
  }

  const { data: linked } = await supabase.from("user_fanteam_teams").select("fanteam_entry_id, team_name").eq("user_id", user.id).maybeSingle();

  return (
    <main className="mx-auto w-full min-w-0 max-w-4xl flex-1 p-4 sm:p-6">
      <p className="text-xs font-bold uppercase tracking-wide text-emerald-400">Your Real FanTeam Roster</p>
      <h1 className="font-[family-name:var(--font-cond)] text-4xl font-extrabold text-navy-100">My Team</h1>
      <p className="mt-2 max-w-2xl text-sm text-navy-300">
        Import your real FanTeam entry and see it here with Hail Mary&apos;s own real projected points, fixtures, and season-to-date stats laid on top of
        FanTeam&apos;s own view.
      </p>

      {!linked ? (
        <div className="mt-8">
          <p className="mb-3 max-w-xl text-xs text-navy-500">
            FanTeam&apos;s own team pages are public by id, with no way for us to verify ownership - paste in the entry id or URL from your own FanTeam
            team page and we&apos;ll look it up. Anyone with the same id could look up the same public entry, the same way anyone with a public profile
            link could.
          </p>
          <ConnectTeamForm />
        </div>
      ) : (
        <TeamView entryId={linked.fanteam_entry_id} cachedName={linked.team_name} />
      )}
    </main>
  );
}

async function TeamView({ entryId, cachedName }: { entryId: number; cachedName: string | null }) {
  const supabase = createPublicClient();

  const { data: latestVersionRow } = await supabase.from("algorithm_versions").select("id").order("id", { ascending: false }).limit(1).maybeSingle();
  const algorithmVersionId = latestVersionRow?.id;
  const { data: gwRow } = algorithmVersionId
    ? await supabase.from("projections").select("gameweek").eq("horizon", 1).eq("algorithm_version_id", algorithmVersionId).order("gameweek", { ascending: false }).limit(1).maybeSingle()
    : { data: null };
  const gameweek = gwRow?.gameweek ?? 1;

  const result = await loadFanteamRoster(entryId, gameweek);
  if ("error" in result) {
    return (
      <div className="mt-8 rounded-lg border border-rose-800/50 bg-rose-950/20 p-4 text-sm text-rose-300">
        {result.error}
        <div className="mt-3">
          <DisconnectButton />
        </div>
      </div>
    );
  }
  const { team, roster } = result;

  const realPlayerIds = roster.map((r) => r.realPlayerId);
  const { data: playerRows } = await supabase
    .from("players")
    .select("id, external_id, full_name, position, price, teams!team_id(abbr, id)")
    .in("external_id", realPlayerIds.map(String));

  type PlayerRow = { id: number; external_id: string; full_name: string; position: string; price: number; teams: { abbr: string; id: number } | null };
  const byExternalId = new Map(((playerRows ?? []) as unknown as PlayerRow[]).map((p) => [p.external_id, p]));
  const ourPlayerIds = [...byExternalId.values()].map((p) => p.id);

  const { data: projectionRows } = algorithmVersionId
    ? await supabase.from("projections").select("player_id, total_points").eq("horizon", 1).eq("gameweek", gameweek).eq("algorithm_version_id", algorithmVersionId).in("player_id", ourPlayerIds)
    : { data: [] };
  const projectedByPlayerId = new Map((projectionRows ?? []).map((r) => [r.player_id, Number(r.total_points)]));

  const teamIds = [...new Set([...byExternalId.values()].map((p) => p.teams?.id).filter((id): id is number => id !== undefined))];
  const { data: fixtureRows } = await supabase
    .from("fixtures")
    .select("home_team_id, away_team_id, home:teams!home_team_id(abbr), away:teams!away_team_id(abbr)")
    .eq("gameweek", gameweek)
    .or(teamIds.length ? `home_team_id.in.(${teamIds.join(",")}),away_team_id.in.(${teamIds.join(",")})` : "home_team_id.eq.-1");
  type FixtureJoin = { home_team_id: number; away_team_id: number; home: { abbr: string } | null; away: { abbr: string } | null };
  const opponentByTeamId = new Map<number, string>();
  for (const f of (fixtureRows ?? []) as unknown as FixtureJoin[]) {
    if (f.home && f.away) {
      opponentByTeamId.set(f.home_team_id, `vs ${f.away.abbr}`);
      opponentByTeamId.set(f.away_team_id, `@ ${f.home.abbr}`);
    }
  }

  const { data: statRows } = await supabase.from("player_stats").select("player_id, total_points").not("gameweek", "is", null).in("player_id", ourPlayerIds);
  const seasonByPlayerId = new Map<number, { points: number; games: number }>();
  for (const row of statRows ?? []) {
    const agg = seasonByPlayerId.get(row.player_id) ?? { points: 0, games: 0 };
    agg.points += Number(row.total_points ?? 0);
    agg.games += 1;
    seasonByPlayerId.set(row.player_id, agg);
  }

  const rosterPlayers: RosterPlayer[] = roster.map((r) => {
    const matched = byExternalId.get(String(r.realPlayerId));
    if (!matched) return { realPlayerId: r.realPlayerId, fanteamPosition: r.position, benchPosition: r.benchPosition, isCaptain: r.isCaptain, player: null };
    const season = seasonByPlayerId.get(matched.id);
    return {
      realPlayerId: r.realPlayerId,
      fanteamPosition: r.position,
      benchPosition: r.benchPosition,
      isCaptain: r.isCaptain,
      player: {
        name: matched.full_name,
        position: matched.position,
        price: Number(matched.price),
        team: matched.teams?.abbr ?? "—",
        opponent: matched.teams ? (opponentByTeamId.get(matched.teams.id) ?? "—") : "—",
        projectedPoints: projectedByPlayerId.get(matched.id) ?? null,
        seasonPoints: season?.points ?? 0,
        seasonGames: season?.games ?? 0,
      },
    };
  });

  const fieldPlayers = rosterPlayers.filter((r) => r.benchPosition === "field");
  const benchPlayers = rosterPlayers.filter((r) => r.benchPosition !== "field");

  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-navy-800 bg-navy-900 p-4">
        <div>
          <p className="font-[family-name:var(--font-cond)] text-xl font-extrabold text-navy-100">{team.teamName || cachedName}</p>
          <p className="text-xs text-navy-500">Real FanTeam rank {team.totalRank || "—"} · Real total score {team.totalScore.toFixed(1)}</p>
        </div>
        <DisconnectButton />
      </div>

      <p className="mt-4 text-xs font-bold uppercase tracking-wide text-navy-500">Gameweek {gameweek} · Starting lineup</p>
      <div className="mt-2">
        <RosterPitch players={fieldPlayers} />
      </div>

      {benchPlayers.length > 0 && (
        <>
          <p className="mt-6 text-xs font-bold uppercase tracking-wide text-navy-500">Bench</p>
          <RosterGrid players={benchPlayers} />
        </>
      )}
    </div>
  );
}

function RosterGrid({ players }: { players: RosterPlayer[] }) {
  return (
    <div className="mt-2 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
      {players.map((r) => (
        <div key={r.realPlayerId} className="rounded-lg border border-navy-800 bg-navy-900 p-3">
          {!r.player ? (
            <p className="text-sm text-navy-500">Player not tracked yet (real FanTeam id {r.realPlayerId}).</p>
          ) : (
            <>
              <div className="flex items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <TeamBadge team={r.player.team} size="sm" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-navy-100">
                      {r.player.name} {r.isCaptain && <span className="text-amber-400">(C)</span>}
                    </p>
                    <p className="text-[11px] text-navy-500">
                      {positionLabel(r.player.position)} · {r.player.team} {r.player.opponent}
                    </p>
                  </div>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-mono text-sm font-bold text-sky-300">{r.player.projectedPoints !== null ? r.player.projectedPoints.toFixed(1) : "—"}</p>
                  <p className="text-[9px] tracking-wide text-navy-500 uppercase">Our proj.</p>
                </div>
              </div>
              <div className="mt-2 flex justify-between font-mono text-[11px] text-navy-400">
                <span>£{r.player.price.toFixed(1)}m</span>
                <span>
                  {r.player.seasonGames > 0 ? `${r.player.seasonPoints.toFixed(1)}pts real season total (${r.player.seasonGames} GW)` : "No real stats yet"}
                </span>
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
