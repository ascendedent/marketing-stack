#!/usr/bin/env node
/**
 * Burns animated captions onto a build-reel base render.
 *
 *   node render.mjs --job /path/to/caption-job.json
 *
 * The job JSON holds the composition props (see src/types.ts) plus
 * `video` (local path of the base MP4) and `out` (output MP4 path).
 * Pattern from claude-shorts render.mjs: serve the clip over local HTTP
 * (Remotion's renderer reads http URLs), bundle once, selectComposition to
 * resolve calculateMetadata, then renderMedia.
 */
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import crypto from "crypto";
import fs from "fs";
import http from "http";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const arg = (name) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : undefined;
};

const jobPath = arg("job");
if (!jobPath) {
  console.error("usage: node render.mjs --job job.json");
  process.exit(1);
}
const job = JSON.parse(fs.readFileSync(jobPath, "utf-8"));
const videoPath = path.resolve(job.video);
if (!fs.existsSync(videoPath)) {
  console.error(`base video not found: ${videoPath}`);
  process.exit(1);
}

// Serve the base video (with range support so the renderer can seek).
const server = http.createServer((req, res) => {
  const stat = fs.statSync(videoPath);
  const range = req.headers.range;
  if (range) {
    const [s, e] = range.replace(/bytes=/, "").split("-");
    const start = parseInt(s, 10);
    const end = e ? parseInt(e, 10) : stat.size - 1;
    res.writeHead(206, {
      "Content-Range": `bytes ${start}-${end}/${stat.size}`,
      "Accept-Ranges": "bytes",
      "Content-Length": end - start + 1,
      "Content-Type": "video/mp4",
    });
    fs.createReadStream(videoPath, { start, end }).pipe(res);
  } else {
    res.writeHead(200, { "Content-Length": stat.size, "Content-Type": "video/mp4", "Accept-Ranges": "bytes" });
    fs.createReadStream(videoPath).pipe(res);
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const videoSrc = `http://127.0.0.1:${server.address().port}/base.mp4`;

// Bundle once and cache it next to the job, keyed by the source files.
const srcDir = path.join(__dirname, "src");
const hash = crypto.createHash("sha1");
for (const f of fs.readdirSync(srcDir, { recursive: true }).sort()) {
  const p = path.join(srcDir, f);
  if (fs.statSync(p).isFile()) hash.update(f).update(fs.readFileSync(p));
}
const key = hash.digest("hex").slice(0, 12);
const cacheRoot = job.bundleCache || path.join(__dirname, ".bundle-cache");
const bundleDir = path.join(cacheRoot, key);
let serveUrl = bundleDir;
if (!fs.existsSync(path.join(bundleDir, "index.html"))) {
  process.stdout.write("bundling captioner... ");
  const t0 = Date.now();
  serveUrl = await bundle({ entryPoint: path.join(srcDir, "index.ts"), outDir: bundleDir });
  console.log(`${((Date.now() - t0) / 1000).toFixed(1)}s`);
}

const inputProps = {
  videoSrc,
  captions: job.captions,
  zones: job.zones,
  style: job.style,
  accent: job.accent,
  uppercase: job.uppercase,
  combineMs: job.combineMs ?? null,
  breakAfter: job.breakAfter ?? [],
  fontSize: job.fontSize ?? null,
  durationInSeconds: job.durationInSeconds,
  fps: job.fps,
  width: job.width,
  height: job.height,
};

const browserExecutable = process.env.REEL_CHROME || job.browserExecutable || null;
const chromiumOptions = { gl: "swangle" };

try {
  const composition = await selectComposition({
    serveUrl,
    id: "Captioned",
    inputProps,
    browserExecutable,
    chromiumOptions,
  });
  let last = -1;
  await renderMedia({
    composition,
    serveUrl,
    codec: "h264",
    crf: job.crf ?? 18,
    x264Preset: job.x264Preset ?? "veryfast",
    audioCodec: "aac",
    audioBitrate: "192k",
    outputLocation: path.resolve(job.out),
    inputProps,
    browserExecutable,
    chromiumOptions,
    concurrency: job.concurrency ?? null,
    scale: job.scale ?? 1,
    onProgress: ({ progress }) => {
      const pct = Math.floor(progress * 10) * 10;
      if (pct !== last) {
        last = pct;
        console.log(`  captions ${pct}%`);
      }
    },
  });
  console.log(`captioned: ${job.out}`);
} finally {
  server.close();
}
