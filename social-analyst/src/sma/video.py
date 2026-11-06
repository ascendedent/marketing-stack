"""Download a social video and get a structured breakdown from Gemini.

Flow: yt-dlp -> data/media/<service>__<id>.mp4 -> Gemini Files API (wait until ACTIVE) ->
generate_content with a JSON schema -> cached in video_analyses + accounts/<slug>/videos/<key>.{json,md}.

- Public YouTube URLs can be passed straight to Gemini (no download) with `--direct`.
- TikTok / Reels / X must be downloaded first (Gemini can't fetch them).
- Short social clips: sample at 2-4 fps (GEMINI_VIDEO_FPS) so the first 3 seconds get real coverage.
- Model id is env-configurable (GEMINI_VIDEO_MODEL) because Gemini ids churn; 2.5-era ids retire 2026-12-01.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

from . import config, store
from .discover import detect_service


class Scene(BaseModel):
    start: str = Field(description="MM:SS")
    end: str = Field(description="MM:SS")
    visual: str = Field(description="What is on screen: subject, action, setting, camera move/framing")
    on_screen_text: str | None = Field(None, description="Verbatim text overlays / captions")
    audio: str | None = Field(None, description="Speech (verbatim if short), VO, music, SFX")
    purpose: str = Field(description="Role in the edit: hook, setup, proof, demo, payoff, CTA, filler...")


class Hook(BaseModel):
    first_frame: str = Field(description="Exactly what the first frame shows")
    first_3s: str = Field(description="What happens in 0:00-0:03, visual + audio + text")
    hook_type: str = Field(description="e.g. pattern interrupt, question, bold claim, result-first, curiosity gap, POV, problem callout")
    strength_1_10: int
    why: str


class VideoBreakdown(BaseModel):
    summary: str = Field(description="One-paragraph plain description of the video")
    format: str = Field(description="e.g. talking head, voiceover b-roll, skit, tutorial, slideshow, UGC testimonial, meme, vlog")
    duration_s: float | None = None
    aspect_ratio: str | None = None
    hook: Hook
    scenes: list[Scene]
    transcript: str | None = Field(None, description="Spoken words, verbatim, with [MM:SS] markers")
    music: str | None = Field(None, description="Music/sound: genre, mood, trending-audio guess, where it changes")
    pacing: str = Field(description="Cut frequency (approx cuts per 10s), energy curve, dead spots with timestamps")
    on_screen_text_style: str | None = None
    people: str | None = Field(None, description="Who appears, how many, delivery style (no identification of real people)")
    branding: str | None = Field(None, description="Logos, product shots, brand mentions and when")
    cta: str | None = Field(None, description="Explicit/implicit call to action and timestamp")
    retention_risks: list[str] = Field(description="Moments likely to lose viewers, with timestamps and reason")
    what_works: list[str]
    improvements: list[str] = Field(description="Concrete, specific edits that would likely improve performance")
    replicable_pattern: str = Field(description="The reusable template of this video in one or two sentences")
    tags: list[str] = Field(description="Short lowercase descriptors for clustering (topic, format, hook type, tone)")


PROMPT = """You are a short-form social video analyst. Break this video down precisely.
Use MM:SS timestamps. Be literal about what is seen and heard; do not guess at things you cannot see.
Focus hardest on the first 3 seconds (hook) and on where attention would drop.
{context}
Return JSON matching the schema."""


def download(url: str, max_height: int = 720) -> Path:
    import yt_dlp
    config.MEDIA.mkdir(parents=True, exist_ok=True)
    tmpl = str(config.MEDIA / f"{detect_service(url)}__%(id)s.%(ext)s")
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "outtmpl": tmpl, "merge_output_format": "mp4",
            "format": f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]/b[height<={max_height}]/bv*+ba/b"}
    if cookies := config.env("YTDLP_COOKIES_FROM_BROWSER"):
        opts["cookiesfrombrowser"] = (cookies,)
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
        path = Path(y.prepare_filename(info)).with_suffix(".mp4")
    if not path.exists():
        cands = sorted(config.MEDIA.glob(f"{detect_service(url)}__{info['id']}.*"))
        if not cands:
            raise RuntimeError(f"download produced no file for {url}")
        path = cands[0]
    return path


def _key(source: str) -> str:
    p = Path(source)
    if p.exists():
        return "file:" + hashlib.sha1(p.read_bytes()).hexdigest()[:16]
    return f"{detect_service(source)}:{hashlib.sha1(source.encode()).hexdigest()[:16]}"


def analyze(source: str, *, account: str | None = None, post_id: str | None = None, context: str = "",
            direct: bool = False, force: bool = False, keep_media: bool = True) -> dict:
    """`source` is a URL or a local file path."""
    from google import genai
    from google.genai import types

    key = _key(source)
    db = store.connect()
    if not force and (row := db.execute("SELECT analysis FROM video_analyses WHERE key=?", (key,)).fetchone()):
        return {"cached": True, "key": key, **json.loads(row["analysis"])}

    api_key = config.secret("GEMINI_API_KEY") or config.secret("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY missing — get one at https://aistudio.google.com/apikey and put it in .env")
    client = genai.Client(api_key=api_key)
    model = config.env("GEMINI_VIDEO_MODEL")
    meta = types.VideoMetadata(fps=float(config.env("GEMINI_VIDEO_FPS")))

    uploaded = None
    if direct and detect_service(source) == "youtube":
        part = types.Part(file_data=types.FileData(file_uri=source, mime_type="video/mp4"), video_metadata=meta)
    else:
        path = Path(source) if Path(source).exists() else download(source)
        uploaded = client.files.upload(file=str(path))
        while uploaded.state and uploaded.state.name == "PROCESSING":
            time.sleep(3)
            uploaded = client.files.get(name=uploaded.name)
        if uploaded.state and uploaded.state.name == "FAILED":
            raise RuntimeError(f"Gemini could not process {path.name}")
        part = types.Part(file_data=types.FileData(file_uri=uploaded.uri, mime_type=uploaded.mime_type), video_metadata=meta)
        if not keep_media and not Path(source).exists():
            path.unlink(missing_ok=True)

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[types.Content(role="user", parts=[part, types.Part(text=PROMPT.format(
                context=f"Context from the account owner: {context}" if context else ""))])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=VideoBreakdown.model_json_schema(),
                media_resolution=config.env("GEMINI_MEDIA_RESOLUTION"),
                temperature=0.2,
            ),
        )
    except Exception as e:  # surface model-id problems clearly; never echo the key
        raise RuntimeError(config.redact(f"Gemini call failed ({model}): {e}")) from None
    finally:
        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass

    result = VideoBreakdown.model_validate_json(resp.text).model_dump()
    usage = getattr(resp, "usage_metadata", None)
    record = {"source": source, "model": model, "analysis": result,
              "tokens": getattr(usage, "total_token_count", None), "created_at": store.now()}
    db.execute("INSERT OR REPLACE INTO video_analyses VALUES (?,?,?,?,?,?,?)",
               (key, account, source, post_id, model, record["created_at"], json.dumps(record)))
    db.commit()
    if account:
        d = config.account_dir(account) / "videos"
        d.mkdir(exist_ok=True)
        stem = key.replace(":", "__")
        (d / f"{stem}.json").write_text(json.dumps(record, indent=2))
        (d / f"{stem}.md").write_text(to_markdown(record))
        record["saved_to"] = str((d / f"{stem}.md").relative_to(config.ROOT))
    return {"cached": False, "key": key, **record}


def to_markdown(rec: dict) -> str:
    a = rec["analysis"]
    h = a["hook"]
    lines = [f"# Video breakdown", f"Source: {rec['source']}  ·  model `{rec['model']}`  ·  {rec['created_at']}", "",
             a["summary"], "", f"**Format:** {a['format']}  ·  **Duration:** {a.get('duration_s')}s  ·  **Aspect:** {a.get('aspect_ratio')}",
             "", "## Hook", f"- First frame: {h['first_frame']}", f"- 0–3s: {h['first_3s']}",
             f"- Type: {h['hook_type']} · strength {h['strength_1_10']}/10 — {h['why']}", "",
             "## Scenes", "| time | visual | text | audio | role |", "|---|---|---|---|---|"]
    lines += [f"| {s['start']}–{s['end']} | {s['visual']} | {s.get('on_screen_text') or ''} | {s.get('audio') or ''} | {s['purpose']} |"
              for s in a["scenes"]]
    for title, k in [("Pacing", "pacing"), ("Music", "music"), ("CTA", "cta"), ("Branding", "branding"), ("Pattern", "replicable_pattern")]:
        if a.get(k):
            lines += ["", f"## {title}", a[k]]
    for title, k in [("Retention risks", "retention_risks"), ("What works", "what_works"), ("Improvements", "improvements")]:
        lines += ["", f"## {title}"] + [f"- {x}" for x in a[k]]
    if a.get("transcript"):
        lines += ["", "## Transcript", a["transcript"]]
    lines += ["", "Tags: " + ", ".join(a["tags"])]
    return "\n".join(lines)
