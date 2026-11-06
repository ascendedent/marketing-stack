---
name: build-reel
description: Turns a script or storyboard plus a recorded voiceover into a vertical 9:16 build-in-public video of a web app. It records real feature walkthroughs, before/after comparisons across git branches, and code diffs, then cuts them to the voiceover with captions, either rendered locally or handed to Descript as an editable project. Use when asked for a build video, feature reel, before/after demo, changelog video, or short-form app content from a voiceover.
---

# build-reel

You get a voiceover file and a script or storyboard. You produce a captioned 1080x1920 MP4 in which every beat of the voiceover is covered by real footage of the app: a feature walkthrough, a before/after across two branches, or the code diff that made the change.

Everything runs locally through one CLI: `SKILL_DIR/scripts/reel` (SKILL_DIR is the folder this file is in). Run `SKILL_DIR/scripts/preflight.sh` once per machine first. It sets up a private venv, installs the Remotion caption renderer (needs Node 20+), and checks ffmpeg, fonts and the browser on Fedora.

What is borrowed and from where: captions are rendered by Remotion's own `@remotion/captions` with styles taken from Remotion's official TikTok template and from claude-shorts (`captioner/`); caption, platform and pacing references come from claude-shorts and iart-ai/tiktok-video-skills (`references/`). Recording, alignment and layout are build-reel's own, on Playwright, faster-whisper, Pillow and ffmpeg.

## Companion skills (use them when installed)

The script and the hook decide whether anyone watches; footage only carries them. If these skills are installed, use them before writing the storyboard. If they are not, mention once that they can be added (commands below) and carry on.

- `hook-writer`: the first line and first 3 seconds. Give the user 3 hook options before locking the script, unless they handed you a final script and VO.
- `short-form-video-script`: beat structure, retention, and the ending (loop or CTA).
- `behind-the-scenes-and-founder`: build-in-public framing (real specifics and stakes, what is safe to reveal).
- `before-after-and-transformation`: honest before/after framing for compare beats.
- `trend-jacking` and `viral-reverse-engineering`: when the user names a trend or a reference video to match. Never invent trend data; ask for the reference or work from what is observable.
- `platform-specs-and-validation`: final checks per platform (length, safe zones, cover frame).

For route B, also install Descript's official plugin (`/plugin marketplace add descriptinc/descript-mcp`, then `/plugin install descript@descript`). Optional: `alexaiarchitect/descript-skills` for token-based scripting with cost gates.

Install (in Claude Code):
```
/plugin marketplace add social-media-skills/skills
/plugin install social-media-skills@social-media-skills
/plugin marketplace add iart-ai/tiktok-video-skills
/plugin install tiktok-video-skills@tiktok-video-skills
```
When the user already recorded the VO, these skills inform the visuals (hook card text, what each beat shows, caption style), not a rewrite of the script.

## Routes (pick one per video; ask if the user hasn't said)

Steps 1 to 7 of the workflow (storyboard, servers, login, record, align) are the same for every route. They differ in who finishes the video.

| Route | Finish | Choose it when |
|---|---|---|
| **A. Local render** (default) | `reel compose`: captions burned in with Remotion, MP4 in `out/` | the user wants a finished file with no further editing; fastest, free, fully repeatable |
| **B. Descript** | `reel export`, then import as a Descript project (each beat a clip carrying its slice of the VO, end to end on a 1080x1920 composition); optional Underlord caption pass; the user polishes and publishes in Descript | the user wants hands-on control: trim by editing the transcript, swap clips, Descript captions and brand kit, Studio Sound, publish links |
| **C. Any editor** | `reel export`, then hand over the package folder | CapCut web, DaVinci Resolve, Kdenlive: clips, raw takes, VO, SRT and plan are all there |

Route B setup and step-by-step: `references/descript.md`. In short:
- **MCP (preferred when connected):** official plugin `descript@descript`. Call `import_media` with `out/<slug>-package/descript-import.json` (drop each `local_path`), save the returned `upload_urls` to `out/<slug>-package/upload_urls.json`, run `reel descript-put STORYBOARD --urls out/<slug>-package/upload_urls.json`, then `wait_for_job`. Show the user the `project_url`. Delete `upload_urls.json` afterwards (signed links).
- **REST token:** `DESCRIPT_TOKEN` in `.env.reel`, then `reel descript STORYBOARD` (add `--dry-run` to see the payload first).
- **Underlord polish** spends AI credits: confirm first, then `prompt_project_agent` with `underlord-prompt.md` (MCP) or `reel descript-polish STORYBOARD --yes` (token). Never publish without the user's explicit yes.
- Uploads go straight from this machine to Descript's storage. A proxy that blocks storage.googleapis.com breaks them; `reel descript-put` names the failed files so you can `report_upload_status` and retry.

## Inputs to collect (ask once, briefly)

1. **Voiceover file** (wav/mp3/m4a). This is the clock. Video is cut to it; it is never stretched.
2. **Script.** The exact words in the VO, split into lines. If only a storyboard is given, ask for the script or transcribe it (`reel align` prints the transcript when faster-whisper is installed).
3. **Repo path and branches.** For before/after, which branch is "before" and which is "after", and the dev server command (e.g. `npm run dev -- --port {port}`). Ask whether the after branch runs database migrations: both branches share one dev database, so a migration can break the before branch.
4. **Test account.** Email and password go in `.env.reel` next to the storyboard, never in the storyboard and never echoed back. Example:
   ```
   DEMO_EMAIL=test@yourapp.dev
   DEMO_PASSWORD=...
   ```
   Make sure `.env.reel` and `.reel/` are gitignored if the project folder is a repo.
5. **Video style.** Always ask this at the start of a new build (one AskUserQuestion), unless the user already said or the storyboard already sets `frame:`/`viewport:`. It sets top-level `frame:` and `viewport:`:
   - **Framed** (`frame: framed`, `viewport: desktop`): the app in a browser window on the branded background, heading above, captions below. Shows the whole UI; it is small on a phone, so lean on `focus:`.
   - **Full screen, desktop crop** (`frame: full`, `viewport: desktop`): the app fills the whole 9:16 frame with the desktop layout; the camera is a 9:16 crop that follows the cursor (`zoom:` to go tighter). Big and readable, shows part of the page at a time.
   - **Full screen, tall desktop** (`frame: full`, `viewport: tall`): the browser itself is 1080x1920, so the whole page fills the frame at 1:1 in its desktop layout (if the app's breakpoints allow 1080 px). Everything visible, text small.
   - **Full screen, mobile** (`frame: full`, `viewport: mobile`): the phone layout fills the frame. Most readable; needs a responsive app.
   In full-screen styles headings become a pill over the footage, captions sit at y≈1380, and code/title beats keep the background. A beat can override with its own `frame:` or `viewport:`.
6. **Cursor and clicks.** Ask in the same question set: pointer and click ripples (default), pointer only, clicks only, or neither. Sets `style.cursor` (`{show, clicks, size}`, or `false` for neither). The pointer is drawn at the UI's own scale; `size: 1.2` makes it a bit bigger.

Do not ask about anything else. Pick sensible defaults and say what you picked.

## Workflow

Work in a project folder, e.g. `reels/<topic>/`, holding `storyboard.yaml`, the VO file and `.env.reel`.

1. **Write the storyboard** (`references/storyboard.md` has the full format; `examples/storyboard.example.yaml` is a complete one). One beat per script line or idea. Each beat's `say:` is the exact VO text it covers; this is how it gets timed.
2. `reel check storyboard.yaml`. Fix every problem it lists.
3. `reel up storyboard.yaml`. This creates a detached git worktree per branch under `.reel/worktrees/`, copies untracked `.env*` files in, runs `install` once, and starts each dev server on its port.
4. `reel login storyboard.yaml`. This signs in with the test account on every target and saves the session, so recordings start logged in.
5. **Find real selectors before writing actions.** Run `reel inspect storyboard.yaml --target after --path /some/page`. It lists every clickable element with a unique selector and saves a screenshot to look at. Never guess selectors.
6. `reel record storyboard.yaml` (or `--beat <id>` to redo one). Then check each take with `reel take storyboard.yaml --beat <id> --target <t>` and look at the PNG it writes. If an action failed, the error names the step and saves `failed.png` in the take folder.
7. `reel align storyboard.yaml`. Read the table it prints. With faster-whisper it is word-accurate. Without it, beats are placed by word count and snapped to pauses, so check every start time. Fix any beat with `at: <seconds>`.
8. `reel compose storyboard.yaml --draft` (half size, a few seconds). Then `reel sheet storyboard.yaml` and **look at the contact sheet**. Check that each beat shows what its line says, nothing important is cropped, captions don't cover the action, and no beat's report says `! cut`.
9. Fix and repeat only what is needed: a bad take means `record --beat`; wrong timing means `at:` then `align`; a framing issue just needs another compose. Then do the final `reel compose storyboard.yaml` (no `--draft`).
10. `reel down storyboard.yaml` stops the servers (`--clean` also removes the worktrees).
11. Deliver `out/<title>.mp4` with one line per beat saying what it shows, and flag anything you compromised on. For route B or C, run `reel export STORYBOARD` instead of the final compose and continue as in Routes above.

`reel render storyboard.yaml` runs steps 6 to 8 in one go (recording only missing takes) once the storyboard is proven.

## Directing rules (what makes these good)

- **The VO decides length.** If a take is longer than its line, the compositor first squeezes idle moments (nothing moving), then speeds up to `max_speed` (default 2.2x). Past that, it cuts the end and the report shows `! cut`. Fix that by trimming actions, splitting the beat, or giving the beat more VO. Never stretch footage slower than real time; shorter takes hold their last frame.
- **One idea per beat, 2 to 6 seconds.** Short-form attention resets at every cut.
- **Make it readable on a phone.** Desktop UIs are small in a vertical frame. A full-screen style (`frame: full`) helps most; otherwise use `focus:` on the element that matters (a zoom punch-in applied at compose time), `camera: follow` for beats about a small area, or `viewport: mobile` if the app is responsive. Focus on a specific element, not a whole page: the zoom never crops the focused element, so focusing on something wide means little zoom.
- **Before/after:** use a `compare` beat. `layout: sequence` shows before, then a flash, then after (best for flows); `stack` (desktop) or `side` (mobile) plays both at once (best when the difference is visual). If the UI differs between branches, give per-target `actions: {before: [...], after: [...]}`.
- **Code beats:** a `diff` between the two branch targets types the added lines in as the VO plays. Keep it short with `context: 1` and `max_lines` around 20 to 30, and point it at the one file that tells the story. For editor or terminal footage you already have (a screen recording, a Claude Code session replay), use a `clip` beat.
- **Start each take on a settled page.** Use `start:` (and `setup:` for unrecorded prep like opening a menu), so recording begins after load, not during it.
- **Hide dev noise.** Add selectors for dev overlays, cookie banners and toasts to `app.hide`.
- **Caption style** (`style.captions.style`, details in `references/caption-styles.md`):
  - `tiktok` (default): the most native look on TikTok and Reels; good for build-in-public and demos.
  - `bold`: punchy all-caps for business, education and tips.
  - `bounce`: high energy, 1 to 2 words at a time; for playful launches.
  - `clean`: calm and professional; for B2B, investor or LinkedIn cuts.
  - `pill`: built in, no Node needed.
  Match the energy of the voiceover, and keep one style per channel so the series looks consistent.
- **Captions** use the script's spelling with the voiceover's timing, so product names stay correct. Set `caption:` on a beat to show different text than `say:`, or `captions: false` to hide them for that beat.
- **Safe zones.** Layouts keep content between roughly y=150 and y=1500, clear of the platform UI on Reels, TikTok and Shorts (`references/platform-specs.md`). Don't move captions lower.
- **Pacing.** Read `references/retention-pacing.md` before planning beats for a script you are writing: hook in the first second, a visual change every 2 to 4 seconds, and a reason to keep watching before each cut.

## Troubleshooting

- *Browser won't launch on Fedora:* re-run `preflight.sh`; it installs Playwright's Chromium and falls back to Google Chrome if that's installed.
- *Whisper model download fails:* alignment falls back to pause detection automatically. Set `whisper: false` in the storyboard to skip it.
- *Login lands on the wrong page:* add `done: { url: "**/dashboard" }` (or a selector) to `app.login` so it waits for the post-login page, then run `reel login --headed` to watch it.
- *Server not ready:* check `.reel/logs/server-<target>.log`; set `ready_path` and `ready_timeout` on the target.
- *Output is MPEG-4 or blurry:* Fedora's `ffmpeg-free` lacks libx264. Preflight prints the RPM Fusion swap command. (Remotion caption renders use Remotion's own bundled encoder, so they are fine either way.)
- *Caption render fails to launch a browser:* run `cd SKILL_DIR/captioner && npx remotion browser ensure`, or set `REEL_CHROME=/usr/bin/google-chrome` to use your installed Chrome.
- *Caption renders feel slow:* they take roughly 2 to 4 times the video length on a laptop. Use `--draft` while iterating; the final render only needs to happen once.
