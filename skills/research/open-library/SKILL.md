---
name: open-library
description: >
  Looks up books in the Open Library search API: title, author, ISBN, work
  records, and cover images. Use when the user names Open Library, an OLID, an
  ISBN, a book cover, or a book they want identified, including when they only
  give a title and author.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS. No packages.
metadata:
  version: "1.0"
---

# Open Library

Docs: https://openlibrary.org/dev/docs/api/search

No key. Send `User-Agent` with an app name and the person's real email. Ask for the email if you do not have it. Never invent one. Cache repeats. Use the API, not the HTML pages. Timeout 30 seconds. On 429 or 503, wait and retry once.

## Search

`GET https://openlibrary.org/search.json`

| Param | Use |
|---|---|
| `q` | Free text, or `title:`, `author:`, `subject:`, `isbn:` |
| `limit` | How many works. Pass it. |
| `page` | 1-based page |
| `fields` | Comma list. Keep it short. |
| `sort` | `new`, `old`, `random`, or a facet |

Ask for `key,title,author_name,first_publish_year,isbn,cover_i,ia,edition_count`. Add `availability` only when the question is whether a copy can be borrowed. That field checks one Internet Archive id and is slower.

```
GET https://openlibrary.org/search.json?q=title:pride%20prejudice%20author:austen&limit=5&fields=key,title,author_name,first_publish_year,isbn,cover_i
```

Read `num_found` and `docs`. `docs[].key` is a work key such as `/works/OL262758W`.

## One record

- ISBN: `GET https://openlibrary.org/isbn/{isbn}.json`
- Work: `GET https://openlibrary.org/works/{OL..W}.json`
- Author: `GET https://openlibrary.org/authors/{OL..A}.json`

Any Open Library page has a JSON form: add `.json` to the path.

## Covers

`https://covers.openlibrary.org/b/id/{cover_i}-M.jpg`

Also `/b/isbn/{isbn}-M.jpg` and `/b/olid/{olid}-M.jpg`. Size letter is `S`, `M`, or `L`. A missing cover is an empty image, not an error.

## Stop

Search hits are works, not files. `ia` lists Internet Archive identifiers. Follow `../internet-archive/SKILL.md` for those. Do not treat `availability` as a download link.

Report the catalog, the query, and the work key. Quote title, authors, and year from the response. If the call failed, say the status and stop.
