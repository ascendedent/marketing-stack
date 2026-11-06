# storyboard.yaml reference

Paths are relative to the storyboard file. `${VAR}` in login steps or actions is read from the environment or from `.env.reel` next to the storyboard.

## Top level

```yaml
title: Instant search            # output file is out/<slug>.mp4
voiceover: vo.wav                # required; the timeline
repo: ../my-app                  # git repo, needed for branch targets and code beats
viewport: desktop                # desktop | laptop | mobile | tall (1080x1920 desktop) | {width, height, dpr, mobile}
frame: framed                    # framed (app in a window on the background) | full (app fills the 9:16 frame)
color_scheme: light              # light | dark (what the app is told)
extend: 0.5                      # seconds of video after the VO ends (outro breathing room)
vo_offset: 0                     # delay the VO start by N seconds
music: bed.mp3                   # optional, looped, auto-ducked under the voice
music_volume: 0.18
max_speed: 2.2                   # fastest a take may be sped up to fit its line
whisper: true                    # false skips transcription and uses pause detection
whisper_model: base.en           # any faster-whisper model (small.en is more accurate)
canvas: { width: 1080, height: 1920, fps: 30 }

style:
  bg: "#0E1116"                  # background gradient top
  bg2: "#1A2130"                 # background gradient bottom
  accent: "#FFB020"              # caption highlight, click ripples, chips
  text: "#FFFFFF"
  muted: "#9AA4B2"
  before: "#E5484D"              # BEFORE chip color
  after: "#30A46C"               # AFTER chip color
  font_bold: /path/to/Font-Bold.ttf   # optional; defaults to Inter, then Noto/DejaVu
  mono: /path/to/Mono.ttf
  logo: logo.png                 # optional, small at the top center
  cursor: { show: true, clicks: true, size: 1.0 }
                                 # pointer and click ripples; `cursor: false` hides both.
                                 # drawn at the UI's own scale; size multiplies it
  captions: { style: tiktok, uppercase: false }
                                 # style: tiktok | bold | bounce | clean (Remotion, see caption-styles.md)
                                 #        pill | lines | off (built in, no Node needed)
                                 # combine_ms: 200 to 1500 (words per page), size: font px override
```

## Targets

A target is one running version of the app. Most reels have `before` and `after`.

```yaml
targets:
  before:
    branch: main                 # checked out as a detached worktree in .reel/worktrees/before
    port: 3001
    start: "npm run dev -- --port {port}"   # {port} is substituted; PORT is also set in env
    install: "npm ci"            # optional, runs once per worktree
    copy: [".env.local"]         # untracked files to copy from repo (default: .env, .env.local, .env.development, .env.development.local)
    dir: apps/web                # optional subfolder to run in (monorepos)
    env: { NEXT_TELEMETRY_DISABLED: "1" }
    ready_path: /login           # polled until it answers (default /)
    ready_timeout: 180
    label: Before                # chip text (default: the target name)
    color: "#E5484D"
  after:
    branch: feature/new-search
    port: 3002
    start: "npm run dev -- --port {port}"
  live:
    url: https://staging.myapp.com   # url only: assumed already running, no worktree
```

`branch: "@worktree"` runs the repo folder as it is, uncommitted changes included.

## App settings

```yaml
app:
  login:
    url: /login
    steps:
      - fill: { selector: "#email", value: "${DEMO_EMAIL}" }
      - fill: { selector: "#password", value: "${DEMO_PASSWORD}" }
      - click: "button[type=submit]"
    done: { url: "**/dashboard" }     # or a selector, or { text: "Welcome" }
  hide: ["#__next-build-watcher", ".cookie-banner", "[data-sonner-toaster]"]
  timeout_ms: 15000
```

## Frame styles

| style | storyboard | result |
|---|---|---|
| Framed | `frame: framed`, `viewport: desktop` | browser window on the background, heading above, captions below |
| Full, desktop crop | `frame: full`, `viewport: desktop` | desktop layout fills the frame; a 9:16 crop follows the cursor (`zoom:` tightens it, default 1) |
| Full, tall desktop | `frame: full`, `viewport: tall` | the browser is 1080x1920, so the whole page fills the frame 1:1 |
| Full, mobile | `frame: full`, `viewport: mobile` | phone layout fills the frame |

With `frame: full`, headings are a pill over the footage, captions sit at y≈1380, compare `stack` splits the frame top/bottom and `side` left/right, and title and code beats keep the background.

## Beats

Every beat has `id`, `type`, and `say` (the exact VO words it covers). Optional on any beat: `at` (start second, overrides alignment), `heading` (text above the footage), `caption` (caption text if different from `say`), `captions: false`.

### title
```yaml
- id: hook
  type: title
  kicker: Build log              # small pill above
  text: Search went from 4 steps to 0
  subtitle: optional smaller line
  say: I rebuilt search in our campaign dashboard.
```

### app (one target)
```yaml
- id: instant
  type: app
  target: after
  start: /dashboard              # loaded before recording starts
  setup: [ { click: "#menu" } ]  # optional, unrecorded prep
  viewport: mobile               # optional per-beat override
  camera: window                 # window (whole UI in a browser frame) | follow (zoomed crop tracking the cursor)
  zoom: 1.8                      # follow camera magnification
  frame: full                    # optional per-beat override of the top-level frame
  cursor: false                  # optional per-beat override of style.cursor
  label: true                    # show the target's chip (or a string)
  lead_ms: 350                   # idle before the first action
  tail_ms: 600                   # idle after the last action
  max_speed: 2.5
  say: Now you just start typing.
  actions: [ ... ]
```

### compare (before and after)
```yaml
- id: before-after
  type: compare
  targets: [before, after]       # default
  layout: sequence               # sequence | stack (desktop default) | side (mobile default)
  split: 0.55                    # sequence only: share of the line given to "before"
  start: /dashboard              # or { before: /old-path, after: /new-path }
  say: Before, it took four clicks. Now it takes none.
  actions:                       # a shared list, or per target:
    before: [ { click: "#filters" }, { type: { selector: "#q", text: "fire" } }, { click: "#apply" } ]
    after:  [ { type: { selector: "[data-testid=search]", text: "fire" } } ]
```

### code
```yaml
- id: code
  type: code
  heading: The diff
  diff: { file: src/search.ts, from: before, to: after, context: 1, max_lines: 28, hunks: [1, 2] }
  # from/to are target names (their branches) or any git ref; to: "@worktree" for uncommitted
  # or a snippet instead:
  # snippet: { file: src/search.ts, ref: after, lines: "10-40", highlight: "18-22" }
  font_size: 26
  theme: github-dark             # any Pygments style
  say: The whole change was about thirty lines.
```

### clip (existing footage)
```yaml
- id: session
  type: clip
  file: footage/claude-session.mp4   # editor/terminal capture, OBS, a session replay
  trim: [12.0, 30.5]             # optional seconds
  fit: window                    # window (framed) | fill (full screen crop); default fill when frame: full
  say: Claude wrote the migration while I reviewed.
```

## Actions

| action | example | notes |
|---|---|---|
| goto | `goto: /settings` | relative to the target URL |
| click | `click: "#save"` or `click: { selector: ".row", text: "Fire", nth: 0 }` | cursor glides there, click ripple |
| type | `type: { selector: "#q", text: "fire", delay: 70, enter: true }` | human-paced typing; `clear: false` to append |
| fill | `fill: { selector: "#q", value: "x" }` | instant (setup or login) |
| press | `press: Enter` | any Playwright key name |
| hover | `hover: ".card"` | moves the cursor and holds (`hold` ms) |
| scroll | `scroll: 600` or `scroll: { by: 800, duration: 1200, in: ".panel" }` or `scroll: { to: "#pricing" }` | eased |
| wait | `wait: 800` | ms |
| waitFor | `waitFor: ".toast"` or `waitFor: { text: "Saved" }` or `waitFor: { url: "**/done" }` | |
| focus | `focus: { selector: "#chart", scale: 1.7, hold: 1600 }` | zoom punch-in at compose time |
| select | `select: { selector: "#plan", value: "pro" }` | |
| cursor | `cursor: { x: 0.5, y: 0.8 }` | park the cursor (fractions of the viewport) |
| speed | `speed: 1.5` | everything after this runs faster (or slower) |
| eval | `eval: "localStorage.clear()"` | escape hatch |

Selectors are Playwright selectors: CSS, `text=...`, `:has-text()`, `[data-testid=...]`. Use `reel inspect` to find them.
