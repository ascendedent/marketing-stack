import { useCallback, useEffect, useState } from "react";
import { AbsoluteFill, OffthreadVideo, continueRender, delayRender } from "remotion";
import { loadFonts } from "./fonts";
import { BoldCaptions } from "./styles/Bold";
import { BounceCaptions } from "./styles/Bounce";
import { CleanCaptions } from "./styles/Clean";
import { TikTokCaptions } from "./styles/TikTok";
import type { CaptionedProps } from "./types";

const STYLES = { tiktok: TikTokCaptions, bold: BoldCaptions, bounce: BounceCaptions, clean: CleanCaptions };

export const Captioned: React.FC<CaptionedProps> = (p) => {
  // Captions are measured with fitText, so hold every frame until fonts are in.
  const [ready, setReady] = useState(false);
  const [handle] = useState(() => delayRender("Loading caption fonts"));
  useEffect(() => {
    loadFonts()
      .catch((e) => console.error(e))
      .finally(() => {
        setReady(true);
        continueRender(handle);
      });
  }, [handle]);
  const { zones, height } = p;
  const y = useCallback(
    (ms: number) => {
      const z = zones.find((zz) => ms >= zz.startMs && ms < zz.endMs) ?? zones[zones.length - 1];
      return z ? z.y : height * 0.75;
    },
    [zones, height],
  );
  const Style = STYLES[p.style] ?? TikTokCaptions;
  return (
    <AbsoluteFill style={{ backgroundColor: "black" }}>
      <OffthreadVideo src={p.videoSrc} style={{ width: "100%", height: "100%" }} />
      {ready && (
      <Style
        captions={p.captions}
        breakAfter={p.breakAfter}
        y={y}
        accent={p.accent}
        uppercase={p.uppercase}
        combineMs={p.combineMs}
        fontSize={p.fontSize}
      />
      )}
    </AbsoluteFill>
  );
};
