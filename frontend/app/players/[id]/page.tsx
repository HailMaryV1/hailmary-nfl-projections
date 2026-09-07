import Link from "next/link";
import { notFound } from "next/navigation";
import SiteHeader from "../../SiteHeader";
import { createPublicClient } from "@/lib/supabaseClient";
import { positionLabel } from "@/lib/positions";

const HORIZON = 1;

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

export default async function PlayerPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ from?: string }> }) {
  const { id } = await params;
  const { from } = await searchParams;
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
    .eq("horizon", HORIZON)
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

  const backHref = from ? `/${from.replace(/^\/+/, "")}` : "/";

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
              <div className="text-xs uppercase tracking-wide text-navy-500">Projected Points · GW{projection.gameweek}</div>
            </div>
          )}
        </div>

        {!projection ? (
          <p className="mt-8 text-sm text-navy-400">No projection available for this player yet.</p>
        ) : (
          <>
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
                    ) : (
                      <div className="mt-1 text-sm text-navy-100">
                        {info.populated ? "Live" : <span className="text-navy-500">Not yet available</span>}
                      </div>
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
