import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { usePages } from "../usePages";
import type { StyleProps } from "../types";

// From claude-shorts BounceCaptions: Bangers, 1 to 2 words per page, bouncy
// scale spring, rotating bright colors (accent leads the rotation).
const COLORS = ["#00FFFF", "#FF00FF", "#00FF00", "#FFFF00", "#FF6600", "#FF0066"];

export const BounceCaptions: React.FC<StyleProps> = ({ captions, breakAfter, y, accent, combineMs, fontSize }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const pages = usePages(captions, combineMs ?? 600, breakAfter);
  const page = pages.find((p) => ms >= p.startMs && ms < p.startMs + p.durationMs);
  if (!page) return null;
  const raw = spring({
    frame: frame - Math.floor((page.startMs / 1000) * fps),
    fps,
    config: { mass: 1, damping: 8, stiffness: 180 },
  });
  const palette = [accent, ...COLORS];
  const color = palette[pages.indexOf(page) % palette.length];
  const sh = "#000000";
  return (
    <div
      style={{
        position: "absolute",
        top: y(page.startMs),
        left: 40,
        right: 40,
        display: "flex",
        justifyContent: "center",
        transform: `translateY(-50%) scale(${0.7 + raw * 0.3})`,
      }}
    >
      <span
        style={{
          fontFamily: "'Bangers', cursive",
          fontSize: fontSize ?? 84,
          color,
          textShadow: `4px 4px 0 ${sh}, -4px -4px 0 ${sh}, 4px -4px 0 ${sh}, -4px 4px 0 ${sh}`,
          textAlign: "center",
          lineHeight: 1.0,
          textTransform: "uppercase",
        }}
      >
        {page.text.trim().toUpperCase()}
      </span>
    </div>
  );
};
