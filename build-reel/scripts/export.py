"""Editor package: the reel as separate, editable pieces.

out/<slug>-package/
  beats/NN-<id>.mp4       one 1080x1920 clip per beat, no captions, carrying its
                          slice of the voiceover (laid end to end = the reel)
  raw/<id>-<target>.mp4   clean browser recordings at real speed (no frame, no cursor)
  voiceover.<ext>         the original VO file
  reel-nocaptions.mp4     the whole reel without captions
  captions.srt            captions with script spelling and VO timing
  plan.md / plan.json     beat table: in/out, file, VO line
  descript-import.json    ready payload for Descript's import (API or MCP)
  underlord-prompt.md     optional Descript polish pass (captions in your style)

Any editor can use it: Descript (route B in SKILL.md), CapCut web, DaVinci
Resolve, Kdenlive.
"""
import json
import mimetypes
import shutil
import subprocess
from pathlib import Path

from common import die, info, read_json, write_json

MIME = {".mp4": "video/mp4", ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
        ".aac": "audio/aac", ".flac": "audio/flac", ".mov": "video/quicktime"}


def _enc():
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    if " libx264 " in out:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p"]
    if " libopenh264 " in out:
        return ["-c:v", "libopenh264", "-b:v", "16M", "-pix_fmt", "yuv420p"]
    return ["-c:v", "mpeg4", "-q:v", "2", "-pix_fmt", "yuv420p"]


def _ts(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s - int(s)) * 1000)):03d}".replace(",1000", ",999")


def write_srt(words, rows, path, max_words=7):
    """Caption lines: break at sentence ends, pauses, beat cuts or max_words."""
    ends = [r["end"] for r in rows]
    lines, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        brk = (nxt is None or len(cur) >= max_words or w["w"][-1:] in ".!?;:"
               or nxt["s"] - w["e"] > 0.6 or any(w["s"] < e <= nxt["s"] + 0.05 for e in ends))
        if brk:
            lines.append(cur)
            cur = []
    with open(path, "w") as f:
        for n, ln in enumerate(lines, 1):
            end = ln[-1]["e"] + 0.15
            if n < len(lines):
                end = min(end, lines[n][0]["s"] - 0.02)
            f.write(f"{n}\n{_ts(ln[0]['s'])} --> {_ts(max(end, ln[0]['s'] + 0.3))}\n{' '.join(x['w'] for x in ln)}\n\n")
    return len(lines)


def raw_take(take_dir, out):
    """Frames + timestamps -> constant 30fps MP4 at real speed."""
    tl = read_json(Path(take_dir) / "timeline.json")
    frames = tl["frames"]
    lst = Path(take_dir) / "concat.txt"
    with open(lst, "w") as f:
        for i, fr in enumerate(frames):
            nxt = frames[i + 1]["t"] if i + 1 < len(frames) else tl["duration"]
            f.write(f"file 'frames/{fr['f']}'\nduration {max(0.001, nxt - fr['t']):.4f}\n")
        f.write(f"file 'frames/{frames[-1]['f']}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-vf", "fps=30,scale=trunc(iw/2)*2:trunc(ih/2)*2", *_enc(), str(out)], check=True)
    lst.unlink()


def export(sb, draft=False):
    import compose
    al = read_json(sb.work / "align.json")
    if not al:
        die("no alignment yet (run `reel align`)")
    pkg = sb.dir / "out" / f"{sb.slug}-package"
    if pkg.exists():
        shutil.rmtree(pkg)
    (pkg / "beats").mkdir(parents=True)
    (pkg / "raw").mkdir()

    full = pkg / "reel-nocaptions.mp4"
    info("rendering the reel without captions...")
    compose.compose(sb, draft=draft, out=full, captions_style="off")

    rows = al["beats"]
    enc = _enc()
    beat_files = []
    for n, (b, r) in enumerate(zip(sb.beats, rows), 1):
        name = f"{n:02d}-{b['id']}.mp4"
        # cut on frame boundaries so the clips add up to the reel exactly
        f0 = round(r["start"] * sb.fps)
        f1 = round(r["end"] * sb.fps)
        start, dur = f0 / sb.fps, (f1 - f0) / sb.fps
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.4f}", "-i", str(full),
                        "-t", f"{dur:.4f}", "-frames:v", str(f1 - f0), *enc, "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                        "-movflags", "+faststart", str(pkg / "beats" / name)], check=True)
        beat_files.append(name)
    info(f"  {len(beat_files)} beat clips")

    raws = []
    for b in sb.beats:
        if b["type"] not in ("app", "compare"):
            continue
        for t in sb.beat_targets(b):
            td = sb.take_dir(b["id"], t)
            if (td / "timeline.json").exists():
                name = f"{b['id']}-{t}.mp4"
                raw_take(td, pkg / "raw" / name)
                raws.append(name)
    info(f"  {len(raws)} raw takes")

    vo_ext = sb.voiceover.suffix.lower()
    shutil.copy2(sb.voiceover, pkg / f"voiceover{vo_ext}")
    n_caps = write_srt(al["words"], rows, pkg / "captions.srt")

    plan = []
    for n, (b, r, f) in enumerate(zip(sb.beats, rows, beat_files), 1):
        plan.append({"index": n, "id": b["id"], "type": b["type"], "file": f"beats/{f}",
                     "in": r["start"], "out": r["end"], "duration": round(r["end"] - r["start"], 3),
                     "say": b.get("say", ""), "heading": b.get("heading") or b.get("text")})
    write_json(pkg / "plan.json", {"title": sb.title, "canvas": [sb.width, sb.height], "fps": sb.fps,
                                   "total": al["total"], "beats": plan,
                                   "caption_style": sb.style["captions"].get("style"),
                                   "accent": sb.style["accent"]})
    md = [f"# {sb.title}", "", f"Canvas {sb.width}x{sb.height}, {al['total']:.1f}s, voiceover `voiceover{vo_ext}`", "",
          "| # | Beat | In | Out | Clip | VO line |", "|---|---|---|---|---|---|"]
    for p in plan:
        md.append(f"| {p['index']} | {p['id']} ({p['type']}) | {p['in']:.2f} | {p['out']:.2f} | {p['file']} | {p['say']} |")
    (pkg / "plan.md").write_text("\n".join(md) + "\n")

    # Descript import payload: beat clips (each with its VO slice) end to end on a 9:16 composition
    prefix = sb.slug
    add_media, clips = {}, []
    for f in beat_files:
        p = pkg / "beats" / f
        key = f"{prefix}-{f}"
        add_media[key] = {"content_type": MIME.get(p.suffix, "video/mp4"), "file_size": p.stat().st_size,
                          "local_path": f"beats/{f}"}
        clips.append({"media": key})
    write_json(pkg / "descript-import.json", {
        "project_name": f"{sb.title} (build-reel)",
        "add_media": add_media,
        "add_compositions": [{"name": sb.title, "width": sb.width, "height": sb.height, "clips": clips}],
        "_note": "local_path is for build-reel's uploader; strip it before sending to Descript.",
    })
    (pkg / "underlord-prompt.md").write_text(underlord_prompt(sb, plan, al["total"]))
    info(f"package: {pkg}  ({n_caps} caption lines)")
    return pkg


STYLE_WORDS = {
    "tiktok": "bold condensed all-caps words with a thick black outline, 3 to 5 words at a time, the spoken word highlighted in {accent}, a quick pop-in as each group appears",
    "bold": "heavy all-caps sans serif (Montserrat-like) with a black outline, 2 to 3 words at a time, the spoken word highlighted in {accent}, a springy pop-in",
    "bounce": "playful display font (Bangers-like), 1 to 2 words at a time, bouncy scale-in, alternating bright colors starting with {accent}",
    "clean": "Inter Bold in sentence case, white with a soft drop shadow, 3 to 5 words at a time, gentle fade-in, no color highlight",
    "pill": "bold sans serif, white with a black outline, 3 words at a time, the spoken word on a rounded {accent} highlight",
}


def underlord_prompt(sb, plan, total):
    style = sb.style["captions"].get("style") or "tiktok"
    look = STYLE_WORDS.get(style, STYLE_WORDS["tiktok"]).format(accent=sb.style["accent"])
    rows = "\n".join(f"| {p['index']} | {p['in']:6.2f} | {p['out']:6.2f} | {sb.slug}-{Path(p['file']).name} | \"{p['say'][:60]}\" |"
                     for p in plan)
    return f"""Edit ONLY the composition "{sb.title}" in this project. Do not create, duplicate or modify any other composition, and do not import, rename or delete media.

CURRENT STATE
- A finished {total:.1f}s vertical {sb.width}x{sb.height} video: {len(plan)} clips laid end to end, each with its own slice of the voiceover. The timing is final.

| # | In (s) | Out (s) | Clip | Spoken cue |
|--:|--:|--:|---|---|
{rows}

TASK
1. Add captions for the whole voiceover. Look: {look}.
2. Captions must use the exact spelling of the transcript (product names as written).
3. Place captions centered horizontally, just below the app footage in each clip, inside the vertical safe area (never in the bottom 20% of the frame, never covering the app window or the code card).

HARD RULES
- Keep every clip, cut, word and the total runtime exactly as they are. Do not remove filler words or pauses.
- Do not add music, sound effects, transitions, b-roll, stock media, layout packs, titles or text overlays other than the captions.
- Do not apply Studio Sound unless asked.

REPORT BACK
- The caption style you applied (font, size, colors, position) and any clip where captions could not avoid the footage.
"""
