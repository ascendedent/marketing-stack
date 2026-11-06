import { useMemo } from "react";
import { createTikTokStyleCaptions, type TikTokPage } from "@remotion/captions";
import type { Caption } from "./types";

// From claude-shorts useCaptionPages: groups word captions into pages with
// @remotion/captions createTikTokStyleCaptions(). build-reel adds hard breaks
// (sentence ends, beat cuts) so a page never straddles two lines of the script.
export const usePages = (captions: Caption[], combineMs: number, breakAfter: number[] = []) =>
  useMemo(() => {
    if (!captions?.length) return [] as TikTokPage[];
    const cuts = [...new Set(breakAfter)].filter((i) => i >= 0 && i < captions.length - 1).sort((a, b) => a - b);
    const pages: TikTokPage[] = [];
    let from = 0;
    for (const end of [...cuts, captions.length - 1]) {
      const chunk = captions.slice(from, end + 1).map((c, i) =>
        i === 0 ? { ...c, text: c.text.replace(/^\s+/, "") } : c,
      );
      if (chunk.length) {
        pages.push(...createTikTokStyleCaptions({ captions: chunk, combineTokensWithinMilliseconds: combineMs }).pages);
      }
      from = end + 1;
    }
    return pages;
  }, [captions, combineMs, breakAfter]);
