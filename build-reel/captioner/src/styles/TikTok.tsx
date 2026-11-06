import { makeTransform, scale, translateY } from "@remotion/animation-utils";
import { fitText } from "@remotion/layout-utils";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { usePages } from "../usePages";
import type { StyleProps } from "../types";

// Adapted from remotion-dev/template-tiktok (Page.tsx + SubtitlePage.tsx):
// thick stroked text, spring entrance, active word in the highlight color.
export const TikTokCaptions: React.FC<StyleProps> = ({ captions, breakAfter, y, accent, uppercase, combineMs, fontSize }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const ms = (frame / fps) * 1000;
  const pages = usePages(captions, combineMs ?? 1200, breakAfter);
  const page = pages.find((p) => ms >= p.startMs && ms < p.startMs + p.durationMs);
  if (!page) return null;
  const enter = spring({
    frame: frame - Math.floor((page.startMs / 1000) * fps),
    fps,
    config: { damping: 200 },
    durationInFrames: 5,
  });
  const fitted = fitText({
    fontFamily: "TheBoldFont",
    text: page.text,
    withinWidth: width * 0.84,
    // TheBoldFont only has capitals, so measure as uppercase whatever is shown
    textTransform: "uppercase",
  });
  const size = Math.min(fontSize ?? 100, fitted.fontSize);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: y(page.startMs),
        transform: "translateY(-50%)",
        display: "flex",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          fontSize: size,
          color: "white",
          WebkitTextStroke: `${Math.round(size / 6)}px black`,
          paintOrder: "stroke",
          fontFamily: "TheBoldFont",
          textTransform: uppercase ? "uppercase" : undefined,
          textAlign: "center",
          transform: makeTransform([
            scale(interpolate(enter, [0, 1], [0.8, 1])),
            translateY(interpolate(enter, [0, 1], [50, 0])),
          ]),
        }}
      >
        {page.tokens.map((t, i) => {
          const active = t.fromMs <= ms && t.toMs > ms;
          return (
            <span key={`${t.fromMs}-${i}`} style={{ whiteSpace: "pre", color: active ? accent : "white" }}>
              {t.text}
            </span>
          );
        })}
      </div>
    </div>
  );
};
