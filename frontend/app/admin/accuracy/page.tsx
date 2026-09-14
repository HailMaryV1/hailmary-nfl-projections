import Link from "next/link";
import { createPublicClient } from "@/lib/supabaseClient";
import { fetchAllRows } from "@/lib/supabasePaginate";
import { POSITION_ORDER, positionLabel } from "@/lib/positions";
import { type Segment, type PointsPair, buildSegment, mae, medianAbsoluteError, rmse, bias, errorBuckets, SMALL_SAMPLE_THRESHOLD } from "@/lib/accuracyMetrics";

// predictions_and_actuals (migration 0009) has "public read" RLS, same as
// every other reference table this app reads from - createPublicClient()
// is enough here, no service-role client needed for a read-only page.
//
// No club-prediction section here (unlike the sibling EFL-Projections
// repo's own Accuracy page) - NFL has no equivalent concept to Fantasy
// EFL's separate club win/draw/clean-sheet picks; every real prediction
// this project makes is a player prediction.

type PlayerSummaryRow = {
  player_id: number;
  gameweek: number;
  predicted_points: number;
  actual_points: number | null;
  players: { position: string } | null;
};

type PlayerDetailRow = {
  player_id: number;
  gameweek: number;
  predicted_points: number;
  actual_points: number | null;
  players: { full_name: string; teams: { name: string } | null } | null;
};

function toPair(r: { predicted_points: number; actual_points: number | null }): PointsPair {
  return { predicted: Number(r.predicted_points), actual: Number(r.actual_points) };
}

function fmt(n: number | null) {
  return n !== null ? n.toFixed(2) : "—";
}

function Stat({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-lg border border-navy-800 bg-navy-900 p-4">
      <p className="text-2xl font-semibold tabular-nums text-navy-100">{value}</p>
      <p className="text-xs text-navy-300">{label}</p>
      {hint && <p className="mt-0.5 text-[11px] text-navy-500">{hint}</p>}
    </div>
  );
}

function BucketStat({ label, value, isWorst = false }: { label: string; value: number; isWorst?: boolean }) {
  return (
    <div className="rounded-lg border border-navy-800 bg-navy-900 p-3">
      <p className={`text-xl font-semibold tabular-nums ${isWorst ? "text-navy-300" : "text-emerald-400"}`}>{value.toFixed(1)}%</p>
      <p className="mt-0.5 text-[11px] text-navy-400">{label}</p>
    </div>
  );
}

function SmallSampleTag({ n }: { n: number }) {
  if (n >= SMALL_SAMPLE_THRESHOLD) return null;
  return (
    <span
      className="ml-1.5 rounded-full bg-navy-800 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-navy-500"
      title={`Only ${n} real captured results - treat this number with more caution than a larger sample.`}
    >
      Small sample
    </span>
  );
}

function SegmentBreakdown({ title, note, segments }: { title: string; note: string; segments: Segment[] }) {
  const ranked = segments.filter((s) => s.n > 0).sort((a, b) => (b.mae ?? 0) - (a.mae ?? 0));
  const worstMae = ranked[0]?.mae ?? 0;
  return (
    <div className="rounded-lg border border-navy-800 bg-navy-900 p-4">
      <p className="text-sm font-semibold text-navy-100">{title}</p>
      <p className="mt-0.5 text-xs text-navy-400">{note}</p>
      <div className="mt-3 flex flex-col gap-2.5">
        {ranked.map((s) => (
          <div key={s.label}>
            <div className="flex flex-wrap items-baseline justify-between gap-x-2 gap-y-0.5 text-sm">
              <span className="text-navy-200">
                {s.label}
                <SmallSampleTag n={s.n} />
              </span>
              <span className="tabular-nums text-navy-100">
                {s.mae !== null ? s.mae.toFixed(2) : "—"} <span className="text-xs text-navy-500">MAE · n={s.n}</span>
                {s.bias !== null && (
                  <span className={`ml-2 text-xs ${s.bias > 0.1 ? "text-amber-400" : s.bias < -0.1 ? "text-sky-400" : "text-navy-500"}`}>
                    {s.bias > 0 ? "+" : ""}
                    {s.bias.toFixed(2)} bias
                  </span>
                )}
              </span>
            </div>
            <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-navy-800">
              <div className="h-full rounded-full bg-rose-400" style={{ width: worstMae > 0 ? `${((s.mae ?? 0) / worstMae) * 100}%` : "0%" }} />
            </div>
          </div>
        ))}
        {ranked.length === 0 && <p className="text-xs text-navy-500">Not enough real captured results yet.</p>}
      </div>
    </div>
  );
}

export default async function AdminAccuracyPage({ searchParams }: { searchParams: Promise<{ gameweek?: string }> }) {
  const params = await searchParams;
  const supabase = createPublicClient();

  // Range-paginated through fetchAllRows - see that helper's own comment.
  // Not an issue yet at 603 players/gameweek, but will be once several
  // gameweeks have accumulated real frozen predictions.
  const playerSummary = await fetchAllRows<PlayerSummaryRow>(
    (from, to) =>
      supabase
        .from("predictions_and_actuals")
        .select("player_id, gameweek, predicted_points, actual_points, players!inner(position)")
        .range(from, to) as unknown as PromiseLike<{ data: PlayerSummaryRow[] | null; error: { message: string } | null }>
  );

  const playerCaptured = playerSummary.filter((r) => r.actual_points !== null);

  const positionSegments: Segment[] = POSITION_ORDER.map((pos) => buildSegment(positionLabel(pos), playerCaptured.filter((r) => r.players?.position === pos).map(toPair)));

  const playerGameweeks = Array.from(new Set(playerSummary.map((r) => r.gameweek))).sort((a, b) => b - a);
  const selectedGw = params.gameweek ? Number(params.gameweek) : playerGameweeks[0];

  const playerDetail =
    selectedGw !== undefined
      ? await fetchAllRows<PlayerDetailRow>(
          (from, to) =>
            supabase
              .from("predictions_and_actuals")
              .select("player_id, gameweek, predicted_points, actual_points, players!inner(full_name, teams!team_id(name))")
              .eq("gameweek", selectedGw)
              .order("predicted_points", { ascending: false })
              .range(from, to) as unknown as PromiseLike<{ data: PlayerDetailRow[] | null; error: { message: string } | null }>
        )
      : [];

  const overallMae = mae(playerCaptured.map(toPair));
  const overallMedianAe = medianAbsoluteError(playerCaptured.map(toPair));
  const overallRmse = rmse(playerCaptured.map(toPair));
  const overallBias = bias(playerCaptured.map(toPair));
  const buckets = errorBuckets(playerCaptured.map(toPair));

  return (
    <div className="mx-auto w-full min-w-0 max-w-5xl">
      <h1 className="text-2xl font-semibold text-navy-100">Prediction Accuracy</h1>
      <p className="mt-1 text-sm text-navy-300">
        Every prediction is frozen the moment it&rsquo;s made - before kickoff - and never edited again. This is what the model actually said, compared to
        what really happened.
      </p>
      <p className="mt-2 max-w-2xl text-xs text-navy-500">
        No snap-percentage diagnostics on this page - FanTeam&rsquo;s real per-player stats don&rsquo;t currently expose a real snap-percentage figure, so
        <code className="text-navy-400"> actual_snap_pct</code> stays empty rather than a fabricated proxy.
      </p>

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Predictions frozen" value={playerSummary.length} />
        <Stat label="Results captured" value={playerCaptured.length} />
        <Stat label="Mean absolute error" value={fmt(overallMae)} />
        <Stat label="Median absolute error" value={fmt(overallMedianAe)} />
        <Stat label="RMSE" value={fmt(overallRmse)} />
        <Stat
          label="Model bias"
          value={overallBias !== null ? `${overallBias > 0 ? "+" : ""}${overallBias.toFixed(2)}` : "—"}
          hint={overallBias === null ? undefined : overallBias > 0.1 ? "Slight over-projection" : overallBias < -0.1 ? "Slight under-projection" : "Well centred"}
        />
      </div>

      <div className="mt-4">
        <p className="text-xs text-navy-500">Share of every real captured prediction landing within a given number of points of what actually happened.</p>
        {buckets ? (
          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <BucketStat label="Within ±1pt" value={buckets.within1} />
            <BucketStat label="Within ±2pt" value={buckets.within2} />
            <BucketStat label="Within ±3pt" value={buckets.within3} />
            <BucketStat label="Within ±5pt" value={buckets.within5} />
            <BucketStat label="More than 5pt away" value={buckets.beyond5} isWorst />
          </div>
        ) : (
          <p className="mt-3 text-xs text-navy-500">Not enough real captured results yet.</p>
        )}
      </div>

      <div className="mt-6">
        <SegmentBreakdown title="Position" note="Which position is hardest to price correctly right now?" segments={positionSegments} />
      </div>

      <div className="mt-6 flex flex-wrap gap-1">
        {playerGameweeks.map((gw) => (
          <Link
            key={gw}
            href={`/admin/accuracy?gameweek=${gw}`}
            className={`rounded-md px-3 py-1.5 text-sm ${gw === selectedGw ? "bg-sky-600 text-white" : "bg-navy-900 text-navy-200 hover:bg-navy-800"}`}
          >
            GW{gw}
          </Link>
        ))}
      </div>

      {playerDetail.length === 0 ? (
        <p className="mt-4 text-sm text-navy-400">No frozen predictions for this gameweek yet.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[560px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-navy-800 text-left text-xs uppercase tracking-wide text-navy-400">
                <th className="py-2 pr-4">Player</th>
                <th className="py-2 pr-4">Team</th>
                <th className="py-2 pr-4">Predicted</th>
                <th className="py-2 pr-4">Actual</th>
                <th className="py-2">Error</th>
              </tr>
            </thead>
            <tbody>
              {playerDetail.map((r) => {
                const hasActual = r.actual_points !== null;
                const error = hasActual ? Number(r.actual_points) - Number(r.predicted_points) : null;
                return (
                  <tr key={r.player_id} className="border-b border-navy-800/60">
                    <td className="py-2 pr-4 font-medium text-navy-100">{r.players?.full_name ?? "—"}</td>
                    <td className="py-2 pr-4 text-navy-300">{r.players?.teams?.name ?? "—"}</td>
                    <td className="py-2 pr-4 tabular-nums text-navy-100">{Number(r.predicted_points).toFixed(2)}</td>
                    <td className="py-2 pr-4 tabular-nums text-navy-100">{hasActual ? Number(r.actual_points).toFixed(2) : "not played yet"}</td>
                    <td className={`py-2 tabular-nums ${error !== null && error < 0 ? "text-rose-400" : error !== null && error > 0 ? "text-emerald-400" : "text-navy-100"}`}>
                      {error !== null ? (error > 0 ? `+${error.toFixed(2)}` : error.toFixed(2)) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
