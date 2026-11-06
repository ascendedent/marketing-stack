# Social Analyst for claude.ai (web, desktop, mobile)

Download `social-analyst-claude.zip` from `web/dist/` in this repo. Unzip it.

You need a paid Claude plan for Skills, Projects and custom connectors (menu names below are current
as of late 2026; Anthropic moves them occasionally).

## 1. Turn on code execution
Settings → **Capabilities** → enable **Code execution and file creation** (needed to run the report).

## 2. Add the skill (recommended)
Settings → **Capabilities** → **Skills** → **Upload skill** → choose `social-analyst-skill.zip`.
Claude now loads the analyst automatically whenever you ask about your social accounts.

*Alternative (no Skills):* create a **Project** → paste `project-instructions.md` into the Project
instructions → upload everything in `project-files/` to the Project knowledge.

## 3. Connect Buffer (optional but best)
Settings → **Connectors** → **Add custom connector** → URL `https://mcp.buffer.com/mcp` → **Connect** →
sign in to Buffer. (On Team/Enterprise plans an owner adds it under Organization settings first.)
In a chat, make sure the Buffer connector is toggled on in the tools menu.

If your posts come back without numbers, the connector's sign-in doesn't include analytics. Upload
analytics exports instead (the analyst tells you how for each platform).

## 4. Make a Project per account
Create a Project named after the account (e.g. "Acme — social"). Start a chat in it and say
**"set up a new account with me"**. At the end the analyst gives you a filled-in account profile —
add it to the Project's knowledge. Do the same with the "Learnings" blocks it writes after sessions,
so every new chat in that Project starts informed.

## 5. Use it
- "How did my posts do this month?" (it pulls from Buffer or asks for an export)
- "What's working — and what should I stop?"
- "Plan next week's posts" → it can file them in Buffer as Ideas/drafts for you to approve
- Video: it hands you a prompt for gemini.google.com; paste Gemini's breakdown back in.

## Compared with the full (local) version
No automatic daily history, no YouTube/Instagram/TikTok/X/LinkedIn deep connectors, no built-in
video download + Gemini. For those, run the main repo with Claude Code on your computer (see the
repo README). Everything you set up here (profile, learnings) carries over as text.
