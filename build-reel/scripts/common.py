"""Shared helpers: storyboard loading, validation, env, fonts, ffmpeg."""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

BEAT_TYPES = {"title", "app", "compare", "code", "clip"}
FRAMES = {"framed", "full"}  # framed: app in a window on the background; full: app fills the 9:16 frame

DEFAULT_STYLE = {
    "bg": "#0E1116",
    "bg2": "#1A2130",
    "accent": "#FFB020",
    "text": "#FFFFFF",
    "muted": "#9AA4B2",
    "before": "#E5484D",
    "after": "#30A46C",
    "font": None,
    "font_bold": None,
    "mono": None,
    "logo": None,
    "captions": {
        "style": "tiktok",     # tiktok | bold | bounce | clean (Remotion) | pill | lines | off (built-in)
        "max_words": 3,        # built-in styles only
        "size": None,          # font size override (px at 1080 wide)
        "combine_ms": None,    # Remotion styles: how many ms of words share a page
        "uppercase": False,
    },
}

VIEWPORTS = {
    "desktop": {"width": 1280, "height": 800, "dpr": 1.5, "mobile": False},
    "laptop": {"width": 1440, "height": 900, "dpr": 1.333, "mobile": False},
    "mobile": {"width": 432, "height": 768, "dpr": 2.5, "mobile": True},
    # portrait desktop browser: exactly 1080x1920, so frame: full shows the whole page at 1:1
    "tall": {"width": 1080, "height": 1920, "dpr": 1.0, "mobile": False},
}


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(msg, flush=True)


def load_env_file(path):
    """Load KEY=VALUE lines into os.environ without overriding existing vars."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand_env(value):
    """Expand ${VAR} in strings, recursively through lists and dicts."""
    if isinstance(value, str):
        def rep(m):
            name = m.group(1)
            if name not in os.environ:
                die(f"environment variable {name} is not set (put it in .env.reel next to the storyboard)")
            return os.environ[name]
        return _ENV_RE.sub(rep, value)
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    return value


def env_refs(value, found=None):
    found = set() if found is None else found
    if isinstance(value, str):
        found.update(_ENV_RE.findall(value))
    elif isinstance(value, list):
        for v in value:
            env_refs(v, found)
    elif isinstance(value, dict):
        for v in value.values():
            env_refs(v, found)
    return found


def deep_merge(base, over):
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Storyboard:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.exists():
            die(f"storyboard not found: {self.path}")
        self.dir = self.path.parent
        load_env_file(self.dir / ".env.reel")
        self.data = yaml.safe_load(self.path.read_text()) or {}
        self.work = self.dir / ".reel"
        self.work.mkdir(exist_ok=True)
        d = self.data
        self.title = d.get("title", self.path.stem)
        canvas = d.get("canvas", {})
        self.width = int(canvas.get("width", 1080))
        self.height = int(canvas.get("height", 1920))
        self.fps = int(canvas.get("fps", 30))
        self.style = deep_merge(DEFAULT_STYLE, d.get("style", {}))
        self.viewport_default = d.get("viewport", "desktop")
        self.targets = d.get("targets", {}) or {}
        self.app = d.get("app", {}) or {}
        self.beats = d.get("beats", []) or []
        self.repo = self.resolve(d["repo"]) if d.get("repo") else None

    def resolve(self, p):
        if p is None:
            return None
        p = Path(os.path.expanduser(str(p)))
        return p if p.is_absolute() else (self.dir / p).resolve()

    @property
    def voiceover(self):
        return self.resolve(self.data.get("voiceover"))

    @property
    def slug(self):
        return re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-") or "reel"

    def target(self, name):
        if name not in self.targets:
            die(f"unknown target '{name}' (defined: {', '.join(self.targets) or 'none'})")
        t = dict(self.targets[name])
        port = t.get("port")
        url = t.get("url") or (f"http://localhost:{port}" if port else None)
        if not url:
            die(f"target '{name}' needs a url or a port")
        t["url"] = url.format(port=port).rstrip("/")
        t["name"] = name
        return t

    def viewport(self, beat=None):
        spec = (beat or {}).get("viewport", self.viewport_default)
        if isinstance(spec, str):
            if spec not in VIEWPORTS:
                die(f"unknown viewport '{spec}' (use {', '.join(VIEWPORTS)} or a {{width,height,dpr}} map)")
            vp = dict(VIEWPORTS[spec])
            vp["kind"] = spec
        else:
            vp = {"width": int(spec["width"]), "height": int(spec["height"]),
                  "dpr": float(spec.get("dpr", 1.5)), "mobile": bool(spec.get("mobile", False))}
            vp["kind"] = "mobile" if vp["width"] < vp["height"] else "desktop"
        return vp

    def frame(self, beat=None):
        """framed | full for a beat (beat 'frame:' overrides the top-level one)."""
        return (beat or {}).get("frame", self.data.get("frame", "framed"))

    def cursor(self, beat=None):
        """Cursor/click drawing for a beat: {show, clicks, size}.
        style.cursor (or a beat's cursor:) may be true/false or a partial map."""
        cfg = {"show": True, "clicks": True, "size": 1.0}
        for v in (self.style.get("cursor"), (beat or {}).get("cursor")):
            if isinstance(v, bool):
                cfg["show"] = cfg["clicks"] = v
            elif isinstance(v, dict):
                cfg.update(v)
        cfg["size"] = float(cfg.get("size") or 1.0)
        return cfg

    def beat_targets(self, beat):
        """Which targets a beat records against."""
        t = beat.get("type")
        if t == "app":
            name = beat.get("target") or (next(iter(self.targets)) if len(self.targets) == 1 else None)
            if not name:
                die(f"beat '{beat.get('id')}' needs a target")
            return [name]
        if t == "compare":
            return list(beat.get("targets") or ["before", "after"])
        return []

    def take_dir(self, beat_id, target):
        return self.work / "takes" / beat_id / target

    def auth_path(self, target):
        return self.work / "auth" / f"{target}.json"


def validate(sb):
    """Return a list of problems (strings). Empty list means OK."""
    errs = []
    if not sb.voiceover:
        errs.append("voiceover: path to the voiceover audio file is required")
    elif not sb.voiceover.exists():
        errs.append(f"voiceover file not found: {sb.voiceover}")
    if not sb.beats:
        errs.append("beats: at least one beat is required")
    if sb.data.get("frame", "framed") not in FRAMES:
        errs.append(f"frame: must be one of {sorted(FRAMES)}")
    ids = set()
    for i, b in enumerate(sb.beats):
        bid = b.get("id")
        where = f"beat #{i + 1}" + (f" ({bid})" if bid else "")
        if not bid:
            errs.append(f"{where}: needs an id")
        elif bid in ids:
            errs.append(f"{where}: duplicate id")
        ids.add(bid)
        t = b.get("type")
        if t not in BEAT_TYPES:
            errs.append(f"{where}: type must be one of {sorted(BEAT_TYPES)}")
            continue
        if not b.get("say") and b.get("at") is None and i > 0:
            errs.append(f"{where}: needs 'say' (the VO line it covers) or 'at' (start second)")
        if t in ("app", "compare"):
            if not b.get("actions") and not b.get("start"):
                errs.append(f"{where}: app beats need 'start' and/or 'actions'")
            for tn in (sb.beat_targets(b) if sb.targets else []):
                if tn not in sb.targets:
                    errs.append(f"{where}: unknown target '{tn}'")
            if not sb.targets:
                errs.append(f"{where}: no targets defined")
        if b.get("frame") is not None and b.get("frame") not in FRAMES:
            errs.append(f"{where}: frame must be one of {sorted(FRAMES)}")
        if t == "title" and not b.get("text"):
            errs.append(f"{where}: title beats need 'text'")
        if t == "code" and not (b.get("diff") or b.get("snippet")):
            errs.append(f"{where}: code beats need 'diff' or 'snippet'")
        if t == "clip":
            f = sb.resolve(b.get("file"))
            if not f or not f.exists():
                errs.append(f"{where}: clip file not found: {b.get('file')}")
    login = sb.app.get("login")
    if login:
        for name in env_refs(login):
            if name not in os.environ:
                errs.append(f"login uses ${{{name}}} but it is not set (add it to {sb.dir / '.env.reel'})")
    for b in sb.beats:
        for name in env_refs(b.get("actions", [])):
            if name not in os.environ:
                errs.append(f"beat {b.get('id')}: uses ${{{name}}} but it is not set")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        errs.append("ffmpeg/ffprobe not found on PATH (run scripts/preflight.sh)")
    return errs


# ---------- media helpers ----------

def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def pick_encoder():
    """Best H.264 encoder available. Fedora's ffmpeg-free lacks libx264."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if " libx264 " in out:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]
    if " libopenh264 " in out:
        return ["-c:v", "libopenh264", "-b:v", "10M", "-pix_fmt", "yuv420p"]
    if " h264_vaapi " in out and Path("/dev/dri/renderD128").exists():
        return ["-vaapi_device", "/dev/dri/renderD128", "-vf", "format=nv12,hwupload",
                "-c:v", "h264_vaapi", "-qp", "20"]
    return ["-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p"]


_font_cache = {}


def find_font(kind, style):
    """kind: regular | bold | mono. Honors style overrides, then fc-match."""
    key = (kind, style.get("font"), style.get("font_bold"), style.get("mono"))
    if key in _font_cache:
        return _font_cache[key]
    explicit = {"regular": style.get("font"), "bold": style.get("font_bold") or style.get("font"),
                "mono": style.get("mono")}[kind]
    candidates = []
    if explicit:
        candidates.append(explicit)
    patterns = {
        "regular": ["Inter:style=Medium", "Inter", "DejaVu Sans"],
        "bold": ["Inter:style=Bold", "Inter:style=ExtraBold", "DejaVu Sans:style=Bold"],
        "mono": ["JetBrains Mono", "Fira Code", "DejaVu Sans Mono", "Liberation Mono"],
    }[kind]
    found = None
    for c in candidates:
        if Path(c).expanduser().exists():
            found = str(Path(c).expanduser())
            break
        patterns.insert(0, c)
    if not found and shutil.which("fc-match"):
        for pat in patterns:
            r = subprocess.run(["fc-match", "-f", "%{file}", pat], capture_output=True, text=True)
            f = r.stdout.strip()
            fam = subprocess.run(["fc-match", "-f", "%{family}", pat], capture_output=True, text=True).stdout
            want = pat.split(":")[0].lower()
            if f and Path(f).exists() and want.split()[0] in fam.lower():
                found = f
                break
    if not found:
        for f in ["/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
            if Path(f).exists():
                found = f
                break
    _font_cache[key] = found
    return found


def hex_rgb(h, alpha=None):
    h = h.lstrip("#")
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return rgb + (alpha,) if alpha is not None else rgb


def read_json(path, default=None):
    p = Path(path)
    return json.loads(p.read_text()) if p.exists() else default


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=1))
