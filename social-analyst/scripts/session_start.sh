#!/usr/bin/env bash
# Prints the setup state for the agent at the start of every session.
# Claude Code runs it automatically (SessionStart hook in .claude/settings.json);
# AGENTS.md tells Codex / Grok / any other agent to run it first.
# Never fails the session: every problem becomes an instruction for the agent.
src="${BASH_SOURCE[0]}"; if [[ "$src" == */* ]]; then dir="${src%/*}"; else dir=.; fi
cd "$dir/.." || exit 0
say() { printf '%s\n' "$@"; }
if ! command -v uv >/dev/null 2>&1; then
  say "[social-analyst setup status]" \
      "✗ uv (Python package manager) is not installed, so the toolkit can't run yet." \
      "NEXT: ask the owner to allow installing uv: \`curl -LsSf https://astral.sh/uv/install.sh | sh\` (macOS: \`brew install uv\`; Windows: \`powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"\`), then re-run \`scripts/session_start.sh\`." \
      "Then follow the \`setup\` skill (.agents/skills/setup/SKILL.md)."
  exit 0
fi
if [ ! -x .venv/bin/python ] && [ ! -x .venv/Scripts/python.exe ]; then
  say "[social-analyst] first run: installing the toolkit (uv sync)…"
  if ! timeout 150 uv sync -q >/dev/null 2>&1; then
    say "✗ \`uv sync\` failed. NEXT: run \`uv sync\` and fix what it reports (network? Python 3.12+?), then follow the \`setup\` skill."
    exit 0
  fi
fi
timeout 40 uv run -q sma setup status --brief 2>/dev/null \
  || say "[social-analyst] status check failed. NEXT: run \`uv run sma setup status\` and read the error; follow the \`setup\` skill."
exit 0
