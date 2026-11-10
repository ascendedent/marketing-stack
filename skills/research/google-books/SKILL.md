---
name: google-books
description: >
  Searches the Google Books Volumes API for metadata and preview status. Use
  when the user names Google Books, wants a preview, or wants to know whether
  Google has a full view, a partial view, or no pages for a title or ISBN.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS and a Google Books API key the user supplies. No packages.
metadata:
  version: "1.0"
---

# Google Books

Docs: https://developers.google.com/books/docs/v1/using

Send a `key` from a Google Cloud project with the Books API enabled. Ask the person for the key. An unauthenticated call is rate-limited and often returns 429. Do not retry a 429 in a loop. Timeout 30 seconds.

## Search

`GET https://www.googleapis.com/books/v1/volumes`

| Param | Use |
|---|---|
| `q` | Free text, or `intitle:`, `inauthor:`, `subject:`, `isbn:` |
| `maxResults` | 1–40 |
| `startIndex` | 0-based offset |
| `fields` | Partial response. Use it. |
| `key` | API key |
| `langRestrict` | Optional ISO language |

```
GET https://www.googleapis.com/books/v1/volumes?q=intitle:pride+prejudice+inauthor:austen&maxResults=5&fields=totalItems,items(id,volumeInfo/title,volumeInfo/authors,volumeInfo/publishedDate,accessInfo/viewability)&key=KEY
```

Read `totalItems` and `items`. `volumeInfo` holds the record. `accessInfo.viewability` is `NO_PAGES`, `PARTIAL`, or `ALL_PAGES`.

## One volume

`GET https://www.googleapis.com/books/v1/volumes/{id}?key=KEY`

`volumeInfo.previewLink` and `volumeInfo.infoLink` open Google's own pages. They are not a file download. Report viewability. Do not scrape the preview reader for the rest of the book.

Report the catalog, the query, and the volume id. Quote title, authors, and date from the response. If the call failed, say the status and stop.
