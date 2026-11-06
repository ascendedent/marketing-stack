# Social Analyst for Grok (grok.com)

Download `social-analyst-grok.zip` from `web/dist/` in this repo. Unzip it.

Grok's web features change often; these steps are current as of late 2026 — adapt names if they've moved.

## 1. Workspace
- If you have **Projects**: create one named after the account → paste `instructions.md` into its
  instructions → add everything in `files/` as project files.
- If not: start a chat, paste `instructions.md` as your first message, and attach the `files/`
  (at least `report.py`, `workflows.md`, `account-profile-template.md`). Keep using that chat, or
  repeat this each time.

## 2. Connect Buffer (optional but best)
grok.com → **Connectors** (or **Plugins**) → search **Buffer** → **Connect** → sign in to Buffer.
If Buffer isn't listed: **New connector → Custom** → `https://mcp.buffer.com/mcp` (custom connectors
need a paid Grok plan). If posts come back without numbers, the connector's sign-in doesn't include
analytics — upload exports instead.

## 3. Start
Say **"Set up a new account with me."** Save the profile it produces (and later "Learnings" blocks)
into the project files, or paste them at the start of new chats.

## Notes
- The report runs best with code execution. If Grok can't run `report.py`, it applies the same method
  by hand and tells you — numbers are then less exact; prefer smaller exports.
- Video: Grok gives you a prompt for gemini.google.com; paste Gemini's breakdown back in.
- Full version (daily history, deep connectors, video pipeline): run the main repo with the Grok CLI
  on your computer (`grok` in the repo folder).
