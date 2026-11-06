#!/usr/bin/env python3
"""Build the web edition bundles into web/dist/ from web/shared + knowledge/.

    python3 web/build.py            # rebuild
    python3 web/build.py --check    # exit 1 if web/dist is out of date (used by tests)

Outputs (all committed, so people can download them straight from GitHub):
  dist/social-analyst-claude.zip   → claude.ai: Skill zip + Project files
  dist/social-analyst-chatgpt.zip  → ChatGPT: Project / Custom GPT instructions + files
  dist/social-analyst-grok.zip     → Grok: Project instructions + files
  dist/<platform>/…                → the same content unzipped, for browsing on GitHub
Zips are deterministic (fixed timestamps, sorted entries) so rebuilding doesn't churn git.
"""

from __future__ import annotations

import io
import shutil
import sys
import zipfile
from pathlib import Path

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
SHARED = WEB / "shared"
DIST = WEB / "dist"
GPT_LIMIT = 8000

FRAMEWORKS = {  # bundle name → source in knowledge/
    "frameworks-metrics.md": "analytics/metrics-by-goal-and-report.md",
    "frameworks-meter.md": "analytics/meter-framework.md",
    "frameworks-benchmarks.md": "analytics/platform-benchmarks.md",
    "frameworks-hooks.md": "writing/hook-generator.md",
    "frameworks-post-scorer.md": "writing/post-scorer.md",
    "frameworks-experiments.md": "experiments/test-framework.md",
}

PLATFORM = {
    "claude": {
        "code_tool": "your code execution tool (the analysis/code environment; enable it in Settings → Capabilities)",
        "connector": "the Buffer connector (Settings → Connectors)",
    },
    "chatgpt": {
        "code_tool": "Code Interpreter / data analysis (it runs Python on uploaded files)",
        "connector": "the Buffer app/connector (developer mode), if it's enabled for this chat",
    },
    "grok": {
        "code_tool": "your code execution tool (if unavailable, apply report.py's method by hand and say so)",
        "connector": "the Buffer connector (grok.com → Connectors/Plugins → Buffer)",
    },
}

CLAUDE_SKILL_HEAD = """---
name: social-analyst
description: Social media analyst for the owner's own accounts — onboard an account (purpose, voice, audience, KPIs), review performance from the Buffer connector or uploaded analytics exports with a deterministic pattern report, interpret Gemini video breakdowns, plan content, and file posts as Buffer Ideas/drafts for approval. Use for "how are my posts doing", "what's working", "best time to post", "analyze my account", "plan next week's posts", "break down this video", or setting up a new social account.
---

"""


def instructions(platform: str) -> str:
    text = (SHARED / "instructions.md").read_text()
    p = PLATFORM[platform]
    text = text.replace("Run it with your code tool", f"Run it with {p['code_tool']}")
    text = text.replace("1. **Buffer connector** (if connected)", f"1. **Buffer connector**: {p['connector']}")
    return text


def files_for(platform: str) -> dict[str, bytes]:
    files = {
        "report.py": (SHARED / "report.py").read_bytes(),
        "workflows.md": (SHARED / "workflows.md").read_bytes(),
        "account-profile-template.md": (SHARED / "account-profile-template.md").read_bytes(),
        "video-breakdown-prompt.md": (SHARED / "video-breakdown-prompt.md").read_bytes(),
    }
    for name, src in FRAMEWORKS.items():
        files[name] = (ROOT / "knowledge" / src).read_bytes()
    return files


def bundle(platform: str) -> dict[str, bytes]:
    """path inside the platform folder → bytes"""
    out: dict[str, bytes] = {}
    instr = instructions(platform)
    files = files_for(platform)
    guide = (WEB / platform / "README.md").read_bytes()
    out["README.md"] = guide
    if platform == "claude":
        body = instr.replace("## Files you have", "## Files in this skill (references/ and scripts/)")
        skill = {"social-analyst/SKILL.md": (CLAUDE_SKILL_HEAD + body).encode(),
                 "social-analyst/scripts/report.py": files["report.py"]}
        for name, data in files.items():
            if name != "report.py":
                skill[f"social-analyst/references/{name}"] = data
        out["social-analyst-skill.zip"] = zipped(skill)
        out["project-instructions.md"] = instr.encode()
        for name, data in files.items():
            out[f"project-files/{name}"] = data
    else:
        if len(instr) > GPT_LIMIT:
            raise SystemExit(f"{platform} instructions are {len(instr)} chars > {GPT_LIMIT}")
        out["instructions.md"] = instr.encode()
        for name, data in files.items():
            out[f"files/{name}"] = data
        out["conversation-starters.md"] = (
            "- Set up a new account with me\n- How did my posts do this month?\n"
            "- What's working on my account — and what should I stop doing?\n"
            "- Plan next week's posts from what's working\n- Break down this video (Gemini result attached)\n").encode()
    return out


def zipped(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_STORED  # deterministic across Python/zlib versions
            z.writestr(info, files[name])
    return buf.getvalue()


def expected() -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for platform in PLATFORM:
        b = bundle(platform)
        for path, data in b.items():
            out[f"{platform}/{path}"] = data
        out[f"social-analyst-{platform}.zip"] = zipped({f"social-analyst-{platform}/{k}": v for k, v in b.items()})
    return out


def main() -> int:
    want = expected()
    if "--check" in sys.argv:
        have = {str(p.relative_to(DIST)): p.read_bytes() for p in DIST.rglob("*") if p.is_file()} if DIST.exists() else {}
        stale = sorted(set(want) ^ set(have) | {k for k in want if k in have and want[k] != have[k]})
        if stale:
            print("web/dist is out of date — run `python3 web/build.py`:\n  " + "\n  ".join(stale[:20]))
            return 1
        print("web/dist is up to date")
        return 0
    shutil.rmtree(DIST, ignore_errors=True)
    for path, data in want.items():
        f = DIST / path
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(data)
    for platform in PLATFORM:
        print(f"built dist/social-analyst-{platform}.zip  (instructions: {len(instructions(platform))} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
