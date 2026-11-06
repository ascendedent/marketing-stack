---
name: buffer-publishing
description: Rules and commands for every write to Buffer — Ideas on the Create board (default), draft posts, scheduled posts, media, platform limits, deletion, and when publishing is allowed. Use whenever creating, scheduling, queueing, drafting or deleting anything in Buffer, via the sma CLI, the sma MCP server, or the official Buffer MCP.
---

# Writing to Buffer

## Ladder of writes (go no further than the owner asked)
| step | command | what happens | needs |
|---|---|---|---|
| 1. Idea (default) | `sma idea <slug> --channel c --text …` | card on the Create board ("In Progress" column) | nothing |
| 2. Draft post | `sma post <slug> --channel c --text … [--at ISO]` | post saved as draft, not queued | nothing |
| 3. Queue / schedule | `sma post … --no-draft [--at ISO \| --next]` | will publish at the slot | owner OK for this post |
| 4. Publish now | `sma post … --now --yes` | goes live immediately | owner said "post it now" in this conversation |

`account.json → approval` can tighten this per account (e.g. `allow_queue: false`). Obey it.

## Before any write
1. Right account, right channel: one account's voice never goes on another's channel.
2. `sma posts <slug> --status sent --limit 10` (and `--status scheduled`) — don't duplicate or repeat a recent beat.
3. `--dry-run` first when anything is unusual. **Never create probe/test Ideas** — the public API
   cannot delete Ideas, so a test card is permanent clutter.

## Facts that bite
- Keys: personal API keys from publish.buffer.com/settings/api. The legacy REST API
  (`api.bufferapp.com`) rejects them. Door: `https://api.buffer.com` (GraphQL).
- Ideas: column is looked up by name (`--column`, default "In Progress"); missing column → stop and ask.
  Ideas accept images, **not video**. `updateIdea` replaces the whole content — resend title, text,
  services, date and media when editing. Tags: use existing tags only; orgs have a small tag cap.
- Media: Buffer fetches media itself. URLs must be public, direct, HTTPS, stable until publish time.
  Drive/Dropbox share links and expiring signed URLs fail. Use a public bucket (R2, S3, Cloudinary).
  Formats: jpeg, png, gif, mp4, mov, webm, pdf. There is no upload endpoint.
- Limits (sma refuses over-length text): LinkedIn 3,000 UTF-16 units with each URL = 24 and emoji/
  unicode-bold = 2; first comment 1,250. X 280. Threads 500. Bluesky 300. IG/TikTok 2,200.
- Daily posting limits per channel: `sma schedule-info <slug>`.
- Rate limits are per account across every key and MCP connection (free: 150 / 15 min). Don't loop
  writes; batch thoughtfully.
- `delete-post <id>` deletes posts (tries every login). Ideas can't be deleted via API — the owner
  removes them in the UI.

## Using the official Buffer MCP instead
Fine for browsing and one-off edits. Same rules: keep tool-approval prompts on, never call
`create_post` with `shareNow` without the explicit instruction, prefer `saveToDraft: true`.
