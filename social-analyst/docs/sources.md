# Sources — what we evaluated, what we took

Checked 2026-11-03. Clones live in `reference/` (`scripts/fetch_reference.sh`), read-only.
"Took" = ported into `src/sma`, copied into `knowledge/`, or adopted as a pattern.

## On the original list
| item | repo | verdict | took |
|---|---|---|---|
| yt-analytics-mcp | conorbronsdon/yt-analytics-mcp | port when YouTube depth is needed | — (retention curve, traffic sources, "episode race" = compare videos at equal age) |
| youtube-analytics-mcp | modbender/… · adilsonicjunior/… | reference | write-large-results-to-file idea; Reporting-API impressions/CTR (`reach-service.ts`) |
| instagram-analytics-mcp | sskghub/… · BilalTariq01/… | reference | Reels completion rate = avg watch time ÷ duration (ffprobe); analysis prompts |
| Socials Assistant | aryaminus/socials-assistant | pattern | snapshot store design (long-format metrics per snapshot), weekly-digest shape, "missing ≠ zero" |
| Metricool MCP | hosted ai.metricool.com/mcp | optional add-on | listed in buffer-setup §10 for account-level metrics |
| Coupler.io MCP | hosted | skip | paid ETL middleman |
| Virlo MCP | Virlo-AI/Virlo-Agent-Plugin | reference | "quote cost before spending" rule for paid tools |
| Apify content analytics | apify/agent-skills | use via Apify MCP | competitor/profile scraping; cost-cap rule |
| Claude skills for SMM | anthropics/knowledge-work-plugins, coreyhaines31/marketingskills | reference | performance-report shape |
| borghei social-media-analyzer | borghei/Claude-Skills | took | deterministic metrics principle; `knowledge/analytics/platform-benchmarks.md` |
| Social Media Skills | social-media-skills/skills | took | METER, NORTH, audit, SCOUT, viral deconstruction, test framework, brand/voice/audience templates → `knowledge/` |

## Added
| repo | why |
|---|---|
| Buffer official MCP (mcp.buffer.com) | publishing + metrics in chat clients; `.mcp.json` |
| adelaidasofia/instagram-mcp | best base if you add Instagram Graph API insights (29 tools, multi-account) |
| xdevplatform/xmcp | official X API MCP, if X depth is needed (paid API) |
| joeswann/threads-mcp | Threads insights |
| charlie947/social-media-skills | post-scorer, hook-generator → `knowledge/writing/` |
| XPOZpublic/xpoz-agent-skills | social-listening prompts (reference) |
| jordanrendric/claude-video-vision, u2n4/video-url-analyzer-mcp, Galbaz1/video-research-mcp, DeepAleph/jevreel | video pipeline patterns; ours is `src/sma/video.py` |
| yt-dlp, instaloader, gallery-dl, twscrape | discovery (yt-dlp built in; instaloader optional extra) |

## Ported
| port | from | where |
|---|---|---|
| YouTube Analytics: per-video watch time/avg view %, retention points, daily trend, traffic, demographics | conorbronsdon/yt-analytics-mcp, aryaminus/socials-assistant | `src/sma/connectors/youtube.py` |
| Instagram Graph insights, Reels completion via ffprobe, metric-drift tolerance, demographics, business_discovery | adelaidasofia/instagram-mcp, sskghub/instagram-analytics-mcp, aryaminus/socials-assistant | `src/sma/connectors/instagram.py` |
| TikTok Studio export import (fuzzy headers, CSV/XLSX) | aryaminus/socials-assistant `importers/tiktok-csv.ts` | `src/sma/connectors/tiktok_import.py` |
| YouTube thumbnail impressions + CTR (Reporting API job, report ingestion, host-pinned download) | adilsonicjunior/youtube-analytics-mcp `reach-service.ts` (fixed: rows are now summed per video/day, not overwritten) | `youtube.py: sync_reach` |
| Threads post + account insights, token refresh | joeswann/threads-mcp | `src/sma/connectors/threads.py` |
| X owned metrics (non_public within 30 days) | X API v2 docs; xdevplatform/xmcp for reference | `src/sma/connectors/x.py` |
| LinkedIn member post analytics + Page share/follower statistics | LinkedIn Community Management API docs (2026-10) | `src/sma/connectors/linkedin.py` |
All write into the same `posts` / `post_metrics` / `account_metrics` tables, merging into the Buffer
post when one links to the same native post, so `sma report` sees everything.

## Not covered (Buffer's analytics are the source)
Facebook Pages, Pinterest, Mastodon, Bluesky (Bluesky has no analytics anywhere), Google Business, Substack.
