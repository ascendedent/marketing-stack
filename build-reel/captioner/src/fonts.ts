import { staticFile } from "remotion";

// Fonts: Montserrat, Bangers, Inter (from claude-shorts, OFL) and TheBoldFont
// (from Remotion's official TikTok template).
const FONTS = [
  { family: "Montserrat", file: "fonts/Montserrat-Bold.ttf", weight: "800" },
  { family: "Bangers", file: "fonts/Bangers-Regular.ttf", weight: "400" },
  { family: "Inter", file: "fonts/Inter-Bold.ttf", weight: "700" },
  { family: "TheBoldFont", file: "fonts/TheBoldFont.ttf", weight: "400" },
];

let pending: Promise<void> | null = null;

export const loadFonts = (): Promise<void> => {
  if (!pending) {
    pending = Promise.all(
      FONTS.map(async (f) => {
        const face = new FontFace(f.family, `url('${staticFile(f.file)}') format('truetype')`, { weight: f.weight });
        await face.load();
        document.fonts.add(face);
      }),
    ).then(() => undefined);
  }
  return pending;
};
