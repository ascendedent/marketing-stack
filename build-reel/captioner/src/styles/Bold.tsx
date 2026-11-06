import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import { usePages } from "../usePages";
import type { StyleProps } from "../types";

// From claude-shorts BoldCaptions: Montserrat 800, all caps, pop-in spring,
// active word highlighted (accent replaces the original fixed yellow).
export const BoldCaptions: React.FC<StyleProps> = ({ captions, breakAfter, y, accent, combineMs, fontSize }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const pages = usePages(captions, combineMs ?? 800, breakAfter);
  const page = pages.find((p) => ms >= p.startMs && ms < p.startMs + p.durationMs);
  if (!page) return null;
  const s = spring({
    frame: frame - Math.floor((page.startMs / 1000) * fps),
    fps,
    config: { mass: 1, damping: 12, stiffness: 200 },
  });
  const shadow = "#000000";
  return (
    <div
      style={{
        position: "absolute",
        top: y(page.startMs),
        left: 40,
        right: 40,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 12,
        transform: `translateY(-50%) scale(${s})`,
      }}
    >
      {page.tokens.map((t, i) => {
        const active = ms >= t.fromMs && ms < t.toMs;
        return (
          <span
            key={`${page.startMs}-${i}`}
            style={{
              fontFamily: "'Montserrat', sans-serif",
              fontWeight: 800,
              fontSize: fontSize ?? 72,
              textTransform: "uppercase",
              color: active ? accent : "#FFFFFF",
              textShadow: `3px 3px 0 ${shadow}, -3px -3px 0 ${shadow}, 3px -3px 0 ${shadow}, -3px 3px 0 ${shadow}`,
              lineHeight: 1.1,
              textAlign: "center",
            }}
          >
            {t.text.trim().toUpperCase()}
          </span>
        );
      })}
    </div>
  );
};
