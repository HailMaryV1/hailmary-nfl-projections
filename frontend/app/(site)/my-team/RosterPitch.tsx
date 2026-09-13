import TeamBadge from "../../TeamBadge";
import { positionLabel } from "@/lib/positions";

export type PitchPlayer = {
  realPlayerId: number;
  fanteamPosition: string;
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

// Real FanTeam formation row order (nearest the end zone first), matching
// the layout their own dashboard renders - not our own invention.
const ROW_ORDER = ["tight_end", "wide_receiver", "quarterback", "running_back", "defense_special"];

// Real yard markers, mirrored either side of midfield - decorative field
// dressing only, not derived from any data.
const YARD_MARKERS = [10, 20, 30, 40, 50, 40, 30, 20, 10];

function lastName(full: string) {
  const parts = full.split(" ");
  return parts.length > 1 ? parts.slice(-1)[0] : full;
}

export default function RosterPitch({ players }: { players: PitchPlayer[] }) {
  const rows = ROW_ORDER.map((pos) => ({ pos, players: players.filter((p) => p.fanteamPosition === pos) })).filter((r) => r.players.length > 0);

  return (
    <div
      className="relative overflow-hidden rounded-2xl border border-emerald-900/50 shadow-2xl shadow-black/40"
      style={{
        background: `
          repeating-linear-gradient(to bottom, transparent 0, transparent 74px, rgba(255,255,255,0.5) 74px, rgba(255,255,255,0.5) 76px),
          repeating-linear-gradient(to bottom, #1e6b3d 0, #1e6b3d 76px, #1a5f36 76px, #1a5f36 152px)
        `,
      }}
    >
      {/* Hash marks - two columns of short real-field-style ticks, purely decorative field dressing. */}
      <div className="pointer-events-none absolute inset-y-0 left-[30%] w-px bg-[repeating-linear-gradient(to_bottom,rgba(255,255,255,0.45)_0,rgba(255,255,255,0.45)_6px,transparent_6px,transparent_76px)]" />
      <div className="pointer-events-none absolute inset-y-0 left-[70%] w-px bg-[repeating-linear-gradient(to_bottom,rgba(255,255,255,0.45)_0,rgba(255,255,255,0.45)_6px,transparent_6px,transparent_76px)]" />

      {/* Yard numbers, mirrored down both sidelines. */}
      <div className="pointer-events-none absolute inset-y-0 left-2 flex flex-col justify-between py-16 font-[family-name:var(--font-cond)] text-sm font-bold text-white/40 sm:left-3">
        {YARD_MARKERS.map((n, i) => (
          <span key={i}>{n}</span>
        ))}
      </div>
      <div className="pointer-events-none absolute inset-y-0 right-2 flex flex-col justify-between py-16 font-[family-name:var(--font-cond)] text-sm font-bold text-white/40 sm:right-3">
        {YARD_MARKERS.map((n, i) => (
          <span key={i}>{n}</span>
        ))}
      </div>

      {/* End zone. */}
      <div className="relative flex h-16 items-center justify-center border-b-4 border-white/70 bg-navy-950/90 sm:h-20">
        <span className="font-[family-name:var(--font-cond)] text-lg font-extrabold tracking-[0.3em] text-white/25 uppercase sm:text-2xl">Hail Mary</span>
        <svg aria-hidden viewBox="0 0 60 30" className="absolute -top-6 h-8 w-16 text-white/60 sm:-top-7 sm:h-9 sm:w-20">
          <path d="M10 30V6M50 30V6M10 6H50M10 6L2 0M50 6L58 0" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
        </svg>
      </div>

      <div className="relative flex flex-col gap-5 px-2 py-8 sm:gap-8 sm:px-10 sm:py-10">
        {rows.map(({ pos, players: rowPlayers }) => (
          <div key={pos} className="flex flex-wrap justify-evenly gap-2 sm:gap-3">
            {rowPlayers.map((r) => (
              <PlayerChip key={r.realPlayerId} entry={r} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function PlayerChip({ entry }: { entry: PitchPlayer }) {
  if (!entry.player) {
    return (
      <div className="flex w-20 flex-col items-center gap-1 rounded-xl bg-navy-950/85 px-1.5 py-2 text-center shadow-lg shadow-black/50 ring-1 ring-white/10 backdrop-blur-sm sm:w-28">
        <span className="text-[10px] text-white/50">Not tracked yet</span>
        <span className="font-mono text-[9px] text-white/30">id {entry.realPlayerId}</span>
      </div>
    );
  }
  const p = entry.player;
  return (
    <div className="flex w-20 flex-col items-center gap-1 rounded-xl bg-navy-950/85 px-1.5 py-2 text-center shadow-lg shadow-black/50 ring-1 ring-white/10 backdrop-blur-sm sm:w-28 sm:px-2 sm:py-2.5">
      <TeamBadge team={p.team} size="sm" />
      <span className="w-full min-w-0 truncate font-[family-name:var(--font-cond)] text-[11px] font-bold uppercase text-white sm:text-sm" title={p.name}>
        {lastName(p.name)} {entry.isCaptain && <span className="text-amber-400">C</span>}
      </span>
      <span className="text-[9px] text-white/45 sm:text-[10px]">
        {positionLabel(p.position)} · {p.opponent}
      </span>
      <span className="font-[family-name:var(--font-cond)] text-lg font-bold text-sky-300 sm:text-xl">{p.projectedPoints !== null ? p.projectedPoints.toFixed(1) : "—"}</span>
      <span className="text-[9px] text-white/50 sm:text-[10px]">£{p.price.toFixed(1)}m</span>
    </div>
  );
}
