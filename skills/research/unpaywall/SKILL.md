---
name: unpaywall
description: >
  Checks Unpaywall for a legal free copy of a scholarly article. Use when the
  user has a DOI and asks for an open-access PDF, a free version, or whether
  the paper is gold, green, hybrid, bronze, or closed. Resolve the DOI with
  Crossref or OpenAlex first when the user only has a title.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS and the user's real email. No packages.
metadata:
  version: "1.0"
---

# Unpaywall

Docs: https://unpaywall.org/products/api

Base: `https://api.unpaywall.org/v2`

Every call needs `email` set to the person's real address. Ask for it. Never invent one. Budget is about 100,000 calls a day. Coverage is Crossref DOIs. A DOI from another agency, or one Unpaywall does not have, is a 404. That is "no record", not a broken client. Timeout 30 seconds.

## By DOI

`GET /v2/{doi}?email=them@example.com`

Read:

- `is_oa`
- `oa_status`: `gold`, `hybrid`, `bronze`, `green`, or `closed`
- `best_oa_location.url_for_pdf`, then `best_oa_location.url`
- `oa_locations` when they want every legal copy, not just the best one

Prefer `url_for_pdf`. Fetch that URL only when they asked for the file. A `closed` record has no free copy. Say so and stop.

## By title

`GET /v2/search?query=TITLE&email=them@example.com`

Use this only when you do not have a DOI. It returns a short ranked list. If the match is weak, resolve the DOI through `../crossref/SKILL.md` or `../openalex/SKILL.md` and call the DOI endpoint.

Report the catalog, the DOI, `oa_status`, and the URL you found. If the call failed, say the status and stop.
