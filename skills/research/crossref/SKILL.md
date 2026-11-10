---
name: crossref
description: >
  Queries the Crossref REST API for the publisher record of a scholarly work,
  including its DOI. Use when the user names Crossref, has a partial citation,
  or needs a DOI. Use Unpaywall when they already have a DOI and want the
  free file. Crossref does not return PDFs.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS and the user's real email for the polite pool. No packages.
metadata:
  version: "1.0"
---

# Crossref

Docs: https://www.crossref.org/documentation/retrieve-metadata/rest-api/ and https://api.crossref.org/swagger-ui/index.html

Base: `https://api.crossref.org`

No key. Add `mailto` with the person's real email, or put `mailto:` in the User-Agent, so the call uses the polite pool. Ask for the email. Never invent one. Example User-Agent: `catalog-search/1.0 (mailto:them@example.com)`. Timeout 30 seconds. On 429, wait and retry once.

## Search works

`GET /works`

| Param | Use |
|---|---|
| `query.bibliographic` | Title plus author, the usual search |
| `query.title` | Title tokens only |
| `query.author` | Author tokens only |
| `query` | All fields |
| `filter` | Comma list, such as `type:journal-article,from-pub-date:2020-01-01` |
| `rows` | Page size. Keep it small. The max is 1000. |
| `select` | Comma list. Use at most a few fields: `DOI,title,author,issued,container-title,URL` |
| `sort` | `relevance`, `published`, `is-referenced-by-count` |
| `order` | `asc` or `desc` |
| `cursor` | Deep pages. First call `cursor=*`, then pass `message.next-cursor`. |

```
GET https://api.crossref.org/works?query.bibliographic=pride%20and%20prejudice%20austen&rows=5&select=DOI,title,author,issued&mailto=them@example.com
```

Read `message.total-results` and `message.items`. `title` and `author` are arrays. `author[].given` and `author[].family` are the name.

## One work

`GET /works/{doi}`

The DOI is the path. Crossref returns the publisher record. It does not return a free PDF. Hand the DOI to `../unpaywall/SKILL.md` when the question is the file.

Report the catalog, the query, and the DOI. Quote title, authors, and year from the response. If the call failed, say the status and stop.
