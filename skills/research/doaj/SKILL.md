---
name: doaj
description: >
  Searches the Directory of Open Access Journals API for articles and journals.
  Use when the user names DOAJ, an open-access journal, or wants articles that
  are open access by the journal's policy, including a DOI or ISSN lookup
  inside DOAJ.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS. No packages.
metadata:
  version: "1.0"
---

# DOAJ

Docs: https://doaj.org/docs/api/

Base: `https://doaj.org/api/v4`

No key for search. The query is a path segment. Encode spaces as `%20`. A `+` in the path is a literal plus and breaks the query. `pageSize` max is 100. Default page size is 10. Timeout 30 seconds. On 429 or 503, wait and retry once.

## Articles

`GET /api/v4/search/articles/{query}?page=1&pageSize=5`

Field prefixes that work in the path: `title:`, `doi:`, `issn:`, `license:`, and `bibjson.abstract:`.

```
GET https://doaj.org/api/v4/search/articles/title:malaria?page=1&pageSize=5
```

Read `total` and `results`. The record is under `bibjson`:

- `title`, `year`, `abstract`
- `author[].name`
- `journal.title`
- `identifier[]` where `type` is `doi`
- `link[]` where `type` is `fulltext`. Use the `url` whose `content_type` is PDF when they asked for the file.

One article by its DOAJ id: `GET /api/v4/articles/{id}`

## Journals

`GET /api/v4/search/journals/{query}?page=1&pageSize=5`

Use this when the question is the journal, its ISSN, or whether DOAJ lists it. Article search does not answer that.

Report the catalog, the query, and the DOI or DOAJ id. Quote title, authors, and year from `bibjson`. If the call failed, say the status and stop.
