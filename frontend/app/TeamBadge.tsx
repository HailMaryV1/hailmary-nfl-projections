import { teamColor } from "@/lib/teamColors";

// Same generated-color reasoning as lib/teamColors.ts's own comment - a
// consistent visual identifier, not a real team brand color (none exists
// in this project's schema). Text is a fixed dark navy rather than a
// per-team contrast calculation - safe against every generated color at
// this component's fixed 62%/58% HSL lightness.
const SIZES = {
  sm: { box: 30, font: 11.5, radius: 8 },
  md: { box: 46, font: 14, radius: 12 },
  lg: { box: 60, font: 19, radius: 14 },
};

export default function TeamBadge({ team, size = "sm" }: { team: string; size?: keyof typeof SIZES }) {
  const { box, font, radius } = SIZES[size];
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
