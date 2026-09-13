// Real per-team jersey art (provided by the user, sliced from a single
// 32-team sheet into public/jerseys/{ABBR}.png - see
// scripts/slice_jerseys.py) - used everywhere a team needs a visual
// identifier. Falls back to the old generated-color initial chip only if a
// team's jersey art is somehow missing, so a real gap is visible rather
// than a broken image.
import { teamColor } from "@/lib/teamColors";
import { JERSEY_TEAMS } from "@/lib/jerseyTeams";

const SIZES = {
  sm: { box: 30, font: 11.5, radius: 8 },
  md: { box: 46, font: 14, radius: 12 },
  lg: { box: 60, font: 19, radius: 14 },
};

export default function TeamBadge({ team, size = "sm" }: { team: string; size?: keyof typeof SIZES }) {
  const { box, font, radius } = SIZES[size];

  if (JERSEY_TEAMS.has(team)) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- local public asset, dynamic per-team src, no optimization needed at this size.
      <img src={`/jerseys/${team}.png`} alt={`${team} jersey`} width={box} height={box} className="shrink-0 object-contain drop-shadow-[0_4px_10px_rgba(0,0,0,0.45)]" style={{ width: box, height: box }} />
    );
  }

  const bg = teamColor(team);
  return (
    <div
      className="flex shrink-0 items-center justify-center font-[family-name:var(--font-cond)] font-bold text-navy-950"
      style={{
        width: box,
        height: box,
        fontSize: font,
        borderRadius: radius,
        background: `linear-gradient(145deg, color-mix(in srgb, ${bg} 100%, white 25%), ${bg})`,
        boxShadow: `0 6px 18px -4px color-mix(in srgb, ${bg} 70%, transparent), inset 0 1px 0 #ffffff40`,
      }}
    >
      {team}
    </div>
  );
}
