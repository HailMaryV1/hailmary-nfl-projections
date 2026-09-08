import Link from "next/link";
import { notFound } from "next/navigation";
import SiteHeader from "../../SiteHeader";
import { createPublicClient } from "@/lib/supabaseClient";
import { positionLabel } from "@/lib/positions";
import { DIFFICULTY_COLORS, computeDifficultyThresholds, difficultyTier } from "@/lib/fixtureDifficulty";

const UPCOMING_FIXTURES_COUNT = 6;

const HORIZONS = [1, 2, 3, 5];
const HORIZON_LABELS: Record<number, string> = { 1: "This Week", 2: "Next 2", 3: "Next 3", 5: "Next 5" };

const STAT_LABELS: Record<string, string> = {
  passing_yards: "Passing Yards", passing_td: "Passing TDs", rushing_yards: "Rushing Yards",
  rushing_td: "Rushing TDs", receiving_yards: "Receiving Yards", receiving_td: "Receiving TDs",
  reception: "Receptions", anytime_td: "Anytime TD", return_td: "Return TD",
  interception_thrown: "INTs Thrown", fumble_lost: "Fumbles Lost", two_point_conversion: "2pt Conversions",
  sack: "Sacks", interception: "INTs", fumble_recovery: "Fumble Recoveries", safety: "Safeties",
  blocked_kick: "Blocked Kicks", defensive_td: "Defensive TD",
  points_allowed_0: "0 Pts Allowed", points_allowed_1_6: "1-6 Pts Allowed", points_allowed_7_13: "7-13 Pts Allowed",
  points_allowed_14_20: "14-20 Pts Allowed", points_allowed_21_27: "21-27 Pts Allowed",
  points_allowed_28_34: "28-34 Pts Allowed", points_allowed_35_plus: "35+ Pts Allowed",
};

const LAYER_LABELS: Record<string, string> = {
  lineup_status: "Lineup Status", form: "Form", fixture_quantity: "Fixture Quantity",
  fixture_quality: "Fixture Quality", live_odds: "Live Odds",
};

function statLabel(stat: string): string {
  return STAT_LABELS[stat] ?? stat;
}

export default async function PlayerPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ from?: string; horizon?: string }> }) {
  const { id } = await params;
  const { from, horizon: horizonParam } = await searchParams;
  const horizon = HORIZONS.includes(Number(horizonParam)) ? Number(horizonParam) : 1;
  const supabase = createPublicClient();

  const { data: player, error: playerError } = await supabase
    .from("players")
    .select("id, full_name, position, price, team_id, teams!team_id(name, abbr)")
    .eq("id", id)
    .maybeSingle();
  if (playerError) throw new Error(`Failed to load player: ${playerError.message}`);
  if (!player) notFound();

  type TeamJoin = { name: string; abbr: string } | null;
  const team = player.teams as unknown as TeamJoin;

  const { data: projection } = await supabase
    .from("projections")
    .select("gameweek, total_points, rating, per_stat, per_layer, data_confidence, algorithm_version_id")
    .eq("player_id", id)
    .eq("horizon", horizon)
    .order("algorithm_version_id", { ascending: false })
    .order("gameweek", { ascending: false })
    .limit(1)
    .maybeSingle();

  let opponentLabel: string | null = null;
  if (projection) {
    const { data: fixture } = await supabase
      .from("fixtures")
      .select("home_team_id, away_team_id, kickoff_at, home:teams!home_team_id(abbr), away:teams!away_team_id(abbr)")
      .eq("gameweek", projection.gameweek)
      .or(`home_team_id.eq.${player.team_id},away_team_id.eq.${player.team_id}`)
      .maybeSingle();
    type FixtureJoin = { home_team_id: number; home: { abbr: string } | null; away: { abbr: string } | null } | null;
    const f = fixture as unknown as FixtureJoin;
    if (f && f.home && f.away) {
      const isHome = f.home_team_id === player.team_id;
      opponentLabel = `${isHome ? "vs" : "@"} ${isHome ? f.away.abbr : f.home.abbr}`;
    }
  }

  // Real upcoming-fixture difficulty ticker - independent of the selected
  // horizon above (always shows the real next N weeks from the player's
  // own team, so it's a stable "how's their run looking" view even while
  // switching between horizon tabs).
  let upcomingFixtures: { gameweek: number; opponentAbbr: string | null; isHome: boolean | null; isBye: boolean; tier: ReturnType<typeof difficultyTier> }[] = [];
  if (projection) {
    const { data: allWinTotals } = await supabase
      .from("team_schedule_difficulty")
      .select("opponent_win_total")
      .not("opponent_win_total", "is", null)
      .eq("is_bye", false);
    const thresholds = computeDifficultyThresholds((allWinTotals ?? []).map((r) => Number(r.opponent_win_total)));

    const { data: teamSchedule } = await supabase
      .from("team_schedule_difficulty")
      .select("gameweek, is_home, is_bye, opponent_win_total, opponent:teams!opponent_team_id(abbr)")
      .eq("team_id", player.team_id)
      .gte("gameweek", projection.gameweek)
      .lt("gameweek", projection.gameweek + UPCOMING_FIXTURES_COUNT)
      .order("gameweek");

    type ScheduleJoin = { gameweek: number; is_home: boolean | null; is_bye: boolean; opponent_win_total: number | null; opponent: { abbr: string } | null };
    upcomingFixtures = ((teamSchedule ?? []) as unknown as ScheduleJoin[]).map((row) => ({
      gameweek: row.gameweek,
      opponentAbbr: row.opponent?.abbr ?? null,
      isHome: row.is_home,
      isBye: row.is_bye,
      tier: difficultyTier(row.opponent_win_total === null ? null : Number(row.opponent_win_total), row.is_bye, thresholds),
    }));
  }

  const backHref = from ? `/${from.replace(/^\/+/, "")}` : "/";
  const horizonHref = (h: number) => {
    const query = new URLSearchParams();
    if (h !== 1) query.set("horizon", String(h));
    if (from) query.set("from", from);
    const qs = query.toString();
    return qs ? `/players/${id}?${qs}` : `/players/${id}`;
  };
  const gameweekLabel = projection ? (horizon === 1 ? `GW${projection.gameweek}` : `GW${projection.gameweek}-${projection.gameweek + horizon - 1}`) : null;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto w-full min-w-0 max-w-3xl flex-1 p-4 sm:p-6">
        <Link href={backHref} className="text-sm text-navy-400 hover:text-sky-300">
          ← Back
        </Link>

        <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-navy-100">{player.full_name}</h1>
            <p className="mt-1 text-sm text-navy-300">
              {positionLabel(player.position)} · {team?.name ?? "—"} · £{player.price}m
              {opponentLabel ? ` · ${opponentLabel}` : ""}
            </p>
          </div>
          {projection && (
            <div className="text-right">
              <div className="font-[family-name:var(--font-cond)] text-4xl font-extrabold tabular-nums text-sky-300">
                {Number(projection.total_points).toFixed(1)}
              </div>
              <div className="text-xs uppercase tracking-wide text-navy-500">Projected Points · {gameweekLabel}</div>
            </div>
          )}
        </div>

        <div className="mt-3 flex flex-wrap gap-1">
          {HORIZONS.map((h) => (
            <Link
              key={h}
              href={horizonHref(h)}
              className={`rounded-full px-3.5 py-1.5 font-[family-name:var(--font-cond)] text-sm font-bold uppercase tracking-wide ${
                h === horizon ? "bg-sky-500 text-navy-950" : "bg-navy-900 text-navy-400 hover:bg-navy-800"
              }`}
            >
              {HORIZON_LABELS[h]}
            </Link>
          ))}
        </div>

        {!projection ? (
          <p className="mt-8 text-sm text-navy-400">No projection available for this player yet.</p>
        ) : (
          <>
            {upcomingFixtures.length > 0 && (
              <section className="mt-6">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-navy-400">Upcoming Fixtures</h2>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {upcomingFixtures.map((f) => {
                    const colors = DIFFICULTY_COLORS[f.tier];
                    return (
                      <span
                        key={f.gameweek}
                        className="flex flex-col items-center gap-0.5 rounded-md px-2.5 py-1.5"
                        style={{ backgroundColor: colors.bg }}
                        title={f.isBye ? `GW${f.gameweek}: Bye` : `GW${f.gameweek}: ${f.isHome ? "vs" : "@"} ${f.opponentAbbr}`}
                      >
                        <span className="text-[10px] uppercase tracking-wide" style={{ color: colors.text, opacity: 0.75 }}>
                          GW{f.gameweek}
                        </span>
                        <span className="font-mono text-xs font-bold" style={{ color: colors.text }}>
                          {f.isBye ? "BYE" : `${f.isHome ? "" : "@"}${f.opponentAbbr}`}
                        </span>
                      </span>
                    );
                  })}
                </div>
              </section>
            )}

            <section className="mt-8">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-navy-400">How this was built</h2>
              <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                {Object.entries(projection.per_layer as Record<string, { populated?: boolean; weight?: number | null; probability?: number; status?: string | null; value?: number }>).map(([layer, info]) => (
                  <div key={layer} className="rounded-lg border border-navy-800 bg-navy-900 p-3">
                    <div className="text-xs font-semibold uppercase tracking-wide text-navy-400">{LAYER_LABELS[layer] ?? layer}</div>
                    {layer === "lineup_status" ? (
                      <div className="mt-1 text-sm text-navy-100">
                        {info.status ?? "unknown"} <span className="text-navy-500">({Math.round((info.probability ?? 0) * 100)}%)</span>
                      </div>
                    ) : !info.populated ? (
                      <div className="mt-1 text-sm text-navy-500">Not yet available</div>
                    ) : layer === "fixture_quantity" && info.value !== undefined ? (
                      <div className="mt-1 text-sm text-navy-100">{Math.round(info.value * 100)}% real games</div>
                    ) : layer === "fixture_quality" && info.value !== undefined && info.value !== null ? (
                      <div className="mt-1 text-sm text-navy-100">avg ×{info.value.toFixed(2)} difficulty</div>
                    ) : (
                      <div className="mt-1 text-sm text-navy-100">Live</div>
                    )}
                  </div>
                ))}
              </div>
            </section>

            <section className="mt-8">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-navy-400">Per-stat breakdown</h2>
              <table className="mt-3 w-full border-collapse text-sm">
                <thead>
                  <tr className="border-b border-navy-800 text-left text-xs uppercase tracking-wide text-navy-500">
                    <th className="py-2 pr-3 font-medium">Stat</th>
                    <th className="py-2 pr-3 text-right font-medium">Expected</th>
                    <th className="py-2 pr-3 text-right font-medium">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(projection.per_stat as Record<string, { expected_count: number; points: number; populated: boolean }>)
                    .filter(([, info]) => info.populated || info.points !== 0)
                    .sort(([, a], [, b]) => b.points - a.points)
                    .map(([stat, info]) => (
                      <tr key={stat} className="border-b border-navy-900">
                        <td className="py-2 pr-3 text-navy-200">{statLabel(stat)}</td>
                        <td className="py-2 pr-3 text-right font-mono tabular-nums text-navy-400">{info.expected_count.toFixed(3)}</td>
                        <td className="py-2 pr-3 text-right font-mono tabular-nums text-navy-100">{info.points.toFixed(2)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </section>
          </>
        )}
      </main>
    </>
  );
}
