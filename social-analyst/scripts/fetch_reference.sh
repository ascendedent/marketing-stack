#!/usr/bin/env bash
# Shallow-clone third-party repos we borrow from into reference/ (gitignored).
# These are READ-ONLY reference material: never run their code from this repo.
# Re-run any time to refresh (it pulls existing clones).
set -uo pipefail
cd "$(dirname "$0")/../reference"
REPOS=(
  # owned-account analytics MCPs
  conorbronsdon/yt-analytics-mcp          # YouTube Analytics: retention, traffic, episode race  [CLONE-grade]
  adilsonicjunior/youtube-analytics-mcp   # YouTube Reporting API impressions/CTR (reach-service.ts)
  modbender/youtube-analytics-mcp         # unrestricted YT queries + write-to-file pattern
  sskghub/instagram-analytics-mcp         # Reels completion rate via ffprobe          [CLONE-grade]
  adelaidasofia/instagram-mcp             # Instagram Graph API, 29 tools, multi-acct  [CLONE-grade]
  BilalTariq01/instagram-analytics-mcp    # IG/FB insight analysis prompts (src/prompts.ts)
  aryaminus/socials-assistant             # multi-platform connectors + SQLite vault + TikTok CSV import
  joeswann/threads-mcp                    # Threads insights
  xdevplatform/xmcp                       # official X API MCP (paid X API)
  # analysis skills / formulas
  borghei/Claude-Skills                   # marketing/social-media-analyzer: fixed-formula metrics
  social-media-skills/skills              # 106 SMM skills (also installed as a Claude plugin)
  charlie947/social-media-skills          # analytics-dashboard, post-scorer, niche-research
  coreyhaines31/marketingskills           # performance-report and other marketing skills
  anthropics/knowledge-work-plugins       # marketing/skills/performance-report
  Virlo-AI/Virlo-Agent-Plugin             # trend-scout command + cost-quote eval pattern
  XPOZpublic/xpoz-agent-skills            # social listening / sentiment prompts
  # profile discovery
  apify/agent-skills                      # apify-ultimate-scraper social-media-analytics workflow
  # video understanding
  jordanrendric/claude-video-vision       # frame extraction + audio analysis plugin
  u2n4/video-url-analyzer-mcp             # yt-dlp + Gemini + FastMCP (same pattern as sma video)
  Galbaz1/video-research-mcp              # Gemini video research MCP
  DeepAleph/jevreel                       # contact-sheet video tools
)
for r in "${REPOS[@]}"; do
  dir="${r//\//__}"
  if [[ -d "$dir/.git" ]]; then
    git -C "$dir" pull -q --ff-only && echo "updated $r" || echo "FAILED pull $r"
  else
    GIT_TERMINAL_PROMPT=0 git clone -q --depth 1 "https://github.com/$r.git" "$dir" && echo "cloned  $r" || echo "FAILED  $r"
  fi
done
