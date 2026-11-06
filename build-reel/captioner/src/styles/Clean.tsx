import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { usePages } from "../usePages";
import type { StyleProps } from "../types";

// From claude-shorts CleanCaptions: Inter Bold, 3 to 5 words per page,
// six-frame fade in, soft shadow. Good for professional or calmer content.
export const CleanCaptions: React.FC<StyleProps> = ({ captions, breakAfter, y, uppercase, combineMs, fontSize }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const pages = usePages(captions, combineMs ?? 1500, breakAfter);
  const page = pages.find((p) => ms >= p.startMs && ms < p.startMs + p.durationMs);
  if (!page) return null;
  const local = frame - Math.floor((page.startMs / 1000) * fps);
  const opacity = interpolate(local, [0, 6], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div
      style={{
        position: "absolute",
        top: y(page.startMs),
        left: 60,
        right: 60,
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        transform: "translateY(-50%)",
        opacity,
      }}
    >
      {page.tokens.map((t, i) => {
        const active = ms >= t.fromMs && ms < t.toMs;
        return (
          <span
            key={`${page.startMs}-${i}`}
            style={{
              fontFamily: "'Inter', sans-serif",
              fontWeight: 700,
              fontSize: fontSize ?? 58,
              color: active ? "#FFFFFF" : "rgba(255,255,255,0.82)",
              textShadow: "2px 2px 8px rgba(0, 0, 0, 0.6)",
              textTransform: uppercase ? "uppercase" : undefined,
              lineHeight: 1.3,
              textAlign: "center",
              marginRight: 12,
            }}
          >
            {t.text.trim()}
          </span>
        );
      })}
    </div>
  );
};
