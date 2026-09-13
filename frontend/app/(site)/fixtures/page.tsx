import FixtureDifficultyGrid, { type TeamScheduleRow } from "./FixtureDifficultyGrid";
import { createPublicClient } from "@/lib/supabaseClient";
import { computeDifficultyThresholds } from "@/lib/fixtureDifficulty";

export default async function FixturesPage() {
  const supabase = createPublicClient();

  const { data: latestVersionRow } = await supabase
    .from("algorithm_versions")
    .select("id")
    .order("id", { ascending: false })
    .limit(1)
    .maybeSingle();

  const { data: gwRow } = latestVersionRow
    ? await supabase
        .from("projections")
        .select("gameweek")
        .eq("horizon", 1)
        .eq("algorithm_version_id", latestVersionRow.id)
        .order("gameweek", { ascending: false })
        .limit(1)
        .maybeSingle()
    : { data: null };
  const currentGameweek = gwRow?.gameweek ?? 1;

  // Real perf fix (ported from the sibling projects): teams and
  // scheduleRows don't depend on each other or on the gameweek lookup
  // above - they were being awaited one after another anyway.
  const [{ data: teams, error: teamsError }, { data: scheduleRows, error: scheduleError }] = await Promise.all([
    supabase.from("teams").select("id, name, abbr").order("name"),
    supabase
      .from("team_schedule_difficulty")
      .select("team_id, gameweek, is_home, is_bye, opponent_win_total, opponent:teams!opponent_team_id(abbr)")
      .order("gameweek"),
  ]);
  if (teamsError) throw new Error(`Failed to load teams: ${teamsError.message}`);
  if (scheduleError) throw new Error(`Failed to load schedule difficulty: ${scheduleError.message}`);

  type RawRow = {
    team_id: number;
    gameweek: number;
    is_home: boolean | null;
    is_bye: boolean;
    opponent_win_total: number | null;
    opponent: { abbr: string } | null;
  };

  const schedule: TeamScheduleRow[] = ((scheduleRows ?? []) as unknown as RawRow[]).map((r) => ({
    teamId: r.team_id,
    gameweek: r.gameweek,
    isHome: r.is_home,
    isBye: r.is_bye,
    opponentAbbr: r.opponent?.abbr ?? null,
    opponentWinTotal: r.opponent_win_total === null ? null : Number(r.opponent_win_total),
  }));

  const thresholds = computeDifficultyThresholds(
    schedule.filter((s) => s.opponentWinTotal !== null && !s.isBye).map((s) => s.opponentWinTotal as number)
  );

  return (
    <main className="mx-auto w-full min-w-0 max-w-6xl flex-1 p-4 sm:p-6">
        <h1 className="text-2xl font-semibold text-navy-100">Fixture Difficulty</h1>
        <p className="mt-1 max-w-2xl text-sm text-navy-300">
          Real, market-derived opponent strength (Sharp Football Analysis&apos;s Vegas-win-total model) for every real
          team, every real week - rank the best and worst upcoming runs.
        </p>

        <div className="mt-6">
          <FixtureDifficultyGrid
            teams={teams ?? []}
            schedule={schedule}
            thresholds={thresholds}
            currentGameweek={currentGameweek}
          />
        </div>
    </main>
  );
}
