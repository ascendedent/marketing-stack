"""Compositor: takes + alignment + voiceover -> vertical MP4.

Works in design units for a 1080x1920 canvas, scaled by k for other sizes
(draft renders at half size). Frames are drawn with Pillow and piped to ffmpeg.
"""
import bisect
import json
import math
import shutil
import subprocess
import time
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import codecard
from common import die, ffprobe_duration, find_font, hex_rgb, info, pick_encoder, read_json

XFADE = 0.18


def ease(x):
    x = max(0.0, min(1.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


# ---------------- time mapping ----------------

class TimeMap:
    """Maps output time within a beat window to source take time.

    Shorter take: plays 1x then holds the last frame. Longer take: idle
    stretches (no repaint, no cursor motion) are squeezed first, then the
    rest is sped up uniformly, capped at max_speed."""

    def __init__(self, src_dur, activity, window, max_speed=2.2, keep_idle=0.45):
        self.src_dur = max(src_dur, 0.01)
        pts = [(0.0, 0.0)]
        excess = self.src_dur - window
        if excess > 0:
            ts = sorted(set(round(t, 3) for t in activity if 0 <= t <= self.src_dur)) + [self.src_dur]
            gaps = [(a, b) for a, b in zip([0.0] + ts, ts) if b - a > keep_idle]
            removable = sum(b - a - keep_idle for a, b in gaps)
            ratio = min(excess, removable) / removable if removable else 0.0
            comp, last = 0.0, 0.0
            for a, b in gaps:
                comp += a - last
                pts.append((a, comp))
                comp += keep_idle + (b - a - keep_idle) * (1 - ratio)
                pts.append((b, comp))
                last = b
            comp += self.src_dur - last
            pts.append((self.src_dur, comp))
        else:
            pts.append((self.src_dur, self.src_dur))
        self.pts = pts
        self.comp_dur = pts[-1][1]
        need = self.comp_dur / window if window > 0 else 1.0
        self.speed = min(max(1.0, need), max_speed)
        self.capped = need > max_speed + 1e-6
        self.squeezed = round(self.src_dur - self.comp_dur, 2)
        self._c = [p[1] for p in pts]

    def src(self, out_t):
        c = out_t * self.speed
        if c >= self.comp_dur:
            return self.src_dur
        i = max(1, bisect.bisect_right(self._c, c))
        (s0, c0), (s1, c1) = self.pts[i - 1], self.pts[i]
        if c1 - c0 < 1e-9:
            return s0
        return s0 + (s1 - s0) * (c - c0) / (c1 - c0)


# ---------------- sources ----------------

class TakeSource:
    def __init__(self, take_dir, window, max_speed):
        tl = read_json(Path(take_dir) / "timeline.json")
        if not tl:
            die(f"missing take: {take_dir} (run `reel record`)")
        self.dir = Path(take_dir)
        self.vp = tl["viewport"]
        self.frames = tl["frames"]
        if not self.frames:
            die(f"take has no frames: {take_dir}")
        self.times = [f["t"] for f in self.frames]
        self.cursor = tl["cursor"]
        self.ctimes = [c[0] for c in self.cursor]
        self.clicks = tl["clicks"]
        self.focus = tl["focus"]
        self.dur = tl["duration"]
        first = Image.open(self.dir / "frames" / self.frames[0]["f"])
        self.fw, self.fh = first.size
        self.css = self.fw / self.vp["width"]
        activity = self.times + self.ctimes + [c[0] for c in self.clicks]
        for f in self.focus:
            activity += [f["t0"], f["t1"]]
        self.tm = TimeMap(self.dur, activity, window, max_speed)
        self.cache = OrderedDict()

    def frame(self, st):
        i = max(0, bisect.bisect_right(self.times, st) - 1)
        if i in self.cache:
            self.cache.move_to_end(i)
            return i, self.cache[i]
        img = Image.open(self.dir / "frames" / self.frames[i]["f"]).convert("RGB")
        if img.size != (self.fw, self.fh):
            img = img.resize((self.fw, self.fh))
        self.cache[i] = img
        if len(self.cache) > 6:
            self.cache.popitem(last=False)
        return i, img

    def cursor_at(self, st):
        if not self.cursor:
            return None
        i = bisect.bisect_right(self.ctimes, st)
        if i == 0:
            c = self.cursor[0]
            return c[1] * self.css, c[2] * self.css
        if i >= len(self.cursor):
            c = self.cursor[-1]
            return c[1] * self.css, c[2] * self.css
        a, b = self.cursor[i - 1], self.cursor[i]
        f = (st - a[0]) / max(1e-6, b[0] - a[0])
        return (a[1] + (b[1] - a[1]) * f) * self.css, (a[2] + (b[2] - a[2]) * f) * self.css

    def clicks_at(self, st, life=0.5):
        return [((st - c[0]) / life, c[1] * self.css, c[2] * self.css) for c in self.clicks if 0 <= st - c[0] < life]

    def is_pressed(self, st):
        return any(0 <= st - c[0] < 0.12 for c in self.clicks)

    def zoom_at(self, st):
        """(scale, cx, cy) in frame px; scale 1 means no zoom."""
        best = (1.0, self.fw / 2, self.fh / 2, 0.0)
        for f in self.focus:
            e = max(0.05, f["ease"])
            if st < f["t0"] or st > f["t1"] + e:
                continue
            z = ease((st - f["t0"]) / e) if st < f["t1"] else 1 - ease((st - f["t1"]) / e)
            x, y, w, h = [v * self.css for v in f["box"]]
            # never zoom so far that the focused element itself gets cropped
            fit = max(1.0, min(f["scale"], self.fw / (w * 1.08), self.fh / (h * 1.08)))
            if z > best[3]:
                best = (1 + (fit - 1) * z, self.fw / 2 + (x + w / 2 - self.fw / 2) * z,
                        self.fh / 2 + (y + h / 2 - self.fh / 2) * z, z)
        return best[:3]

    def follow_center(self, st, lag=0.7, samples=8):
        pts = [self.cursor_at(st - lag * j / (samples - 1)) for j in range(samples)]
        pts = [p for p in pts if p]
        if not pts:
            return self.fw / 2, self.fh / 2
        return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


class ClipSource:
    """An existing video file (screen capture of your editor, a terminal, a
    session replay). Extracted to frames at the output fps and size."""

    def __init__(self, sb, beat, width_px, window, max_speed, draft):
        f = sb.resolve(beat["file"])
        trim = beat.get("trim")
        out = sb.work / "clips" / f"{beat['id']}-{width_px}"
        stamp = out / ".src"
        key = f"{f}:{f.stat().st_mtime}:{trim}"
        if not stamp.exists() or stamp.read_text() != key:
            out.mkdir(parents=True, exist_ok=True)
            for old in out.glob("*.jpg"):
                old.unlink()
            cmd = ["ffmpeg", "-v", "error", "-y"]
            if trim:
                cmd += ["-ss", str(trim[0]), "-to", str(trim[1])]
            cmd += ["-i", str(f), "-vf", f"fps={sb.fps},scale={width_px}:-2", "-q:v", "3", str(out / "%05d.jpg")]
            subprocess.run(cmd, check=True)
            stamp.write_text(key)
        self.paths = sorted(out.glob("*.jpg"))
        if not self.paths:
            die(f"could not read clip {f}")
        self.fps = sb.fps
        self.dur = len(self.paths) / sb.fps
        first = Image.open(self.paths[0])
        self.fw, self.fh = first.size
        self.tm = TimeMap(self.dur, [i / sb.fps for i in range(len(self.paths))], window, max_speed)
        self.cache = OrderedDict()

    def frame(self, st):
        i = min(len(self.paths) - 1, max(0, int(st * self.fps)))
        if i not in self.cache:
            self.cache[i] = Image.open(self.paths[i]).convert("RGB")
            if len(self.cache) > 4:
                self.cache.popitem(last=False)
        return i, self.cache[i]


# ---------------- drawing kit ----------------

class Kit:
    def __init__(self, sb, k):
        self.sb = sb
        self.k = k
        self.W, self.H = int(round(1080 * k)), int(round(1920 * k))
        self.st = sb.style
        self.bold = find_font("bold", self.st)
        self.reg = find_font("regular", self.st)
        if not self.bold:
            die("no usable font found (install google-noto-sans-fonts or set style.font_bold)")
        self._fonts = {}
        self._masks = {}
        self._shadows = {}
        self.bg = self._background()

    def S(self, v):
        return int(round(v * self.k))

    def font(self, size, bold=True):
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(self.bold if bold else (self.reg or self.bold), self.S(size))
        return self._fonts[key]

    def _background(self):
        top, bot = hex_rgb(self.st["bg"]), hex_rgb(self.st["bg2"])
        grad = Image.new("RGB", (1, 256))
        for y in range(256):
            f = y / 255
            grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * f) for i in range(3)))
        img = grad.resize((self.W, self.H), Image.BILINEAR)
        glow = Image.new("L", (self.W, self.H), 0)
        ImageDraw.Draw(glow).ellipse([-self.W * 0.3, -self.H * 0.25, self.W * 1.3, self.H * 0.35], fill=38)
        glow = glow.filter(ImageFilter.GaussianBlur(self.S(120)))
        acc = Image.new("RGB", (self.W, self.H), hex_rgb(self.st["accent"]))
        img = Image.composite(acc, img, glow)
        logo = self.st.get("logo")
        if logo:
            p = self.sb.resolve(logo)
            if p and p.exists():
                lg = Image.open(p).convert("RGBA")
                h = self.S(54)
                lg = lg.resize((max(1, int(lg.width * h / lg.height)), h), Image.LANCZOS)
                img.paste(lg, ((self.W - lg.width) // 2, self.S(70)), lg)
        return img

    def mask(self, w, h, r):
        key = (w, h, r)
        if key not in self._masks:
            m = Image.new("L", (w, h), 0)
            ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255)
            self._masks[key] = m
        return self._masks[key]

    def shadow(self, img, x, y, w, h, r):
        key = (w, h, r)
        if key not in self._shadows:
            pad = self.S(60)
            m = Image.new("L", (w + pad * 2, h + pad * 2), 0)
            ImageDraw.Draw(m).rounded_rectangle([pad, pad + self.S(18), pad + w, pad + h + self.S(18)], r, fill=150)
            self._shadows[key] = (m.filter(ImageFilter.GaussianBlur(self.S(26))), pad)
        m, pad = self._shadows[key]
        black = Image.new("RGB", m.size, (0, 0, 0))
        img.paste(black, (x - pad, y - pad), m)

    def text_center(self, d, text, cy, size, fill, max_w=940, bold=True, spacing=1.12):
        f = self.font(size, bold)
        lines = self.wrap(text, f, self.S(max_w))
        lh = int(f.size * spacing)
        y = cy - lh * len(lines) / 2
        for ln in lines:
            w = f.getlength(ln)
            d.text(((self.W - w) / 2, y), ln, font=f, fill=fill)
            y += lh
        return lh * len(lines)

    @staticmethod
    def wrap(text, f, max_w):
        out = []
        for para in str(text).split("\n"):
            cur = ""
            for w in para.split():
                trial = (cur + " " + w).strip()
                if f.getlength(trial) <= max_w or not cur:
                    cur = trial
                else:
                    out.append(cur)
                    cur = w
            out.append(cur)
        return out

    def chip(self, img, x, y, text, color, alpha=235):
        f = self.font(30)
        tw = f.getlength(text)
        pw, ph = int(tw + self.S(36)), self.S(52)
        layer = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        ImageDraw.Draw(layer).rounded_rectangle([0, 0, pw - 1, ph - 1], ph // 2, fill=hex_rgb(color, alpha))
        ImageDraw.Draw(layer).text((self.S(18), (ph - f.size) / 2 - self.S(3)), text, font=f, fill=(255, 255, 255))
        img.paste(layer, (int(x), int(y)), layer)
        return pw

    # u = canvas px per CSS px of the recorded page (times style.cursor.size), so the
    # pointer is drawn at the same scale as the UI around it, as a real one would be.
    def cursor(self, img, x, y, mobile, pressed, u=1.0):
        d = ImageDraw.Draw(img, "RGBA")
        if mobile:
            r = 18 * u * (0.85 if pressed else 1)
            d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, 120), outline=(0, 0, 0, 90),
                      width=max(1, round(2 * u)))
            return
        s = 0.8 * u * (0.9 if pressed else 1)  # the shape is 29 units tall: about a 23 CSS px pointer
        pts = [(0, 0), (0, 25), (6.5, 19), (11, 29), (15, 27.5), (10.5, 18), (19, 18)]
        poly = [(x + px * s, y + py * s) for px, py in pts]
        sh = [(px + 1.5 * s, py + 2 * s) for px, py in poly]
        d.polygon(sh, fill=(0, 0, 0, 70))
        d.polygon(poly, fill=(20, 20, 24, 255), outline=(255, 255, 255, 255))
        d.line(poly + [poly[0]], fill=(255, 255, 255, 255), width=max(1, round(1.6 * s)))

    def ripple(self, img, x, y, f, u=1.0):
        d = ImageDraw.Draw(img, "RGBA")
        r = (10 + 26 * ease_out(f)) * u
        a = int(200 * (1 - f))
        d.ellipse([x - r, y - r, x + r, y + r], outline=hex_rgb(self.st["accent"], a), width=max(1, round(3 * u)))


# ---------------- layouts ----------------

def slot_for(aspect, max_w, max_h, cx, top):
    w = max_w
    h = w / aspect
    if h > max_h:
        h = max_h
        w = h * aspect
    return int(cx - w / 2), int(top), int(w), int(h)


class AppView:
    """Draws one take into a slot: desktop browser window or phone frame."""

    def __init__(self, kit, src, slot, mobile, camera="window", follow_scale=1.8, chrome=True,
                 full=False, cursor=None):
        self.kit, self.src = kit, src
        self.x, self.y, self.w, self.h = slot
        self.mobile = mobile
        self.full = full  # edge to edge: no window chrome, corners, shadow or phone outline
        self.camera = camera
        self.follow_scale = follow_scale
        self.chrome = chrome and not mobile and camera == "window" and not full
        self.bar = kit.S(40) if self.chrome else 0
        self.radius = 0 if full else kit.S(46 if mobile else 18)
        self.cur = cursor or {"show": True, "clicks": True, "size": 1.0}
        self.rcache = OrderedDict()

    @property
    def outer(self):
        return self.x, self.y - self.bar, self.w, self.h + self.bar

    def _crop(self, st):
        src = self.src
        fw, fh = src.fw, src.fh
        zs, zx, zy = src.zoom_at(st)
        aspect = self.w / self.h
        if self.camera == "follow":
            base = self.follow_scale
            cx, cy = src.follow_center(st)
            cw = fw / base
            ch = cw / aspect
            if ch > fh:
                ch = fh
                cw = ch * aspect
            if zs > 1:
                cw, ch = cw / zs, ch / zs
                cx, cy = cx + (zx - cx) * min(1, zs - 1), cy + (zy - cy) * min(1, zs - 1)
        else:
            cw, ch = fw / zs, fh / zs
            # cover the slot: when its shape differs from the frame's, crop instead of stretching
            if cw / ch > aspect:
                cw = ch * aspect
            else:
                ch = cw / aspect
            cx, cy = zx, zy
        cx = min(max(cx, cw / 2), fw - cw / 2)
        cy = min(max(cy, ch / 2), fh - ch / 2)
        return cx - cw / 2, cy - ch / 2, cw, ch

    def draw(self, img, out_t):
        kit, src = self.kit, self.src
        st = src.tm.src(out_t)
        idx, frame = src.frame(st)
        crop = self._crop(st)
        key = (idx, tuple(round(v, 1) for v in crop))
        if key in self.rcache:
            view = self.rcache[key]
        else:
            x0, y0, cw, ch = crop
            box = (x0, y0, x0 + cw, y0 + ch)
            view = frame.resize((self.w, self.h), Image.BICUBIC, box=box, reducing_gap=2.0)
            self.rcache[key] = view
            if len(self.rcache) > 4:
                self.rcache.popitem(last=False)
        ox, oy, ow, oh = self.outer
        if self.full:
            img.paste(view, (self.x, self.y))
        elif self.chrome:
            kit.shadow(img, ox, oy, ow, oh, self.radius)
            bar = Image.new("RGB", (ow, oh), (236, 238, 242))
            bd = ImageDraw.Draw(bar)
            for j, col in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
                r = kit.S(7)
                cx = kit.S(24) + j * kit.S(22)
                bd.ellipse([cx - r, self.bar / 2 - r, cx + r, self.bar / 2 + r], fill=col)
            bar.paste(view, (0, self.bar))
            img.paste(bar, (ox, oy), kit.mask(ow, oh, self.radius))
        else:
            kit.shadow(img, ox, oy, ow, oh, self.radius)
            img.paste(view, (self.x, self.y), kit.mask(self.w, self.h, self.radius))
            if self.mobile:
                ImageDraw.Draw(img).rounded_rectangle(
                    [self.x - 2, self.y - 2, self.x + self.w + 1, self.y + self.h + 1], self.radius + 2,
                    outline=(40, 44, 52), width=max(2, kit.S(6)))
        # cursor + clicks, mapped from frame px into the slot
        x0, y0, cw, ch = crop
        sx, sy = self.w / cw, self.h / ch
        u = sx * src.css * self.cur["size"]
        u = max(kit.k * 0.4, min(kit.k * 2.4, u))
        if self.cur.get("clicks", True):
            for f, cxp, cyp in src.clicks_at(st):
                px, py = self.x + (cxp - x0) * sx, self.y + (cyp - y0) * sy
                if self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h:
                    kit.ripple(img, px, py, f, u)
        c = src.cursor_at(st) if self.cur.get("show", True) else None
        if c:
            px, py = self.x + (c[0] - x0) * sx, self.y + (c[1] - y0) * sy
            if self.x <= px <= self.x + self.w and self.y <= py <= self.y + self.h:
                if not self.mobile or src.is_pressed(st) or any(True for _ in src.clicks_at(st, 0.35)):
                    kit.cursor(img, px, py, self.mobile, src.is_pressed(st), u)


def heading(kit, img, beat, y=330):
    text = beat.get("heading")
    if not text:
        return
    d = ImageDraw.Draw(img)
    kit.text_center(d, text, kit.S(y), 60, hex_rgb(kit.st["text"]), max_w=920)


def banner(kit, img, text, y):
    """Heading as a dark pill over full-frame footage (y in 1080x1920 px)."""
    if not text:
        return
    f = kit.font(50)
    lines = kit.wrap(text, f, kit.S(900))
    lh = f.size * 1.18
    w = int(max(f.getlength(ln) for ln in lines) + kit.S(64))
    h = int(lh * len(lines) + kit.S(34))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, w - 1, h - 1], kit.S(26), fill=(10, 12, 16, 205))
    for i, ln in enumerate(lines):
        d.text(((w - f.getlength(ln)) / 2, kit.S(14) + i * lh), ln, font=f, fill=hex_rgb(kit.st["text"]))
    img.paste(layer, (int((kit.W - w) / 2), kit.S(y)), layer)


FULL_TOP = 160    # first y clear of the platform UI (references/platform-specs.md)
FULL_CAP_Y = 1380  # captions on full-frame beats: low, but inside the safe zone


def full_camera(beat, src, slot):
    """Full-frame beats: a take whose shape doesn't match the slot follows the cursor
    with a crop of the slot's shape (zoom 1 = the largest crop that fits)."""
    aspect = slot[2] / slot[3]
    if beat.get("camera"):
        return beat["camera"], float(beat.get("zoom", 1.8 if beat["camera"] == "follow" else 1.0))
    if abs(src.fw / src.fh - aspect) / aspect < 0.04:
        return "window", 1.0
    return "follow", float(beat.get("zoom", 1.0))


def label_color(sb, tname):
    t = sb.targets.get(tname, {})
    return t.get("color") or {"before": sb.style["before"], "after": sb.style["after"]}.get(tname, sb.style["accent"])


def label_text(sb, tname):
    return str(sb.targets.get(tname, {}).get("label", tname)).upper()


# ---------------- beat renderers ----------------

class TitleBeat:
    cap_y = 1440

    def __init__(self, kit, sb, beat, window):
        self.kit, self.beat, self.window = kit, beat, window

    def render(self, t):
        kit = self.kit
        img = kit.bg.copy()
        f = ease_out(t / 0.5)
        layer = Image.new("RGBA", (kit.W, kit.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        y = kit.S(self.beat.get("y", 820)) + kit.S(40) * (1 - f)
        h = kit.text_center(d, self.beat["text"], y, self.beat.get("size", 92), hex_rgb(kit.st["text"]), max_w=920)
        if self.beat.get("subtitle"):
            kit.text_center(d, self.beat["subtitle"], y + h / 2 + kit.S(70), 44, hex_rgb(kit.st["muted"]),
                            max_w=880, bold=False)
        if self.beat.get("kicker"):
            fk = kit.font(30)
            txt = self.beat["kicker"].upper()
            kit.chip(layer, (kit.W - fk.getlength(txt) - kit.S(36)) / 2, y - h / 2 - kit.S(100),
                     txt, kit.st["accent"])
        if f < 1:
            alpha = layer.getchannel("A").point(lambda a: int(a * f))
            layer.putalpha(alpha)
        img.paste(layer, (0, 0), layer)
        return img

    def report(self):
        return ""


class AppBeat:
    def __init__(self, kit, sb, beat, window, max_speed):
        self.kit, self.beat = kit, beat
        vp = sb.viewport(beat)
        tname = sb.beat_targets(beat)[0]
        self.src = TakeSource(sb.take_dir(beat["id"], tname), window, max_speed)
        self.tname = tname
        mobile = vp["mobile"]
        camera = beat.get("camera", "window")
        aspect = self.src.fw / self.src.fh
        self.full = sb.frame(beat) == "full"
        self.show_label = beat.get("label", False)
        if self.full:
            slot = (0, 0, kit.W, kit.H)
            camera, zoom = full_camera(beat, self.src, slot)
            self.cap_y = FULL_CAP_Y
            self.view = AppView(kit, self.src, slot, mobile, camera, zoom, full=True, cursor=sb.cursor(beat))
            return
        if mobile:
            slot = slot_for(aspect, kit.S(620), kit.S(1100), kit.W / 2, kit.S(250))
            self.cap_y = 1470
        elif camera == "follow":
            slot = slot_for(0.86, kit.S(1000), kit.S(1080), kit.W / 2, kit.S(250))
            self.cap_y = 1470
        else:
            top = 520 if beat.get("heading") else 470
            slot = slot_for(aspect, kit.S(1040), kit.S(900), kit.W / 2, kit.S(top))
            self.cap_y = top + slot[3] / kit.k + 200
        self.view = AppView(kit, self.src, slot, mobile, camera, float(beat.get("zoom", 1.8)),
                            cursor=sb.cursor(beat))

    def render(self, t):
        img = self.kit.bg.copy()
        if self.full:
            self.view.draw(img, t)
            kit = self.kit
            y = FULL_TOP
            if self.show_label:
                txt = self.show_label if isinstance(self.show_label, str) else label_text(kit.sb, self.tname)
                kit.chip(img, kit.S(40), kit.S(y), txt.upper(), label_color(kit.sb, self.tname))
                y += 80
            banner(kit, img, self.beat.get("heading"), y)
            return img
        heading(self.kit, img, self.beat, 330 if not self.view.mobile else 150)
        self.view.draw(img, t)
        if self.show_label:
            txt = self.show_label if isinstance(self.show_label, str) else label_text(self.kit.sb, self.tname)
            self.kit.chip(img, self.view.x + self.kit.S(18), self.view.y + self.kit.S(18), txt.upper(),
                          label_color(self.kit.sb, self.tname))
        return img

    def report(self):
        tm = self.src.tm
        msg = f"take {self.src.dur:.1f}s"
        if tm.squeezed > 0.05:
            msg += f", squeezed {tm.squeezed:.1f}s idle"
        if tm.speed > 1.01:
            msg += f", sped {tm.speed:.2f}x"
        if tm.capped:
            msg += "  ! still too long, end is cut: trim actions or give it more VO"
        return msg


class CompareBeat:
    def __init__(self, kit, sb, beat, window, max_speed):
        self.kit, self.sb, self.beat = kit, sb, beat
        vp = sb.viewport(beat)
        self.names = sb.beat_targets(beat)[:2]
        self.layout = beat.get("layout") or ("side" if vp["mobile"] else "stack")
        self.window = window
        if self.layout == "sequence":
            self.split = float(beat.get("split", 0.5))
            wins = [window * self.split, window * (1 - self.split)]
        else:
            wins = [window, window]
        self.srcs = [TakeSource(sb.take_dir(beat["id"], n), w, max_speed) for n, w in zip(self.names, wins)]
        aspect = self.srcs[0].fw / self.srcs[0].fh
        mobile = vp["mobile"]
        self.full = sb.frame(beat) == "full"
        cur = sb.cursor(beat)
        if self.full:
            W, H = kit.W, kit.H
            if self.layout == "stack":
                slots = [(0, 0, W, H // 2), (0, H // 2, W, H - H // 2)]
                self.cap_y = 960  # on the seam, clear of both halves' action as much as possible
            elif self.layout == "side":
                slots = [(0, 0, W // 2, H), (W // 2, 0, W - W // 2, H)]
                self.cap_y = FULL_CAP_Y
            else:
                slots = [(0, 0, W, H), (0, 0, W, H)]
                self.cap_y = FULL_CAP_Y
            self.views = []
            for src, sl in zip(self.srcs, slots):
                cam, zoom = full_camera(beat, src, sl)
                self.views.append(AppView(kit, src, sl, mobile, cam, zoom, full=True, cursor=cur))
            return
        if self.layout == "stack":
            s1 = slot_for(aspect, kit.S(860), kit.S(540), kit.W / 2, kit.S(175))
            s2 = slot_for(aspect, kit.S(860), kit.S(540), kit.W / 2, s1[1] + s1[3] + kit.S(130))
            slots = [s1, s2]
            self.cap_y = (s2[1] + s2[3]) / kit.k + 120
        elif self.layout == "side":
            w = kit.S(480)
            slots = [slot_for(aspect, w, kit.S(1000), kit.W * 0.27, kit.S(300)),
                     slot_for(aspect, w, kit.S(1000), kit.W * 0.73, kit.S(300))]
            self.cap_y = (slots[0][1] + slots[0][3]) / kit.k + 130
        else:  # sequence
            if mobile:
                s = slot_for(aspect, kit.S(620), kit.S(1100), kit.W / 2, kit.S(250))
                self.cap_y = 1470
            else:
                s = slot_for(aspect, kit.S(1040), kit.S(900), kit.W / 2, kit.S(520))
                self.cap_y = (s[1] + s[3]) / kit.k + 190
            slots = [s, s]
        self.views = [AppView(kit, src, sl, mobile, "window", cursor=cur) for src, sl in zip(self.srcs, slots)]

    def _render_full(self, t):
        kit = self.kit
        img = kit.bg.copy()
        if self.layout == "sequence":
            cut = self.window * self.split
            i = 0 if t < cut else 1
            lt = t if i == 0 else t - cut
            self.views[i].draw(img, lt)
            kit.chip(img, kit.S(40), kit.S(FULL_TOP), label_text(self.sb, self.names[i]),
                     label_color(self.sb, self.names[i]))
            banner(kit, img, self.beat.get("heading"), FULL_TOP + 80)
            if i == 1 and lt < 0.22:
                a = int(150 * (1 - lt / 0.22))
                flash = Image.new("RGBA", (kit.W, kit.H), (255, 255, 255, a))
                img.paste(flash, (0, 0), flash)
            return img
        for v in self.views:
            v.draw(img, t)
        d = ImageDraw.Draw(img)
        if self.layout == "stack":
            d.rectangle([0, kit.H // 2 - kit.S(3), kit.W, kit.H // 2 + kit.S(3)], fill=(10, 12, 16))
            spots = [(kit.S(40), kit.S(FULL_TOP)), (kit.S(40), kit.H // 2 + kit.S(30))]
        else:
            d.rectangle([kit.W // 2 - kit.S(3), 0, kit.W // 2 + kit.S(3), kit.H], fill=(10, 12, 16))
            spots = [(kit.S(30), kit.S(FULL_TOP)), (kit.W // 2 + kit.S(30), kit.S(FULL_TOP))]
        for n, (x, y) in zip(self.names, spots):
            kit.chip(img, x, y, label_text(self.sb, n), label_color(self.sb, n))
        banner(kit, img, self.beat.get("heading"), FULL_TOP + 80)
        return img

    def render(self, t):
        if self.full:
            return self._render_full(t)
        kit = self.kit
        img = kit.bg.copy()
        if self.layout == "sequence":
            cut = self.window * self.split
            i = 0 if t < cut else 1
            lt = t if i == 0 else t - cut
            heading(kit, img, self.beat, 330)
            v = self.views[i]
            v.draw(img, lt)
            kit.chip(img, v.x + kit.S(18), v.y + kit.S(18), label_text(self.sb, self.names[i]),
                     label_color(self.sb, self.names[i]))
            if i == 1 and lt < 0.22:  # flash on the switch
                a = int(150 * (1 - lt / 0.22))
                flash = Image.new("RGBA", (kit.W, kit.H), (255, 255, 255, a))
                img.paste(flash, (0, 0), flash)
            return img
        if self.layout == "side":
            heading(kit, img, self.beat, 170)
        for n, v in zip(self.names, self.views):
            v.draw(img, t)
            if self.layout == "side":
                ox = v.x + v.w / 2 - kit.font(30).getlength(label_text(self.sb, n)) / 2 - kit.S(18)
                kit.chip(img, ox, v.y - kit.S(76), label_text(self.sb, n), label_color(self.sb, n))
            else:
                kit.chip(img, v.x + kit.S(16), v.y - v.bar - kit.S(66), label_text(self.sb, n), label_color(self.sb, n))
        return img

    def report(self):
        parts = []
        for n, s in zip(self.names, self.srcs):
            tm = s.tm
            p = f"{n} {s.dur:.1f}s"
            if tm.speed > 1.01:
                p += f" @{tm.speed:.2f}x"
            if tm.capped:
                p += " ! cut"
            parts.append(p)
        return ", ".join(parts)


class CodeBeat:
    def __init__(self, kit, sb, beat, window):
        self.kit, self.beat, self.window = kit, beat, window
        self.card = codecard.build(sb, beat, kit.k)
        c = self.card
        self.header_h = kit.S(76)
        self.vx = (kit.W - c["width"]) // 2
        self.vy = kit.S(beat.get("y", 300))
        max_body = kit.S(beat.get("max_height", 980))
        self.body_h = min(c["height"], max_body)
        self.cap_y = (self.vy + self.header_h + self.body_h) / kit.k + 130
        adds = [i for i, r in enumerate(c["rows"]) if r["kind"] == "+"]
        self.adds = adds
        total_chars = sum(max(1, c["rows"][i]["chars"]) for i in adds) or 1
        self.total_chars = total_chars
        self.t_type0 = 0.12 * window
        self.t_type1 = max(self.t_type0 + 0.5, 0.78 * window)

    def _typed(self, t):
        f = (t - self.t_type0) / (self.t_type1 - self.t_type0)
        return int(max(0.0, min(1.0, f)) * self.total_chars)

    def render(self, t):
        kit, c = self.kit, self.card
        img = kit.bg.copy()
        heading(kit, img, self.beat, 170)
        focus_y = 0
        lh = c["lh"]
        if c["typing"] and self.adds:
            # Added lines are inserted as they get typed, so the file grows on screen.
            body = Image.new("RGB", (c["width"], c["height"]), c["bg"])
            d = ImageDraw.Draw(body)
            budget = self._typed(t)
            y = c["rows"][0]["y"] if c["rows"] else 0
            typing_y = None
            for r in c["rows"]:
                shown = None
                if r["kind"] == "+":
                    n = max(1, r["chars"])
                    shown = max(0, min(n, budget))
                    budget -= n
                    if shown == 0:
                        continue
                body.paste(c["img"].crop((0, r["y"], c["width"], r["y"] + lh)), (0, y))
                if shown is not None and shown < max(1, r["chars"]):
                    x = c["gutter"] + c["cw"] * shown
                    d.rectangle([x, y, c["width"], y + lh - 1], fill=r["bg"])
                    d.rectangle([x, y + kit.S(8), x + kit.S(3), y + lh - kit.S(8)], fill=hex_rgb(kit.st["accent"]))
                    typing_y = y
                y += lh
            content_h = y + lh
            focus_y = typing_y if typing_y is not None else y - lh
        else:
            body = c["img"]
            content_h = c["height"]
            stars = [r["y"] for r in c["rows"] if r["kind"] == "*"]
            focus_y = stars[0] if stars else 0
        # scroll to keep the action in view
        scroll = 0
        if content_h > self.body_h:
            target = max(0, min(content_h - self.body_h, focus_y - self.body_h * 0.45))
            if not c["typing"]:
                target *= ease(t / max(0.5, self.window * 0.4))
            scroll = int(target)
        view = body.crop((0, scroll, c["width"], scroll + self.body_h))
        ox, oy = self.vx, self.vy
        H = self.header_h + self.body_h
        kit.shadow(img, ox, oy, c["width"], H, kit.S(20))
        card = Image.new("RGB", (c["width"], H), tuple(min(255, v + 14) for v in c["bg"]))
        cd = ImageDraw.Draw(card)
        fname = c["file"]
        f = kit.font(28)
        cd.text((kit.S(28), (self.header_h - f.size) / 2 - kit.S(2)), fname, font=f, fill=(230, 237, 243))
        stats = []
        if c["adds"]:
            stats.append((f"+{c['adds']}", (63, 185, 80)))
        if c["dels"]:
            stats.append((f"−{c['dels']}", (248, 81, 73)))
        fs = kit.font(26)
        x = c["width"] - kit.S(28)
        for txt, col in reversed(stats):
            x -= fs.getlength(txt)
            cd.text((x, (self.header_h - fs.size) / 2 - kit.S(2)), txt, font=fs, fill=col)
            x -= kit.S(16)
        fr = kit.font(22, bold=False)
        refs = c["refs"]
        cd.text((kit.S(28) + f.getlength(fname) + kit.S(18), (self.header_h - fr.size) / 2), refs,
                font=fr, fill=(139, 148, 158))
        card.paste(view, (0, self.header_h))
        img.paste(card, (ox, oy), kit.mask(c["width"], H, kit.S(20)))
        return img

    def report(self):
        return f"{len(self.card['rows'])} lines, {self.card['adds']} added"


class ClipBeat:
    def __init__(self, kit, sb, beat, window, max_speed, draft):
        self.kit, self.beat = kit, beat
        self.fill = beat.get("fit", "fill" if sb.frame(beat) == "full" else "window") == "fill"
        width_px = kit.W if self.fill else kit.S(1000)
        self.src = ClipSource(sb, beat, width_px, window, max_speed, draft)
        aspect = self.src.fw / self.src.fh
        if self.fill:
            self.slot = None
            self.cap_y = 1440
        else:
            self.slot = slot_for(aspect, kit.S(1000), kit.S(1050), kit.W / 2, kit.S(470))
            self.cap_y = (self.slot[1] + self.slot[3]) / kit.k + 130

    def render(self, t):
        kit = self.kit
        img = kit.bg.copy()
        st = self.src.tm.src(t)
        _, fr = self.src.frame(st)
        if self.fill:
            s = max(kit.W / fr.width, kit.H / fr.height)
            w, h = int(fr.width * s), int(fr.height * s)
            big = fr.resize((w, h), Image.BICUBIC)
            img.paste(big, ((kit.W - w) // 2, (kit.H - h) // 2))
            return img
        heading(kit, img, self.beat, 330)
        x, y, w, h = self.slot
        view = fr.resize((w, h), Image.BICUBIC)
        r = kit.S(18)
        kit.shadow(img, x, y, w, h, r)
        img.paste(view, (x, y), kit.mask(w, h, r))
        return img

    def report(self):
        tm = self.src.tm
        return f"clip {self.src.dur:.1f}s" + (f" @{tm.speed:.2f}x" if tm.speed > 1.01 else "") + (" ! cut" if tm.capped else "")


# ---------------- captions ----------------

class Captions:
    def __init__(self, kit, words, cfg):
        self.kit = kit
        self.cfg = cfg
        self.style = cfg.get("style", "words")
        self.size = cfg.get("size") or 74
        self.upper = cfg.get("uppercase", False)
        maxw = int(cfg.get("max_words", 3))
        if self.style == "lines":
            maxw = max(maxw, 7)
        chunks, cur = [], []
        for i, w in enumerate(words):
            if cur and (len(cur) >= maxw or w["s"] - cur[-1]["e"] > 0.45):
                chunks.append(cur)
                cur = []
            cur.append(w)
            if w["w"][-1:] in ".!?;:," and len(cur) >= 1:
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        self.chunks = []
        for i, ch in enumerate(chunks):
            s = ch[0]["s"]
            e = ch[-1]["e"] + 0.25
            if i + 1 < len(chunks):
                nxt = chunks[i + 1][0]["s"]
                e = nxt if nxt - ch[-1]["e"] < 0.7 else min(e, nxt)
            self.chunks.append((s, e, ch))
        self.starts = [c[0] for c in self.chunks]

    def draw(self, img, t, cy):
        if self.style == "off" or not self.chunks:
            return
        i = bisect.bisect_right(self.starts, t) - 1
        if i < 0:
            return
        s, e, ch = self.chunks[i]
        if t > e:
            return
        kit = self.kit
        f = kit.font(self.size)
        words = [(w["w"].upper() if self.upper else w["w"]) for w in ch]
        space = f.getlength(" ")
        widths = [f.getlength(w) for w in words]
        max_w = kit.S(960)
        lines, cur, cw = [], [], 0
        for j, w in enumerate(widths):
            if cur and cw + space + w > max_w:
                lines.append(cur)
                cur, cw = [], 0
            cw += (space if cur else 0) + w
            cur.append(j)
        lines.append(cur)
        lh = int(f.size * 1.25)
        y = kit.S(cy) - lh * len(lines) / 2
        pop = ease_out((t - s) / 0.12)
        d = ImageDraw.Draw(img, "RGBA")
        active = max([j for j, w in enumerate(ch) if w["s"] <= t + 0.02], default=-1)
        stroke = max(2, kit.S(6))
        for ln in lines:
            total = sum(widths[j] for j in ln) + space * (len(ln) - 1)
            x = (kit.W - total) / 2
            for j in ln:
                yy = y + kit.S(10) * (1 - pop)
                if j == active and self.style in ("words", "pill"):
                    pad = kit.S(12)
                    d.rounded_rectangle([x - pad, yy - pad * 0.3, x + widths[j] + pad, yy + f.size * 1.08],
                                        kit.S(14), fill=hex_rgb(kit.st["accent"], 255))
                    d.text((x, yy), words[j], font=f, fill=hex_rgb(kit.st["bg"]))
                else:
                    d.text((x, yy), words[j], font=f, fill=(255, 255, 255), stroke_width=stroke,
                           stroke_fill=(0, 0, 0))
                x += widths[j] + space
            y += lh


# ---------------- main ----------------

def compose(sb, draft=False, out=None, max_speed=None, captions_style=None):
    al = read_json(sb.work / "align.json")
    if not al:
        die("no alignment yet (run `reel align`)")
    ids = [b["id"] for b in sb.beats]
    if [r["id"] for r in al["beats"]] != ids:
        die("beats changed since the last align; run `reel align` again")
    k = 0.5 if draft else sb.width / 1080
    kit = Kit(sb, k)
    kit.sb = sb
    max_speed = max_speed or float(sb.data.get("max_speed", 2.2))
    rows = al["beats"]
    renderers = []
    for b, r in zip(sb.beats, rows):
        w = r["dur"]
        t = b["type"]
        ms = float(b.get("max_speed", max_speed))
        if t == "title":
            rd = TitleBeat(kit, sb, b, w)
        elif t == "app":
            rd = AppBeat(kit, sb, b, w, ms)
        elif t == "compare":
            rd = CompareBeat(kit, sb, b, w, ms)
        elif t == "code":
            rd = CodeBeat(kit, sb, b, w)
        else:
            rd = ClipBeat(kit, sb, b, w, ms, draft)
        renderers.append(rd)
    ccfg = dict(sb.style["captions"])
    if captions_style:
        ccfg["style"] = captions_style
    engine = caption_engine(ccfg)
    caps = Captions(kit, al["words"], ccfg) if engine == "builtin" else None
    total = al["total"]
    fps = sb.fps
    n = int(round(total * fps))
    out_dir = sb.dir / "out"
    out_dir.mkdir(exist_ok=True)
    final = Path(out) if out else out_dir / f"{sb.slug}{'.draft' if draft else ''}.mp4"
    out = sb.work / f"base{'.draft' if draft else ''}.mp4" if engine == "remotion" else final
    starts = [r["start"] for r in rows]

    vo_off = float(sb.data.get("vo_offset", 0))
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{kit.W}x{kit.H}", "-r", str(fps), "-i", "-", "-i", str(sb.voiceover)]
    music = sb.resolve(sb.data.get("music")) if sb.data.get("music") else None
    delay = int(vo_off * 1000)
    af = f"[1:a]adelay={delay}|{delay},apad[vo]" if delay else "[1:a]apad[vo]"
    if music and music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music)]
        mv = float(sb.data.get("music_volume", 0.18))
        af = (f"{af};[vo]asplit[v1][v2];[2:a]volume={mv},afade=t=out:st={max(0, total - 1.5)}:d=1.5[m];"
              f"[m][v1]sidechaincompress=threshold=0.04:ratio=6:attack=15:release=350[md];"
              f"[v2][md]amix=inputs=2:duration=first:normalize=0[mix];[mix]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        af += ";[vo]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    enc = pick_encoder()
    if engine == "remotion" and "libx264" in enc:
        enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p"]
    elif engine == "remotion" and "libopenh264" in enc:
        enc = ["-c:v", "libopenh264", "-b:v", "24M", "-pix_fmt", "yuv420p"]
    elif draft and "libx264" in enc:
        enc = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p"]
    cmd += ["-filter_complex", af, "-map", "0:v", "-map", "[a]", "-t", f"{total:.3f}", *enc,
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    info(f"rendering {n} frames at {kit.W}x{kit.H} -> {out}")
    t0 = time.time()
    last_frames = {}
    cur_b = -1
    try:
        for i in range(n):
            t = i / fps
            bi = max(0, bisect.bisect_right(starts, t) - 1)
            local = t - starts[bi]
            frame = renderers[bi].render(local)
            if bi > 0 and local < XFADE and (bi - 1) in last_frames:
                frame = Image.blend(last_frames[bi - 1], frame, ease(local / XFADE))
            if bi != cur_b:
                cur_b = bi
            # remember the final frame of each beat for the crossfade
            if i + 1 >= n or (bi + 1 < len(starts) and (i + 1) / fps >= starts[bi + 1]):
                last_frames[bi] = frame.copy()
            if caps:
                caps.draw(frame, t, renderers[bi].cap_y)
            proc.stdin.write(frame.tobytes())
            if i and i % (fps * 5) == 0:
                el = time.time() - t0
                info(f"  {i}/{n} frames ({el / i * (n - i):.0f}s left)")
    except BrokenPipeError:
        pass
    proc.stdin.close()
    if proc.wait() != 0:
        die("ffmpeg failed while encoding")
    info(f"footage done in {time.time() - t0:.0f}s")
    for b, r, rd in zip(sb.beats, rows, renderers):
        rep = rd.report()
        info(f"  {b['id']:<16} {r['dur']:5.1f}s  {rep}")
    if engine == "remotion":
        burn_captions(sb, al, rows, renderers, out, final, ccfg, draft, total)
    else:
        info(f"done: {final}")
    return final


# ---------------- Remotion caption pass ----------------

CAPTIONER = Path(__file__).resolve().parent.parent / "captioner"
REMOTION_STYLES = {"tiktok", "bold", "bounce", "clean"}
BUILTIN_STYLES = {"pill", "words", "lines", "off"}


def captioner_ready():
    return (CAPTIONER / "node_modules" / "@remotion" / "renderer").exists() and shutil.which("node")


def caption_engine(ccfg):
    style = ccfg.get("style") or "tiktok"
    if style in BUILTIN_STYLES:
        if style == "words":
            ccfg["style"] = "words"
        return "builtin"
    if style not in REMOTION_STYLES:
        die(f"unknown caption style '{style}'. Use one of: {', '.join(sorted(REMOTION_STYLES | {'pill', 'lines', 'off'}))}")
    if not captioner_ready():
        info(f"  caption style '{style}' needs the Remotion captioner (run scripts/preflight.sh); using built-in 'pill' captions")
        ccfg["style"] = "words"
        return "builtin"
    return "remotion"


def burn_captions(sb, al, rows, renderers, base, final, ccfg, draft, total):
    words = [w for w in al["words"] if w["e"] > w["s"]]
    caps = []
    for i, w in enumerate(words):
        text = w["w"].upper() if ccfg.get("uppercase") else w["w"]
        caps.append({"text": ("" if i == 0 else " ") + text, "startMs": round(w["s"] * 1000),
                     "endMs": round(w["e"] * 1000), "timestampMs": round((w["s"] + w["e"]) * 500),
                     "confidence": None})
    # hard page breaks: sentence ends, long pauses, and beat cuts
    ends = [r["end"] for r in rows]
    brk = []
    for i in range(len(words) - 1):
        w, nx = words[i], words[i + 1]
        cut = any(w["s"] < e <= nx["s"] + 0.05 for e in ends)
        if w["w"][-1:] in ".!?;:" or nx["s"] - w["e"] > 0.6 or cut:
            brk.append(i)
    unit = sb.width / 1080
    zones = [{"startMs": round(r["start"] * 1000), "endMs": round(r["end"] * 1000),
              "y": round(rd.cap_y * unit)} for r, rd in zip(rows, renderers)]
    job = {
        "video": str(base), "out": str(final), "captions": caps, "zones": zones,
        "style": ccfg.get("style", "tiktok"), "accent": sb.style["accent"],
        "uppercase": bool(ccfg.get("uppercase", False)),
        "combineMs": ccfg.get("combine_ms"), "fontSize": ccfg.get("size"), "breakAfter": brk,
        "durationInSeconds": total, "fps": sb.fps, "width": sb.width, "height": sb.height,
        "scale": 0.5 if draft else 1, "crf": 26 if draft else 18,
        "x264Preset": "ultrafast" if draft else "veryfast",
        "bundleCache": str(sb.work / "captioner-bundle"),
    }
    jp = sb.work / "caption-job.json"
    jp.write_text(json.dumps(job))
    info(f"burning '{job['style']}' captions with Remotion...")
    t0 = time.time()
    r = subprocess.run(["node", str(CAPTIONER / "render.mjs"), "--job", str(jp)], cwd=CAPTIONER)
    if r.returncode != 0:
        die("caption render failed (see output above). Set style.captions.style: pill to use built-in captions.")
    info(f"done in {time.time() - t0:.0f}s: {final}")
