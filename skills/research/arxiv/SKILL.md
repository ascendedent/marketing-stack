---
name: arxiv
description: >
  Searches the arXiv export API for preprints and their PDF links. Use when
  the user names arXiv, a preprint id, or a paper in physics, math, computer
  science, quantitative biology, finance, statistics, or economics. For a
  biomedical paper use the pubmed-central skill instead.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS. No packages. At most one request every 3 seconds.
metadata:
  version: "1.0"
---

# arXiv

Docs: https://info.arxiv.org/help/api/user-manual.html

`GET https://export.arxiv.org/api/query`

No key. The response is Atom XML, not JSON. One request every 3 seconds on a single connection. At most 2,000 results in one response and 30,000 results reached by paging a single query. A deeper search has to be split, by date or by category. Timeout 30 seconds.

| Param | Use |
|---|---|
| `search_query` | Fielded query |
| `id_list` | Comma-separated arXiv ids, when you already have them |
| `start` | 0-based offset |
| `max_results` | Default 10 |
| `sortBy` | `relevance`, `lastUpdatedDate`, `submittedDate` |
| `sortOrder` | `ascending` or `descending` |

Prefixes: `ti:` title, `au:` author, `abs:` abstract, `cat:` category, `all:` every field. Combine with `AND`, `OR`, and `ANDNOT`. A phrase is quoted.

```
GET https://export.arxiv.org/api/query?search_query=au:vaswani+AND+ti:attention&max_results=5&sortBy=relevance
```

From each `<entry>` read `<title>`, `<name>` inside `<author>`, `<published>`, `<summary>`, and the `<link>` whose `title` is `pdf`. The abstract page is `https://arxiv.org/abs/{id}`. The PDF is `https://arxiv.org/pdf/{id}`.

Fetch the PDF only when they asked for the file. Metadata is CC0. The e-print itself stays under its own license. Give the link and the id. Do not paste the paper.

Report the catalog, the query, and the arXiv id. Quote title, authors, and published date from the feed. If the call failed, say the status and stop.
