@AGENTS.md

## Claude Code notes
- The SessionStart hook (`.claude/settings.json`) already ran `scripts/session_start.sh`; its output
  is in your context. If it lists pending steps, follow the `setup` skill before anything else.
- Skills are in `.claude/skills` (a symlink to `.agents/skills`, shared with Codex and Grok).
- `.mcp.json` is read automatically; approve `social-analyst`, `buffer`, `apify` when prompted. Start
  via `scripts/agent.sh claude` so `.env` is exported for the MCP auth headers. Buffer's MCP can also
  use OAuth: `claude mcp add --transport http buffer https://mcp.buffer.com/mcp`, then `/mcp`.
- If the owner pastes something in chat that looks like a key, don't echo it back; store it with
  `printf '%s' '…' | uv run sma setup set-key NAME` and suggest rotating it.
