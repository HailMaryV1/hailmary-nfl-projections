import { type ComparePlayer, type StatLine, statGroup } from "@/lib/comparePlayer";
import { POSITION_COLOR_VAR, positionLabel } from "@/lib/positions";
import { DIFFICULTY_COLORS } from "@/lib/fixtureDifficulty";

export type { ComparePlayer };

const COLOR_A = "#38bdf8";
const COLOR_B = "#fb7185";

function fmt1(n: number | null | undefined) {
  return n === null || n === undefined ? "—" : n.toFixed(1);
}

function PositionTag({ position }: { position: string }) {
  const cssVar = POSITION_COLOR_VAR[position] ?? "--color-navy-300";
  return (
    <span
      className="rounded px-1.5 py-0.5 font-[family-name:var(--font-cond)] text-xs font-bold uppercase tracking-wide"
      style={{ color: `var(${cssVar})`, backgroundColor: `color-mix(in srgb, var(${cssVar}) 16%, transparent)` }}
    >
      {positionLabel(position)}
    </span>
  );
}

function MiniHeader({ player, color, align }: { player: ComparePlayer; color: string; align: "left" | "right" }) {
  return (
    <div className={`flex min-w-0 flex-col gap-1.5 border-t-2 pt-3 ${align === "right" ? "items-end text-right" : "items-start text-left"}`} style={{ borderColor: color }}>
      <PositionTag position={player.position} />
      <div className="min-w-0">
        <div className="truncate font-[family-name:var(--font-cond)] text-2xl font-extrabold text-navy-50">{player.name}</div>
        <div className="truncate text-sm font-semibold text-navy-300">
          {player.team.name} · £{player.price}m
        </div>
      </div>
    </div>
  );
}

function CompareRow({ label, valueA, valueB, formatA, formatB, note }: { label: string; valueA: number; valueB: number; formatA: string; formatB: string; note?: string }) {
  const max = Math.max(valueA, valueB, 1e-6);
  const aWins = valueA > valueB;
  const bWins = valueB > valueA;
  return (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
      <div className="flex min-w-0 flex-col items-end gap-1.5">
        <span className={`font-mono text-xl font-extrabold tabular-nums sm:text-2xl ${aWins ? "text-sky-300" : "text-navy-300"}`}>{formatA}</span>
        <div className="h-2 w-full max-w-[140px] overflow-hidden rounded-full bg-navy-800">
          <div className="ml-auto h-full rounded-full" style={{ width: `${(valueA / max) * 100}%`, background: COLOR_A }} />
        </div>
      </div>
      <div className="w-24 min-w-0 px-1 text-center sm:w-32">
        <div className="text-sm font-bold uppercase tracking-wide text-navy-300">{label}</div>
        {note && <div className="text-[11px] text-navy-600">{note}</div>}
      </div>
      <div className="flex min-w-0 flex-col items-start gap-1.5">
        <span className={`font-mono text-xl font-extrabold tabular-nums sm:text-2xl ${bWins ? "text-rose-300" : "text-navy-300"}`}>{formatB}</span>
        <div className="h-2 w-full max-w-[140px] overflow-hidden rounded-full bg-navy-800">
          <div className="h-full rounded-full" style={{ width: `${(valueB / max) * 100}%`, background: COLOR_B }} />
        </div>
      </div>
    </div>
  );
}

function FixtureTicker({ player }: { player: ComparePlayer }) {
  return (
    <div className="grid grid-cols-6 gap-1 sm:gap-1.5">
      {player.upcomingFixtures.length === 0 && <span className="col-span-6 text-center text-xs text-navy-500">No real upcoming fixtures found yet.</span>}
      {player.upcomingFixtures.map((f) => {
        const colors = DIFFICULTY_COLORS[f.tier];
        return (
          <div
            key={f.gameweek}
            className="flex aspect-square flex-col items-center justify-center gap-0.5 rounded-md px-1"
            style={{ backgroundColor: colors.bg }}
            title={f.isBye ? `GW${f.gameweek}: Bye` : `GW${f.gameweek}: ${f.isHome ? "vs" : "@"} ${f.opponentAbbr ?? "—"}`}
          >
            <span className="text-[9px] font-bold uppercase tracking-wide" style={{ color: colors.text, opacity: 0.75 }}>
              GW{f.gameweek}
            </span>
            <span className="truncate font-mono text-xs font-extrabold" style={{ color: colors.text }}>
              {f.isBye ? "BYE" : `${f.isHome ? "" : "@"}${f.opponentAbbr}`}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// Shared-group stats: both players track the exact same stat set, so each
// stat gets one side-by-side bar row - same pattern as the points/ownership
// rows above. A row only appears when BOTH players have a real recorded
// value for that stat; if either side has none yet (see ComparePlayer's own
// doc comment - genuinely the case for the whole site this early in the
// season) that single stat is left out rather than showing a fabricated 0
// against a real number.
function SharedStatRows({ playerA, playerB }: { playerA: ComparePlayer; playerB: ComparePlayer }) {
  const byKeyA = new Map(playerA.statLines.map((l) => [l.key, l]));
  const byKeyB = new Map(playerB.statLines.map((l) => [l.key, l]));
  const keys = [...new Set([...byKeyA.keys(), ...byKeyB.keys()])];
  const rows: { key: string; a: StatLine; b: StatLine }[] = [];
  for (const key of keys) {
    const a = byKeyA.get(key);
    const b = byKeyB.get(key);
    if (a && b) rows.push({ key, a, b });
  }

  if (rows.length === 0) {
    return <p className="text-center text-sm text-navy-500">No real season stats recorded yet for either player.</p>;
  }

  return (
    <div className="flex flex-col gap-5">
      {rows.map((r) => (
        <CompareRow key={r.key} label={r.a.label} note="Real season total" valueA={r.a.value} valueB={r.b.value} formatA={String(r.a.value)} formatB={String(r.b.value)} />
      ))}
    </div>
  );
}

// Cross-group stats (e.g. QB vs WR): the two positions don't share a stat
// set at all, so forcing a shared row per stat would mean inventing a
// number for whichever side can't produce that stat. Two independent
// columns instead - each side's own real, position-relevant totals.
function StatColumns({ playerA, playerB }: { playerA: ComparePlayer; playerB: ComparePlayer }) {
  return (
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
      {[playerA, playerB].map((player, i) => (
        <div key={player.id} className={i === 0 ? "sm:text-right" : "sm:text-left"}>
          <div className="mb-2 text-xs font-bold uppercase tracking-wide text-navy-400">
            {player.name} · {positionLabel(player.position)}
          </div>
          {player.statLines.length === 0 ? (
            <p className="text-sm text-navy-500">No real season stats recorded yet.</p>
          ) : (
            <ul className="flex flex-col gap-1.5">
              {player.statLines.map((line) => (
                <li key={line.key} className={`flex items-center gap-2 text-sm ${i === 0 ? "justify-end" : "justify-start"}`}>
                  <span className="font-mono font-bold tabular-nums text-navy-100">{line.value}</span>
                  <span className="text-navy-400">{line.label}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

export default function CompareView({ playerA, playerB }: { playerA: ComparePlayer; playerB: ComparePlayer }) {
  const havePpg = playerA.seasonPointsSoFar !== null && playerB.seasonPointsSoFar !== null && playerA.gamesPlayed !== null && playerB.gamesPlayed !== null;
  const perGameA = havePpg && playerA.gamesPlayed! > 0 ? playerA.seasonPointsSoFar! / playerA.gamesPlayed! : 0;
  const perGameB = havePpg && playerB.gamesPlayed! > 0 ? playerB.seasonPointsSoFar! / playerB.gamesPlayed! : 0;
  const haveSeasonPoints = playerA.seasonPointsSoFar !== null && playerB.seasonPointsSoFar !== null;
  const sameGroup = statGroup(playerA.position) === statGroup(playerB.position);

  return (
    <div className="flex flex-col gap-8 rounded-2xl border border-navy-800 bg-navy-900 p-6">
      <div>
        <div className="mb-4 grid grid-cols-2 items-start gap-4">
          <MiniHeader player={playerA} color={COLOR_A} align="left" />
          <MiniHeader player={playerB} color={COLOR_B} align="right" />
        </div>
        <p className="mb-5 text-center font-[family-name:var(--font-cond)] text-lg font-extrabold uppercase tracking-wide text-navy-200">
          FanTeam NFL Regular Season 2026/27 · Head-to-Head
        </p>
        <div className="flex flex-col gap-5">
          <CompareRow
            label="This Week"
            note="Projected points this gameweek"
            valueA={playerA.pointsByHorizon[1] ?? 0}
            valueB={playerB.pointsByHorizon[1] ?? 0}
            formatA={fmt1(playerA.pointsByHorizon[1])}
            formatB={fmt1(playerB.pointsByHorizon[1])}
          />
          <CompareRow
            label="Next 5 GWs"
            note="Total projected points over the next 5 gameweeks"
            valueA={playerA.pointsByHorizon[5] ?? 0}
            valueB={playerB.pointsByHorizon[5] ?? 0}
            formatA={fmt1(playerA.pointsByHorizon[5])}
            formatB={fmt1(playerB.pointsByHorizon[5])}
          />
          {haveSeasonPoints ? (
            <CompareRow
              label="Season Points"
              note="Real total so far"
              valueA={playerA.seasonPointsSoFar!}
              valueB={playerB.seasonPointsSoFar!}
              formatA={fmt1(playerA.seasonPointsSoFar)}
              formatB={fmt1(playerB.seasonPointsSoFar)}
            />
          ) : (
            <p className="text-center text-xs text-navy-500">No real games played yet this season - season points aren&apos;t available until week 1 is final.</p>
          )}
          {havePpg && (
            <CompareRow
              label="Points Per Game"
              note={`${playerA.gamesPlayed} vs ${playerB.gamesPlayed} real games played`}
              valueA={perGameA}
              valueB={perGameB}
              formatA={fmt1(perGameA)}
              formatB={fmt1(perGameB)}
            />
          )}
          <CompareRow
            label="Ownership"
            note="% of managers who own this player right now"
            valueA={playerA.ownershipPct ?? 0}
            valueB={playerB.ownershipPct ?? 0}
            formatA={playerA.ownershipPct === null ? "—" : `${playerA.ownershipPct.toFixed(1)}%`}
            formatB={playerB.ownershipPct === null ? "—" : `${playerB.ownershipPct.toFixed(1)}%`}
          />
        </div>
      </div>

      <section>
        <h2 className="mb-4 text-center font-[family-name:var(--font-cond)] text-lg font-extrabold uppercase tracking-wide text-navy-200">Season Stats</h2>
        {sameGroup ? <SharedStatRows playerA={playerA} playerB={playerB} /> : <StatColumns playerA={playerA} playerB={playerB} />}
      </section>

      <section>
        <h2 className="mb-4 text-center font-[family-name:var(--font-cond)] text-lg font-extrabold uppercase tracking-wide text-navy-200">Upcoming Fixtures</h2>
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <FixtureTicker player={playerA} />
          <FixtureTicker player={playerB} />
        </div>
      </section>
    </div>
  );
}
