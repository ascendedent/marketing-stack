# Social Analyst for ChatGPT

Download `social-analyst-chatgpt.zip` from `web/dist/` in this repo. Unzip it.

Two ways to set it up. Use **A** for your own accounts (it can talk to Buffer); use **B** to share a
ready-made GPT with others (it works from uploaded exports). Menu names move around — these are
current as of late 2026.

## A. Project + Buffer (recommended)
1. Sidebar → **Projects → New project** (name it after the account).
2. Project settings → **Instructions** → paste all of `instructions.md`.
3. Project **Files** → upload everything in `files/`.
4. Connect Buffer (needs a plan with developer mode / custom connectors — Plus/Pro or a workspace
   where the admin allowed it): Settings → **Apps & Connectors** → **Advanced** → turn on
   **Developer mode** → **Create** → MCP server URL `https://mcp.buffer.com/mcp` → authentication
   **OAuth** → sign in to Buffer. In a chat, open **+ → Developer mode** and select Buffer.
   ChatGPT asks before each write action — keep those confirmations on.
5. Start a chat in the project: **"Set up a new account with me."** Save the profile it produces
   (and later "Learnings" blocks) into the project files.

If Buffer posts come back without numbers, the connector's sign-in doesn't include analytics —
upload analytics exports instead (the analyst explains how per platform).

## B. Custom GPT (shareable, exports only)
1. **Explore GPTs → Create → Configure**.
2. Name: "Social Analyst". Instructions: paste `instructions.md` (it fits the 8,000-character limit).
3. Conversation starters: from `conversation-starters.md`.
4. **Knowledge** → upload everything in `files/`.
5. Capabilities: **Code Interpreter & Data Analysis** ON (required), **Web Search** ON.
6. Save (Only me / Anyone with the link).
Custom GPTs can't use your Buffer connector, so this one works from exports you upload, and hands
posts back as copy-ready text.

## Use it
- "How did my posts do this month?" (upload exports or let it pull from Buffer)
- "What's working — and what should I stop?"
- "Plan next week's posts" → Buffer drafts (A) or copy-ready posts (B)
- Video: it gives you a prompt for gemini.google.com; paste Gemini's breakdown back in.

## Compared with the full (local) version
No automatic daily history and no deep platform connectors or built-in video pipeline. For those,
run the main repo with Codex CLI on your computer (`codex` in the repo folder).
