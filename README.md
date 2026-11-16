# Marketing Stack

One folder that gives Claude Code, Codex or Grok a full marketing team: strategy, paid media, copy, creative, video, CRO, email, SEO, analytics and measurement. Open it in any of the three and the skills are available straight away.

Third-party skills are git submodules linked to their original repos, not copies, so you get updates from the authors and they keep credit.

## Install

```sh
git clone --recurse-submodules --shallow-submodules https://github.com/ascendedent/marketing-stack.git
cd marketing-stack
claude   # or: codex, grok
```

Trust the folder when asked. Grok skips project skills until you do. Skills are symlinks, so on Windows enable Developer Mode and set `git config --global core.symlinks true` before cloning.

## Use it with your agent

All three agents read the same skills, so there's nothing to convert or keep in sync.

| Agent | Reads skills from | Plugins |
|---|---|---|
| Claude Code | `.claude/skills/` | Offered automatically from `.claude/settings.json` |
| Codex | `.agents/skills/` | Install with the commands below |
| Grok | `.agents/skills/` | Install with the commands below |

The paid media, SEO and web design functions rely on plugins, and so does Descript. The LOTGEN plugin is what connects the `lotgen-*` skills to the service. Claude Code users don't need the commands below for the first four, only for LOTGEN:

```sh
/plugin marketplace add ascendedent/lotgen-skills
/plugin install lotgen@lotgen
```

**Codex**

```sh
codex plugin marketplace add AgriciDaniel/claude-ads
codex plugin marketplace add AgriciDaniel/claude-seo
codex plugin marketplace add pbakaus/impeccable
codex plugin marketplace add descriptinc/descript-mcp
codex plugin marketplace add ascendedent/lotgen-skills
codex plugin add claude-ads@ai-marketing-hub-claude-ads
codex plugin add claude-seo@agricidaniel-claude-seo
codex plugin add impeccable@impeccable
codex plugin add descript@descript
codex plugin add lotgen@lotgen
```

**Grok**

```sh
grok plugin install AgriciDaniel/claude-ads
grok plugin install AgriciDaniel/claude-seo
grok plugin install descriptinc/descript-mcp
grok plugin marketplace add pbakaus/impeccable
grok plugin install impeccable@impeccable
grok plugin marketplace add ascendedent/lotgen-skills
grok plugin install lotgen@lotgen-skills
```

`claude-ads` and `claude-seo` are built for Claude Code. They install on Codex and Grok, but their authors only verify Claude Code, and most `claude-seo` skills expect Claude's plugin paths, so some may need adjusting.

## API access: Meta and YouTube

Two connections need accounts set up outside this repo. Do them once; the person pastes every token
into `.env` themselves and never into a chat.

**Meta (Facebook page, Instagram, Threads): posting and numbers.** Full steps:
[`social-analyst/docs/post-direct-to-meta.md`](social-analyst/docs/post-direct-to-meta.md).
1. At developers.facebook.com create a **Business** app in your business portfolio with the use case
   "Manage everything on your Page" (add the Instagram and Threads use cases if you post there), give
   it a privacy policy URL, and switch it to **Live**.
2. In the business portfolio's settings add a **system user** (Admin) and assign it the page, the app
   and the Instagram account with full control.
3. On that system user choose **Generate token**: pick the app, set expiry to Never, tick the page
   permissions and the `instagram_*` ones. Put it in `.env` as `META_SYSTEM_TOKEN`, with `META_PAGE_ID`
   and `META_IG_USER_ID`.
4. Threads needs its own token: add the profile as a **Threads Tester** in the app, accept the invite
   in Threads (Settings → Account → Website permissions), then use the app's **User Token Generator**.
   Put it in `.env` as `THREADS_TOKEN`.
5. Post with `social-analyst/scripts/meta_publish.py --help`. Facebook is only ever scheduled; Instagram and
   Threads ask a person to confirm at a terminal, because those go public at once.

**YouTube: numbers, and uploads if you really need them.** Full steps:
[`social-analyst/docs/connect-youtube.md`](social-analyst/docs/connect-youtube.md).
1. In Google Cloud create a project and enable **YouTube Data API v3** and **YouTube Analytics API**.
2. Set the OAuth consent screen to **External** and publish it to **In production**, or the sign-in
   expires every 7 days. Publishing needs a home page, privacy policy link and authorized domain filled
   in; it does not need Google's verification for your own channel.
3. Create an **OAuth client ID** of type **Desktop app** (API keys and service accounts cannot act for
   a channel) and store the client ID and secret with `uv run sma setup keys`.
4. Run `uv run sma connect youtube <slug>`, sign in as the channel's owner, and check it connected the
   channel you meant.
5. For posting, prefer connecting the channel in Buffer: uploads through Google's API stay private
   until Google approves an audit form, which can take weeks.

## Update

```sh
git submodule update --remote --depth 1   # pull the latest from every source
git add vendor && git commit -m "Update skills"
```

## What's in it

Skills are grouped by function in [`skills/`](skills/). `.claude/skills/` is a flat list of links into those folders, because Claude Code only finds skills one level deep there, and `.agents/skills` links to that same list for Codex and Grok. To add a skill, put it in a category folder and link it from `.claude/skills/`.

| Function | Skills |
|---|---|
| [Strategy](skills/strategy/) | `marketing-plan` `marketing-ideas` `marketing-psychology` `product-marketing` `offers` `pricing` `launch` |
| [Research](skills/research/) | `customer-research` `competitor-profiling` `review-audit` `catalog-search` `open-library` `internet-archive` `google-books` `openalex` `crossref` `unpaywall` `arxiv` `pubmed-central` `doaj` |
| [Paid media](skills/paid-media/) | `ads` `ad-creative` plus the `claude-ads` plugin |
| [Copy](skills/copy/) | `copywriting` `copy-editing` `direct-response-copy` `ad-copy` `landing-page-copy` `copychief` `compliance-checker` |
| [Conversion](skills/conversion/) | `cro` `ab-testing` `popups` `lead-magnets` |
| [Email and SMS](skills/email-sms/) | `emails` `sms` |
| [SEO](skills/seo/) | `seo-audit` `ai-seo` `schema` `site-architecture` `programmatic-seo` `link-building` `directory-submissions` plus the `claude-seo` plugin |
| [Analytics](skills/analytics/) | `analytics` `attribution` `conversion-tracking` and the [`google-data`](google-data/) connector |
| [Measurement](skills/measurement/) | `meridian-*` `*causalpy*` `causal-detective` `running-placebo-analysis` `marketing-geo-experiments` and the [`measurement`](measurement/) environments |
| [Web build](skills/web-build/) | `core-web-vitals` `vercel-react-best-practices` `web-design-guidelines` `frontend-design` `flags-sdk` `vercel-flags` `gsap-*` plus the `impeccable` plugin |
| Social | [`social-analyst`](social-analyst/) |
| [Video](skills/video/) | [`build-reel`](build-reel/), `reel-team`, `craft`, the `descript` plugin, and `lotgen-*` |

The `lotgen-*` skills drive [LOTGEN](https://lotgen.ai), a hosted video service, and need a LOTGEN account. The app isn't part of this repo.

## Sources

| Submodule | Repo | Licence |
|---|---|---|
| `vendor/marketingskills` | [coreyhaines31/marketingskills](https://github.com/coreyhaines31/marketingskills) | MIT |
| `vendor/copywriting-skills` | [robpalmer99/claude-code-copywriting-skills](https://github.com/robpalmer99/claude-code-copywriting-skills) | CC BY 4.0 |
| `vendor/claude-ads` | [AgriciDaniel/claude-ads](https://github.com/AgriciDaniel/claude-ads) | MIT |
| `vendor/claude-seo` | [AgriciDaniel/claude-seo](https://github.com/AgriciDaniel/claude-seo) | MIT |
| `vendor/impeccable` | [pbakaus/impeccable](https://github.com/pbakaus/impeccable) | Apache-2.0 |
| `vendor/vercel-agent-skills` | [vercel-labs/agent-skills](https://github.com/vercel-labs/agent-skills) | See repo |
| `vendor/vercel-flags` | [vercel/flags](https://github.com/vercel/flags) | MIT |
| `vendor/web-quality-skills` | [addyosmani/web-quality-skills](https://github.com/addyosmani/web-quality-skills) | MIT |
| `vendor/creative-strategy-skills` | [motion-team/creative-strategy-skills](https://github.com/motion-team/creative-strategy-skills) | MIT |
| `vendor/gsap-skills` | [greensock/gsap-skills](https://github.com/greensock/gsap-skills) | MIT |
| `vendor/meridian` | [google/meridian](https://github.com/google/meridian) | Apache-2.0 |
| `vendor/causalpy` | [pymc-labs/CausalPy](https://github.com/pymc-labs/CausalPy) | Apache-2.0 |
| `vendor/narenaryan-agent-skills` | [narenaryan/agent-skills](https://github.com/narenaryan/agent-skills) | MIT |
| `vendor/anthropic-skills` | [anthropics/skills](https://github.com/anthropics/skills) | See repo |
| `vendor/ponytail` | [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail) | MIT |
| `vendor/lotgen-skills` | [ascendedent/lotgen-skills](https://github.com/ascendedent/lotgen-skills) | See repo |
| `vendor/descript` | [descriptinc/descript-mcp](https://github.com/descriptinc/descript-mcp) | Apache-2.0 |

## Licence

The code in this repo is [MIT](LICENSE). Each submodule keeps its own licence, listed above, and third-party components in `build-reel` are covered by its [notices](build-reel/THIRD_PARTY_NOTICES.md).
