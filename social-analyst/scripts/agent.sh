#!/usr/bin/env bash
# Launch an agent CLI in this project with .env exported, so MCP configs that read
# ${BUFFER_API_KEY} / bearer_token_env_var see the keys.  Usage: scripts/agent.sh claude|codex|grok [args…]
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -f .env ]]; then set -a; source .env; set +a; fi
# *_FILE keys → export the value for MCP headers (the sma CLI reads *_FILE itself)
for v in BUFFER_API_KEY APIFY_TOKEN; do
  f="${v}_FILE"
  if [[ -z "${!v:-}" && -n "${!f:-}" ]]; then export "$v"="$(grep -v '^#' "${!f/#\~/$HOME}" | head -1 | sed 's/^[A-Za-z_][A-Za-z0-9_]*=//')"; fi
done
python3 scripts/sync_mcp.py >/dev/null
exec "${1:-claude}" "${@:2}"
