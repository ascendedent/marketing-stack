#!/usr/bin/env python3
"""reel: script + storyboard + voiceover -> vertical build-in-public video.

  reel check   STORYBOARD            validate and print the plan
  reel up      STORYBOARD            worktrees + dev servers for each target
  reel login   STORYBOARD            sign in with the test account, save session
  reel inspect STORYBOARD --target after --path /dashboard
                                     list clickable elements + selectors
  reel record  STORYBOARD [--beat id]   record app/compare beats
  reel take    STORYBOARD --beat id --target after   contact sheet of one take
  reel align   STORYBOARD            fit beats to the voiceover
  reel compose STORYBOARD [--draft]  render the MP4
  reel sheet   STORYBOARD            contact sheet of the rendered MP4
  reel render  STORYBOARD [--draft]  record missing takes + align + compose + sheet
  reel down    STORYBOARD [--clean]  stop servers (and remove worktrees)

Route B (finish in Descript or another editor):
  reel export  STORYBOARD            editor package: beat clips, raw takes, VO, SRT, plan,
                                     Descript import payload and Underlord prompt
  reel descript STORYBOARD [--dry-run]   upload the package as a Descript project (API token)
  reel descript-put STORYBOARD --urls upload_urls.json   upload bytes for an MCP import
  reel descript-polish STORYBOARD [--yes] [--model auto]  Underlord caption pass (AI credits)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import Storyboard, die, info, validate  # noqa: E402


def cmd_check(sb, a):
    errs = validate(sb)
    info(f"{sb.title}: {len(sb.beats)} beats, voiceover {sb.voiceover.name if sb.voiceover else '?'}")
    for name in sb.targets:
        t = sb.target(name)
        info(f"  target {name:<8} {t.get('branch', '(running)'):<24} {t['url']}")
    for b in sb.beats:
        extra = ""
        if b.get("type") in ("app", "compare"):
            acts = b.get("actions") or []
            n = sum(len(v) for v in acts.values()) if isinstance(acts, dict) else len(acts)
            extra = f"[{', '.join(sb.beat_targets(b))}] {n} actions"
        info(f"  {b.get('id', '?'):<16} {b.get('type', '?'):<8} {extra:<28} {(b.get('say') or '')[:50]}")
    if errs:
        info("\nproblems:")
        for e in errs:
            info(f"  - {e}")
        sys.exit(1)
    info("\nok")


def main():
    ap = argparse.ArgumentParser(prog="reel", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name):
        p = sub.add_parser(name)
        p.add_argument("storyboard")
        return p

    add("check")
    p = add("up")
    p.add_argument("--target", action="append")
    p = add("down")
    p.add_argument("--clean", action="store_true", help="also remove the worktrees")
    p = add("login")
    p.add_argument("--target", action="append")
    p.add_argument("--headed", action="store_true")
    p = add("inspect")
    p.add_argument("--target", required=True)
    p.add_argument("--path", default="/")
    p.add_argument("--beat", help="use this beat's viewport")
    p.add_argument("--headed", action="store_true")
    p = add("record")
    p.add_argument("--beat", action="append")
    p.add_argument("--headed", action="store_true")
    p.add_argument("--missing", action="store_true", help="only beats without a take")
    p = add("take")
    p.add_argument("--beat", required=True)
    p.add_argument("--target", required=True)
    p = add("align")
    p.add_argument("--model", help="faster-whisper model (default base.en)")
    p = add("compose")
    p.add_argument("--draft", action="store_true", help="half size, fast encode")
    p.add_argument("--out")
    p = add("sheet")
    p.add_argument("--video")
    p.add_argument("--n", type=int, default=12)
    p = add("render")
    p.add_argument("--draft", action="store_true")
    p.add_argument("--rerecord", action="store_true")
    p = add("export")
    p.add_argument("--draft", action="store_true")
    p = add("descript")
    p.add_argument("--dry-run", action="store_true")
    p = add("descript-put")
    p.add_argument("--urls", required=True, help="JSON file with the upload_urls map from import_media")
    p = add("descript-polish")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--model", default="auto")
    p.add_argument("--prompt", help="prompt file (default: package underlord-prompt.md)")
    a = ap.parse_args()

    sb = Storyboard(a.storyboard)
    if a.cmd == "check":
        return cmd_check(sb, a)
    if a.cmd in ("record", "align", "compose", "render", "export"):
        errs = validate(sb)
        if errs:
            die("storyboard problems:\n  - " + "\n  - ".join(errs))
    if a.cmd == "up":
        import servers
        servers.up(sb, a.target)
    elif a.cmd == "down":
        import servers
        servers.down(sb, a.clean)
    elif a.cmd == "login":
        import record
        record.login(sb, a.target, a.headed)
    elif a.cmd == "inspect":
        import record
        beat = next((b for b in sb.beats if b.get("id") == a.beat), None)
        record.inspect(sb, a.target, a.path, a.headed, beat)
    elif a.cmd == "record":
        import record
        record.record(sb, a.beat, a.headed, a.missing)
    elif a.cmd == "take":
        import sheet
        sheet.take_sheet(sb, a.beat, a.target)
    elif a.cmd == "align":
        import align
        align.align(sb, a.model)
    elif a.cmd == "compose":
        import compose
        compose.compose(sb, a.draft, a.out)
    elif a.cmd == "sheet":
        import sheet
        video = a.video or (sb.dir / "out" / f"{sb.slug}.mp4")
        if not Path(video).exists():
            draft = sb.dir / "out" / f"{sb.slug}.draft.mp4"
            video = draft if draft.exists() else video
        sheet.video_sheet(sb, video, a.n)
    elif a.cmd == "render":
        import align
        import compose
        import record
        import sheet
        record.record(sb, None, False, only_missing=not a.rerecord)
        align.align(sb)
        out = compose.compose(sb, a.draft)
        sheet.video_sheet(sb, out)
    elif a.cmd == "export":
        import export
        export.export(sb, a.draft)
    elif a.cmd == "descript":
        import descript
        descript.upload(sb, a.dry_run)
    elif a.cmd == "descript-put":
        import json as _json

        import descript
        data = _json.loads(Path(a.urls).read_text())
        descript.put_uploads(sb.dir / "out" / f"{sb.slug}-package", data.get("upload_urls", data))
    elif a.cmd == "descript-polish":
        import descript
        descript.polish(sb, a.prompt, a.model, a.yes)


if __name__ == "__main__":
    main()
