---
name: internet-archive
description: >
  Searches Internet Archive items and reads one item's metadata and public
  files. Use when the user names archive.org, an Internet Archive identifier,
  a scan, or a text the Archive hosts, including a book they already found
  on Open Library that has an ia id.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS. No packages.
metadata:
  version: "1.0"
---

# Internet Archive

Search docs: https://archive.org/advancedsearch.php

No key for search or metadata. Timeout 30 seconds. On 429 or 503, wait and retry once.

## Search

`GET https://archive.org/advancedsearch.php`

| Param | Use |
|---|---|
| `q` | Lucene query |
| `fl[]` | One field per repeated param. Always include `identifier`. |
| `output` | `json` |
| `rows` | Page size |
| `page` | 1-based |
| `sort[]` | Example: `downloads desc` |

Restrict texts with `mediatype:texts`. Phrase a title as `title:(pride prejudice)`.

```
GET https://archive.org/advancedsearch.php?q=mediatype:texts+AND+title:(pride+prejudice)&fl[]=identifier&fl[]=title&fl[]=creator&fl[]=year&output=json&rows=5
```

Read `response.numFound` and `response.docs`. The item page is `https://archive.org/details/{identifier}`.

## One item

`GET https://archive.org/metadata/{identifier}`

Read `metadata` for title, creator, date, and rights. Read `files` for the names the item actually holds.

A file listed there is fetched at `https://archive.org/download/{identifier}/{filename}`. Fetch it only when the metadata shows the item is openly available. If it is borrow-only, lend-restricted, or the files list is empty of a readable copy, give the details URL and stop.

Report the catalog, the query, and the identifier. Quote title and creator from the response. If the call failed, say the status and stop.
