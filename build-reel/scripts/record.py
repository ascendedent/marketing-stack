"""Browser side: login, inspect, and recording takes via CDP screencast.

A take is a folder of JPEG frames (only written when the page repaints, each
with a timestamp) plus timeline.json: cursor path, clicks, focus/zoom windows
and the take length. The compositor draws the cursor and zooms later, so a bad
zoom is a recompose, not a re-record.
"""
import base64
import json
import math
import shutil
import time
from pathlib import Path

from common import die, expand_env, info, write_json

HIDE_CSS = """
::-webkit-scrollbar { display: none !important; }
html { scrollbar-width: none !important; }
* { caret-color: auto; }
"""


def _launch(p, headed=False):
    # Prefer the Playwright-bundled Chromium, fall back to an installed Chrome.
    try:
        return p.chromium.launch(headless=not headed)
    except Exception:
        try:
            return p.chromium.launch(headless=not headed, channel="chrome")
        except Exception as e:
            die(f"could not launch a browser ({e}). Run: .venv/bin/playwright install chromium")


def _context(browser, sb, vp, target, use_auth=True):
    kw = dict(
        viewport={"width": vp["width"], "height": vp["height"]},
        device_scale_factor=vp["dpr"],
        is_mobile=vp["mobile"],
        has_touch=vp["mobile"],
        color_scheme=sb.data.get("color_scheme", "light"),
        locale="en-US",
    )
    auth = sb.auth_path(target)
    if use_auth and auth.exists():
        kw["storage_state"] = str(auth)
    ctx = browser.new_context(**kw)
    hide = list(sb.app.get("hide", []))
    css = HIDE_CSS + "".join(f"{s}{{display:none !important}}\n" for s in hide)
    ctx.add_init_script(
        "(() => { const add = () => { const s = document.createElement('style');"
        " s.textContent = " + json.dumps(css) + "; document.documentElement.appendChild(s); };"
        " if (document.documentElement) add(); else document.addEventListener('DOMContentLoaded', add); })();")
    ctx.set_default_timeout(int(sb.app.get("timeout_ms", 15000)))
    return ctx


def _url(base, path):
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base + ("" if path.startswith("/") else "/") + path


# ---------------- login ----------------

def login(sb, target_names=None, headed=False):
    from playwright.sync_api import sync_playwright
    spec = sb.app.get("login")
    if not spec:
        info("no app.login block; skipping login")
        return
    names = target_names or list(sb.targets)
    with sync_playwright() as p:
        browser = _launch(p, headed)
        for name in names:
            t = sb.target(name)
            vp = sb.viewport()
            ctx = _context(browser, sb, vp, name, use_auth=False)
            page = ctx.new_page()
            page.goto(_url(t["url"], spec.get("url", "/login")), wait_until="domcontentloaded")
            runner = Runner(page, None, vp, t["url"], recording=False)
            for step in spec.get("steps", []):
                runner.run(expand_env(step))
            done = spec.get("done")
            if done:
                runner.run({"waitFor": expand_env(done)})
            else:
                page.wait_for_load_state("networkidle")
            path = sb.auth_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            ctx.storage_state(path=str(path))
            info(f"logged in on {name} ({t['url']}) -> {path.relative_to(sb.dir)}")
            ctx.close()
        browser.close()


# ---------------- inspect ----------------

INSPECT_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const q = 'a,button,input,select,textarea,[role=button],[role=link],[role=tab],[role=menuitem],[onclick],[data-testid],summary,label';
  const esc = s => s.replace(/"/g, '\\"');
  const uniq = sel => { try { return document.querySelectorAll(sel).length === 1; } catch { return false; } };
  for (const el of document.querySelectorAll(q)) {
    const r = el.getBoundingClientRect();
    if (r.width < 4 || r.height < 4) continue;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || +st.opacity === 0) continue;
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('placeholder') || '').trim().replace(/\s+/g, ' ').slice(0, 50);
    const tag = el.tagName.toLowerCase();
    const cands = [];
    const tid = el.getAttribute('data-testid'); if (tid) cands.push(`[data-testid="${esc(tid)}"]`);
    if (el.id) cands.push(`#${CSS.escape(el.id)}`);
    const al = el.getAttribute('aria-label'); if (al) cands.push(`${tag}[aria-label="${esc(al)}"]`);
    const nm = el.getAttribute('name'); if (nm) cands.push(`${tag}[name="${esc(nm)}"]`);
    const ph = el.getAttribute('placeholder'); if (ph) cands.push(`${tag}[placeholder="${esc(ph)}"]`);
    let sel = cands.find(uniq);
    if (!sel && text && ['a','button','summary','label'].includes(tag)) sel = `${tag}:has-text("${esc(text.slice(0, 30))}")`;
    if (!sel) continue;
    if (seen.has(sel)) continue; seen.add(sel);
    out.push({ tag, text, selector: sel, box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)], inView: r.top < innerHeight && r.bottom > 0 });
  }
  const heads = [...document.querySelectorAll('h1,h2,h3')].slice(0, 12).map(h => h.innerText.trim().slice(0, 60));
  return { title: document.title, url: location.href, headings: heads, elements: out.slice(0, 120) };
}
"""


def inspect(sb, target, path="/", headed=False, beat=None):
    from playwright.sync_api import sync_playwright
    t = sb.target(target)
    vp = sb.viewport(beat)
    out_dir = sb.work / "inspect"
    out_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = _launch(p, headed)
        ctx = _context(browser, sb, vp, target)
        page = ctx.new_page()
        page.goto(_url(t["url"], path), wait_until="domcontentloaded")
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        data = page.evaluate(INSPECT_JS)
        stem = f"{target}-{path.strip('/').replace('/', '_') or 'root'}"
        page.screenshot(path=str(out_dir / f"{stem}.png"))
        write_json(out_dir / f"{stem}.json", data)
        browser.close()
    info(f"{data['title']}  {data['url']}")
    if data["headings"]:
        info("headings: " + " | ".join(data["headings"]))
    for el in data["elements"]:
        flag = "" if el["inView"] else "  (below fold)"
        info(f"  {el['tag']:<8} {el['selector']:<48} {el['text'][:40]}{flag}")
    info(f"screenshot: {out_dir / (stem + '.png')}")


# ---------------- recording ----------------

def _ease(x):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))


class Runner:
    """Executes storyboard actions on a page. When recording, logs cursor
    positions, clicks and focus windows against wall-clock time."""

    def __init__(self, page, take, vp, base_url, recording=True):
        self.page = page
        self.take = take
        self.vp = vp
        self.base = base_url
        self.recording = recording
        self.cursor = (vp["width"] * 0.62, vp["height"] * 0.72)
        self.speed = 1.0
        if take:
            take.log_cursor(*self.cursor)

    # -- helpers --
    def _wait(self, ms):
        self.page.wait_for_timeout(max(1, int(ms)))

    def _loc(self, target):
        if isinstance(target, dict):
            if "text" in target and "selector" not in target:
                return self.page.get_by_text(target["text"], exact=target.get("exact", False)).first
            loc = self.page.locator(target["selector"])
            if "text" in target:
                loc = loc.filter(has_text=target["text"])
            return loc.nth(int(target.get("nth", 0)))
        return self.page.locator(target).first

    def _box(self, loc, scroll=True):
        loc.wait_for(state="visible")
        if scroll:
            inview = loc.evaluate(
                "el => { const r = el.getBoundingClientRect();"
                " return r.top >= 60 && r.bottom <= innerHeight - 60; }")
            if not inview:
                loc.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})")
                self._wait(650)
        b = loc.bounding_box()
        if not b:
            die("element has no bounding box (is it visible?)")
        return b

    def _move(self, x, y, ms=None):
        x0, y0 = self.cursor
        dist = math.hypot(x - x0, y - y0)
        if ms is None:
            ms = min(900, max(280, dist * 1.1))
        ms = ms / self.speed
        # slight arc so it reads as a hand, not a robot
        bend = min(60, dist * 0.12)
        nx, ny = (-(y - y0) / dist, (x - x0) / dist) if dist > 1 else (0, 0)
        # time-based so the move lasts `ms` regardless of round-trip latency
        t0 = time.time()
        while True:
            el = (time.time() - t0) * 1000
            f = _ease(el / ms) if el < ms else 1.0
            arc = math.sin(math.pi * f) * bend
            cx = x0 + (x - x0) * f + nx * arc
            cy = y0 + (y - y0) * f + ny * arc
            self.page.mouse.move(cx, cy)
            if self.take:
                self.take.log_cursor(cx, cy)
            if f >= 1.0:
                break
            if el < ms - 20:
                self._wait(12)
        self.cursor = (x, y)

    def _point_in(self, box, where=None):
        fx, fy = (0.5, 0.5) if not where else where
        return box["x"] + box["width"] * fx, box["y"] + box["height"] * fy

    # -- actions --
    def run(self, action):
        if isinstance(action, str):
            action = {action: True}
        if not isinstance(action, dict) or not action:
            die(f"bad action: {action!r}")
        op, arg = next(iter(action.items()))
        extra = {k: v for k, v in action.items() if k != op}
        fn = getattr(self, "a_" + op.replace("-", "_"), None)
        if not fn:
            die(f"unknown action '{op}'. Known: goto, click, type, fill, press, hover, scroll, wait, waitFor, focus, select, eval, speed")
        if self.take:
            self.take.mark(op, arg)
        fn(arg, **extra)

    def a_goto(self, path, wait="networkidle"):
        self.page.goto(_url(self.base, path), wait_until="domcontentloaded")
        try:
            self.page.wait_for_load_state(wait, timeout=8000)
        except Exception:
            pass

    def a_click(self, target, pause=180, after=450):
        loc = self._loc(target)
        box = self._box(loc)
        x, y = self._point_in(box)
        if self.recording:
            self._move(x, y)
            self._wait(pause / self.speed)
            if self.take:
                self.take.log_click(x, y)
            self.page.mouse.click(x, y)
            self._wait(after / self.speed)
        else:
            loc.click()

    def a_hover(self, target, hold=600):
        loc = self._loc(target)
        box = self._box(loc)
        x, y = self._point_in(box)
        if self.recording:
            self._move(x, y)
        else:
            loc.hover()
        self._wait(hold / self.speed)

    def a_type(self, arg, text=None, delay=55, clear=True, enter=False):
        if isinstance(arg, dict):
            text = arg.get("text", text)
            delay = arg.get("delay", delay)
            clear = arg.get("clear", clear)
            enter = arg.get("enter", enter)
            target = arg.get("selector") or arg.get("target")
        else:
            target = arg
        if text is None:
            die("type needs text")
        loc = self._loc(target)
        if self.recording:
            box = self._box(loc)
            x, y = self._point_in(box, (0.15, 0.5))
            self._move(x, y)
            self._wait(120)
            if self.take:
                self.take.log_click(x, y)
            self.page.mouse.click(x, y)
        else:
            loc.click()
        if clear:
            loc.fill("")
        if not self.recording:
            loc.fill(text)
        else:
            for ch in text:
                self.page.keyboard.type(ch)
                jitter = delay * (0.6 + 0.8 * ((hash(ch) % 100) / 100))
                self._wait(jitter / self.speed)
        if enter:
            self.page.keyboard.press("Enter")
            self._wait(300)

    def a_fill(self, arg, value=None):
        """Instant fill (good for login or setup)."""
        if isinstance(arg, dict):
            target, value = arg.get("selector"), arg.get("value", value)
        else:
            target = arg
        self._loc(target).fill(str(value))

    def a_press(self, key, after=350):
        self.page.keyboard.press(key)
        self._wait(after / self.speed)

    def a_select(self, arg):
        self._loc(arg["selector"]).select_option(arg["value"])
        self._wait(300)

    def a_wait(self, ms):
        self._wait(float(ms) / self.speed)

    def a_waitFor(self, arg, timeout=15000):
        if isinstance(arg, dict):
            if "url" in arg:
                self.page.wait_for_url(arg["url"], timeout=timeout)
                return
            if "text" in arg:
                self.page.get_by_text(arg["text"]).first.wait_for(state="visible", timeout=timeout)
                return
            arg = arg.get("selector")
        self.page.locator(arg).first.wait_for(state="visible", timeout=timeout)

    a_wait_for = a_waitFor

    def a_scroll(self, arg, duration=900):
        """scroll: 600 | {by: 600, duration: 900, in: '.panel'} | {to: '#pricing'}"""
        if not isinstance(arg, dict):
            arg = {"by": arg}
        duration = arg.get("duration", duration) / self.speed
        if "to" in arg:
            loc = self._loc(arg["to"])
            loc.wait_for(state="attached")
            delta = loc.evaluate("el => el.getBoundingClientRect().top - innerHeight * 0.25")
        else:
            delta = float(arg.get("by", 600))
        container = arg.get("in")
        js = """async ([delta, dur, sel]) => {
          const el = sel ? document.querySelector(sel) : null;
          const get = () => el ? el.scrollTop : scrollY;
          const set = v => el ? (el.scrollTop = v) : scrollTo(0, v);
          const start = get(); const t0 = performance.now();
          await new Promise(res => { const step = now => {
            const f = Math.min(1, (now - t0) / dur);
            const e = f < .5 ? 4*f*f*f : 1 - Math.pow(-2*f + 2, 3) / 2;
            set(start + delta * e); f < 1 ? requestAnimationFrame(step) : res(); };
            requestAnimationFrame(step); });
        }"""
        self.page.evaluate(js, [delta, duration, container])
        self._wait(150)

    def a_focus(self, target, scale=1.7, hold=1600, ease=380):
        """Zoom the camera onto an element (applied at compose time)."""
        loc = self._loc(target)
        box = self._box(loc)
        if self.take:
            self.take.log_focus(box, scale, hold / self.speed, ease)
        self._wait(hold / self.speed)

    a_zoom = a_focus

    def a_eval(self, js):
        self.page.evaluate(js)

    def a_speed(self, factor):
        """Speed up or slow down everything after this point (cursor, typing, waits)."""
        self.speed = float(factor)

    def a_cursor(self, arg):
        """Park the cursor: cursor: {x: 0.5, y: 0.8} as fractions of the viewport."""
        x, y = arg["x"] * self.vp["width"], arg["y"] * self.vp["height"]
        self._move(x, y, arg.get("ms"))


class Take:
    def __init__(self, out_dir, cdp, vp):
        self.dir = Path(out_dir)
        if self.dir.exists():
            shutil.rmtree(self.dir)
        (self.dir / "frames").mkdir(parents=True)
        self.cdp = cdp
        self.vp = vp
        self.t0 = None
        self.frames, self.cursor, self.clicks, self.focus, self.marks = [], [], [], [], []
        self.last_frame_wall = None

    def now(self):
        return time.time() - (self.t0 or time.time())

    def _on_frame(self, f):
        try:
            ts = f["metadata"].get("timestamp") or time.time()
            if self.t0 is None:
                return
            i = len(self.frames)
            name = f"{i:05d}.jpg"
            (self.dir / "frames" / name).write_bytes(base64.b64decode(f["data"]))
            self.frames.append({"t": round(max(0.0, ts - self.t0), 4), "f": name})
        finally:
            try:
                self.cdp.send("Page.screencastFrameAck", {"sessionId": f["sessionId"]})
            except Exception:
                pass

    def start(self):
        self.cdp.on("Page.screencastFrame", self._on_frame)
        self.t0 = time.time()
        self.cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 92,
            "maxWidth": int(self.vp["width"] * self.vp["dpr"]),
            "maxHeight": int(self.vp["height"] * self.vp["dpr"]),
            "everyNthFrame": 1})

    def stop(self):
        self.duration = self.now()
        try:
            self.cdp.send("Page.stopScreencast")
        except Exception:
            pass

    def log_cursor(self, x, y):
        self.cursor.append([round(self.now(), 4), round(x, 1), round(y, 1)])

    def log_click(self, x, y):
        self.clicks.append([round(self.now(), 4), round(x, 1), round(y, 1)])

    def log_focus(self, box, scale, hold_ms, ease_ms):
        t = self.now()
        self.focus.append({"t0": round(t, 3), "t1": round(t + hold_ms / 1000, 3),
                           "ease": ease_ms / 1000, "scale": float(scale),
                           "box": [box["x"], box["y"], box["width"], box["height"]]})

    def mark(self, op, arg):
        self.marks.append([round(self.now(), 3), op, str(arg)[:60]])

    def save(self):
        write_json(self.dir / "timeline.json", {
            "viewport": self.vp, "duration": round(self.duration, 3),
            "frames": self.frames, "cursor": self.cursor, "clicks": self.clicks,
            "focus": self.focus, "marks": self.marks})


def per_target(value, tname):
    """Compare beats may give start/setup/actions per target: {before: [...], after: [...]}."""
    if isinstance(value, dict) and tname in value:
        return value[tname]
    if isinstance(value, dict) and set(value) & {"before", "after"}:
        return None
    return value


def record(sb, beat_ids=None, headed=False, only_missing=False):
    from playwright.sync_api import sync_playwright
    beats = [b for b in sb.beats if b["type"] in ("app", "compare")]
    if beat_ids:
        beats = [b for b in beats if b["id"] in beat_ids]
        if not beats:
            die(f"no app/compare beats match {beat_ids}")
    if only_missing:
        beats = [b for b in beats
                 if any(not (sb.take_dir(b["id"], t) / "timeline.json").exists() for t in sb.beat_targets(b))]
    if not beats:
        info("nothing to record")
        return
    with sync_playwright() as p:
        browser = _launch(p, headed)
        for beat in beats:
            vp = sb.viewport(beat)
            for tname in sb.beat_targets(beat):
                t = sb.target(tname)
                if sb.app.get("login") and not sb.auth_path(tname).exists():
                    info(f"  (no saved login for {tname}; run `reel login` first if pages need auth)")
                ctx = _context(browser, sb, vp, tname)
                page = ctx.new_page()
                cdp = ctx.new_cdp_session(page)
                setup = Runner(page, None, vp, t["url"], recording=False)
                start = per_target(beat.get("start"), tname)
                if start:
                    setup.a_goto(start)
                for a in per_target(beat.get("setup"), tname) or []:
                    setup.run(expand_env(a))
                take = Take(sb.take_dir(beat["id"], tname), cdp, vp)
                take.start()
                runner = Runner(page, take, vp, t["url"], recording=True)
                page.mouse.move(*runner.cursor)
                runner._wait(int(beat.get("lead_ms", 350)))
                try:
                    for a in per_target(beat.get("actions"), tname) or []:
                        runner.run(expand_env(a))
                except SystemExit:
                    raise
                except Exception as e:
                    shot = take.dir / "failed.png"
                    page.screenshot(path=str(shot))
                    take.stop()
                    take.save()
                    browser.close()
                    die(f"beat '{beat['id']}' on {tname} failed at {take.marks[-1] if take.marks else 'start'}: "
                        f"{str(e).splitlines()[0]}\n  screenshot: {shot}")
                runner._wait(int(beat.get("tail_ms", 600)))
                take.stop()
                take.save()
                info(f"recorded {beat['id']} [{tname}] {take.duration:.1f}s, {len(take.frames)} frames")
                ctx.close()
        browser.close()
