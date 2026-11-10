---
name: catalog-search
description: >
  Chooses which legal catalog API to call for a book or a paper, then follows
  that catalog's skill. Use when the user wants a book, a paper, a DOI, a
  preprint, an open-access PDF, a cover, or a catalog record and does not name
  a single source, or names more than one of Open Library, Internet Archive,
  Google Books, OpenAlex, Crossref, Unpaywall, arXiv, PubMed Central, Europe
  PMC, NCBI, or DOAJ.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS. No packages.
metadata:
  version: "1.0"
---

# Choose a catalog

These skills are files on disk. They are not installed. Read the matching sibling `SKILL.md` and follow it. Do not invent a second client.

| The person wants | Skill |
|---|---|
| A book: title, author, ISBN, subjects, cover | `../open-library/SKILL.md` |
| A file or scan the Internet Archive hosts | `../internet-archive/SKILL.md` |
| A book preview, or a match against Google's catalog | `../google-books/SKILL.md` |
| A scholarly work, its authors, citations, or open-access status | `../openalex/SKILL.md` |
| A DOI, or the publisher record for a work | `../crossref/SKILL.md` |
| Whether a known DOI has a legal free copy | `../unpaywall/SKILL.md` |
| A preprint in physics, math, cs, or related fields | `../arxiv/SKILL.md` |
| A biomedical paper, PubMed, or PubMed Central | `../pubmed-central/SKILL.md` |
| An article in a fully open-access journal | `../doaj/SKILL.md` |

When the request is vague:

- A book title goes to Open Library. Add Internet Archive when they want a hosted copy, and Google Books when they want a preview.
- A paper title goes to OpenAlex. Take the DOI from that hit and open Unpaywall only when they want the free file.
- A DOI in hand goes to Unpaywall for the file and to Crossref for the publisher record. One of those is enough when the question is only one of those things.
- Biomedical wording goes to PubMed Central instead of OpenAlex.
- "Preprint" with no biomedical cue goes to arXiv.

## How to report

Name the catalog, the query, and the stable id (DOI, Open Library key, Internet Archive identifier, arXiv id, PMID, PMCID). Quote title, authors, and year from the response. If the call failed, say the status and stop. Do not fill the gap from memory.

A file URL is one the catalog returned as an open copy. A preview, a borrow button, or a snippet is not the full text. Say which of those you have.
