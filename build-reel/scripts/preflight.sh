#!/usr/bin/env bash
# Sets up and checks everything build-reel needs on Fedora (works on other
# Linux too). Safe to re-run. Creates a private venv inside the skill folder.
set -uo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$SKILL_DIR/.venv"
ok=1
say() { printf '%s\n' "$*"; }
need() { say "  MISSING: $*"; ok=0; }

say "build-reel preflight ($SKILL_DIR)"

# --- system tools ---
command -v python3 >/dev/null || need "python3   -> sudo dnf install python3"
command -v git >/dev/null || need "git       -> sudo dnf install git"
if command -v ffmpeg >/dev/null; then
  enc=$(ffmpeg -hide_banner -encoders 2>/dev/null)
  if grep -q " libx264 " <<<"$enc"; then
    say "  ffmpeg: ok (libx264)"
  elif grep -q " libopenh264 " <<<"$enc"; then
    say "  ffmpeg: ok, using OpenH264 (Fedora's ffmpeg-free)."
    say "          For better quality and smaller files, switch to RPM Fusion's full build:"
    say "          sudo dnf install https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-\$(rpm -E %fedora).noarch.rpm"
    say "          sudo dnf swap ffmpeg-free ffmpeg --allowerasing"
  else
    say "  ffmpeg: no H.264 encoder found; output will fall back to MPEG-4. Install RPM Fusion ffmpeg (see above)."
  fi
else
  need "ffmpeg    -> sudo dnf install ffmpeg-free   (or RPM Fusion 'ffmpeg' for libx264)"
fi
command -v fc-match >/dev/null || need "fontconfig -> sudo dnf install fontconfig"
fonts=$(fc-list 2>/dev/null)
if ! grep -qiE "Inter|Noto Sans|DejaVu Sans" <<<"$fonts"; then
  need "a UI font -> sudo dnf install google-noto-sans-fonts dejavu-sans-mono-fonts (or rsms-inter-fonts)"
fi
grep -qi "Inter" <<<"$fonts" || say "  tip: sudo dnf install rsms-inter-fonts  for the default caption font"

# --- python venv ---
if [ ! -x "$VENV/bin/python" ]; then
  say "  creating venv at $VENV"
  python3 -m venv "$VENV" || { need "python3 venv (sudo dnf install python3-virtualenv)"; }
fi
if [ -x "$VENV/bin/python" ]; then
  "$VENV/bin/pip" install -q --upgrade pip >/dev/null 2>&1
  "$VENV/bin/pip" install -q playwright pyyaml pillow pygments || need "python packages (pip install failed)"
  if [ "${REEL_NO_WHISPER:-0}" != "1" ]; then
    "$VENV/bin/pip" install -q faster-whisper "av<19" >/dev/null 2>&1 \
      && say "  faster-whisper: ok (word-accurate VO alignment; model downloads on first use)" \
      || say "  faster-whisper: not installed; alignment will use pause detection"
  fi
  if ! "$VENV/bin/python" - <<'EOF' >/dev/null 2>&1
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    p.chromium.launch().close()
EOF
  then
    say "  installing Playwright Chromium..."
    "$VENV/bin/playwright" install chromium >/dev/null 2>&1 || true
    if ! "$VENV/bin/python" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p: p.chromium.launch().close()" >/dev/null 2>&1; then
      if command -v google-chrome >/dev/null || command -v google-chrome-stable >/dev/null; then
        say "  bundled Chromium failed; will fall back to your installed Google Chrome"
      else
        need "a browser Playwright can launch. Try: sudo dnf install nss atk at-spi2-atk cups-libs libdrm libxkbcommon mesa-libgbm alsa-lib pango"
      fi
    fi
  fi
  say "  python env: ok"
fi

# --- Remotion captioner (tiktok / bold / bounce / clean caption styles) ---
CAP="$SKILL_DIR/captioner"
if command -v node >/dev/null && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 20 ]; then
  if [ ! -d "$CAP/node_modules/@remotion/renderer" ]; then
    say "  installing the caption renderer (Remotion, pinned versions)..."
    (cd "$CAP" && npm ci --no-audit --no-fund --loglevel=error) || need "npm install in $CAP failed"
  fi
  if [ -d "$CAP/node_modules/@remotion/renderer" ]; then
    # Remotion renders with its own Chrome Headless Shell; fetch it now, not mid-render.
    (cd "$CAP" && npx --no-install remotion browser ensure >/dev/null 2>&1) \
      && say "  captioner: ok (Remotion + Chrome Headless Shell)" \
      || say "  captioner: installed, but the headless browser download failed. Set REEL_CHROME=/usr/bin/google-chrome to use your Chrome instead."
  fi
else
  say "  captioner: skipped (needs Node 20+: sudo dnf install nodejs). Built-in 'pill' captions will be used."
fi

chmod +x "$SKILL_DIR/scripts/reel" 2>/dev/null || true
if [ $ok = 1 ]; then
  say "ready. Run: $SKILL_DIR/scripts/reel --help"
else
  say "fix the MISSING items above, then run this again."
  exit 1
fi
