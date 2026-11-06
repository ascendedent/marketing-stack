import { z } from "zod";

export const CaptionSchema = z.object({
  text: z.string(),
  startMs: z.number(),
  endMs: z.number(),
  timestampMs: z.number().nullable(),
  confidence: z.number().nullable(),
});

// Vertical center of the caption block (px) for a time range. build-reel
// moves captions per beat so they sit under the footage, never on it.
export const ZoneSchema = z.object({ startMs: z.number(), endMs: z.number(), y: z.number() });

export const StyleName = z.enum(["tiktok", "bold", "bounce", "clean"]);

export const CaptionedPropsSchema = z.object({
  videoSrc: z.string(),
  captions: z.array(CaptionSchema),
  zones: z.array(ZoneSchema),
  style: StyleName,
  accent: z.string(),
  uppercase: z.boolean(),
  combineMs: z.number().nullable(),
  breakAfter: z.array(z.number()),
  fontSize: z.number().nullable(),
  durationInSeconds: z.number(),
  fps: z.number(),
  width: z.number(),
  height: z.number(),
});

export type CaptionedProps = z.infer<typeof CaptionedPropsSchema>;
export type Caption = z.infer<typeof CaptionSchema>;

export type StyleProps = {
  captions: Caption[];
  breakAfter: number[];
  y: (ms: number) => number;
  accent: string;
  uppercase: boolean;
  combineMs: number | null;
  fontSize: number | null;
};
