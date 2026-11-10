---
name: openalex
description: >
  Searches the OpenAlex works API for scholarly papers, authors, citation
  counts, and open-access links. Use when the user names OpenAlex, a work id
  starting with W, a scholarly paper that is not specifically biomedical, or
  asks which papers cite a topic. Use Unpaywall instead when they already
  have a DOI and only want the free file.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS. A free OpenAlex API key is the normal way to call it.
metadata:
  version: "1.0"
---

# OpenAlex

Docs: https://docs.openalex.org and https://help.openalex.org/api/

Base: `https://api.openalex.org`

A free key is the normal way to call it. The person gets one at https://openalex.org/settings/api and you send it as `api_key` or `Authorization: Bearer`. Without a key the call shares a small daily budget with the IP and may be refused. Do not POST `/api-keys` and do not invent an email to create one. Ask the person for a key if a call comes back short of budget.

Search costs more of that budget than a filter. Prefer `filter` once you have an id. Timeout 30 seconds. On 429, wait and retry once.

## Search works

`GET /works?search=QUERY&per_page=5&select=id,display_name,publication_year,doi,authorships,open_access`

| Param | Use |
|---|---|
| `search` | Title, abstract, and some full text |
| `filter` | `publication_year:2024`, `is_oa:true`, `type:article`, combined with commas. OR inside one filter uses `\|`. |
| `sort` | `cited_by_count:desc` or `relevance_score:desc` |
| `per_page` | Max 100. Default 25. |
| `cursor` | Deep pages. First call `cursor=*`, then pass `meta.next_cursor`. |
| `select` | Comma list of fields |

`filter=title.search:WORDS` searches the title only.

Author and institution names are not filters. Search `/authors?search=NAME`, take the id (`A...`), then `filter=authorships.author.id:A...`. Same two-step pattern for sources, institutions, and topics.

## One work

- OpenAlex id: `GET /works/W2741809807`
- DOI: `GET /works/doi:10.7717/peerj.4375`

Read `open_access.is_oa` and `open_access.oa_url`. That URL is the catalog's open copy. For a second opinion on the file, pass the DOI to `../unpaywall/SKILL.md`.

A content download from `content.openalex.org` is a paid call. Do not start one unless the person asked for the file and the record says it is open.

Report the catalog, the query, and the OpenAlex id or DOI. Quote the display name, year, and authorships from the response. If the call failed, say the status and stop.
