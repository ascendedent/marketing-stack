import { Composition } from "remotion";
import { Captioned } from "./Captioned";
import { CaptionedPropsSchema } from "./types";

export const Root: React.FC = () => (
  <Composition
    id="Captioned"
    component={Captioned}
    schema={CaptionedPropsSchema}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={300}
    defaultProps={{
      videoSrc: "",
      captions: [],
      zones: [],
      style: "tiktok" as const,
      accent: "#FFB020",
      uppercase: false,
      combineMs: null,
      breakAfter: [],
      fontSize: null,
      durationInSeconds: 10,
      fps: 30,
      width: 1080,
      height: 1920,
    }}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, Math.round(props.durationInSeconds * props.fps)),
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
