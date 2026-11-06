"""Contact sheets: a grid of frames from the output (or a raw take) to review."""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import ffprobe_duration, find_font, info, read_json


def video_sheet(sb, video, n=12, cols=4, out=None):
    video = Path(video)
    dur = ffprobe_duration(video)
    times = [dur * (i + 0.5) / n for i in range(n)]
    al = read_json(sb.work / "align.json", {})
    rows = al.get("beats", [])
    thumbs = []
    tmp = sb.work / "sheet"
    tmp.mkdir(exist_ok=True)
    for i, t in enumerate(times):
        p = tmp / f"f{i:02d}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video),
                        "-frames:v", "1", "-vf", "scale=270:-2", str(p)], check=True)
        beat = next((r["id"] for r in rows if r["start"] <= t < r["end"]), "")
        thumbs.append((Image.open(p).convert("RGB"), f"{t:5.1f}s {beat}"))
    return _grid(sb, thumbs, cols, out or (sb.dir / "out" / f"{sb.slug}.sheet.png"))


def take_sheet(sb, beat_id, target, n=8, cols=4, out=None):
    d = sb.take_dir(beat_id, target)
    tl = read_json(d / "timeline.json")
    frames = tl["frames"]
    pick = [frames[int(i * (len(frames) - 1) / max(1, n - 1))] for i in range(n)]
    thumbs = []
    for f in pick:
        im = Image.open(d / "frames" / f["f"]).convert("RGB")
        im.thumbnail((420, 420))
        thumbs.append((im, f"{f['t']:.1f}s"))
    return _grid(sb, thumbs, cols, out or (sb.work / f"take-{beat_id}-{target}.png"))


def _grid(sb, thumbs, cols, out):
    w = max(t[0].width for t in thumbs)
    h = max(t[0].height for t in thumbs) + 30
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w + (cols + 1) * 8, rows * h + (rows + 1) * 8), (24, 24, 28))
    font = ImageFont.truetype(find_font("bold", sb.style), 18)
    d = ImageDraw.Draw(sheet)
    for i, (im, label) in enumerate(thumbs):
        x = 8 + (i % cols) * (w + 8)
        y = 8 + (i // cols) * (h + 8)
        sheet.paste(im, (x, y))
        d.text((x + 4, y + im.height + 4), label, font=font, fill=(220, 220, 220))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    info(f"contact sheet: {out}")
    return out
