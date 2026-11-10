---
name: pubmed-central
description: >
  Searches biomedical literature through Europe PMC and NCBI E-utilities,
  including PubMed and PubMed Central. Use when the user names PubMed, PMC,
  Europe PMC, NCBI, a PMID, a PMCID, or a biomedical paper. Use arXiv for a
  non-biomedical preprint.
compatibility: Agent Skills SKILL.md. Any client that reads this format, including Claude, Codex, Grok, ChatGPT, Copilot, and Cursor. Needs outbound HTTPS. NCBI calls need the user's email. An NCBI API key is optional.
metadata:
  version: "1.0"
---

# PubMed Central

Use Europe PMC to search. Use NCBI when you need official PubMed or PMC ids, or the PMC open-access package. Both cover the biomedical literature. Europe PMC also returns the full-text links in one JSON call.

## Europe PMC

Docs: https://europepmc.org/RestfulWebService

`GET https://www.ebi.ac.uk/europepmc/webservices/rest/search`

No key. Stay under 10 requests a second. Send a User-Agent. Timeout 30 seconds.

| Param | Use |
|---|---|
| `query` | Free text, or `TITLE:`, `AUTH:`, `DOI:`, `PUB_YEAR:[2020 TO 2024]` |
| `format` | `json` |
| `resultType` | `lite` for a short record. `core` when you need the abstract and full-text links. |
| `pageSize` | Default 25. Max 1000. |
| `cursorMark` | First call `*`, then the returned `nextCursorMark`. `page` does not advance the list. |
| `sort` | Example `CITED desc` |

`SRC:PMC` limits the query to PubMed Central. `OPEN_ACCESS:Y` limits it to open articles.

```
GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=TITLE:malaria&format=json&resultType=core&pageSize=5&cursorMark=*
```

Read `hitCount` and `resultList.result`. Useful fields: `title`, `authorString`, `pubYear`, `doi`, `pmid`, `pmcid`, `isOpenAccess`, `abstractText`. In `fullTextUrlList.fullTextUrl`, take the entry whose `documentStyle` is `pdf`.

## NCBI E-utilities

Docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/

Base: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`

Send `tool` and `email`. Ask for the email. Never invent one. Without `api_key`, stay at or under 3 requests a second. With a key the person created in their NCBI account, 10 a second.

Search: `esearch.fcgi?db=pubmed&term=QUERY&retmode=json&retmax=5`

Use `db=pmc` for PubMed Central ids. The response is `esearchresult.count` and `esearchresult.idlist`. Those are ids, not records.

Summary: `esummary.fcgi?db=pubmed&id=ID,ID&retmode=json`

An open-access file in PMC, when one exists: `https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=PMC1234567`

That service returns XML, and only for articles in the open-access subset. No link means PMC does not offer the file. Do not fetch the article HTML and scrape it.

Report the catalog, the query, and the PMID or PMCID. Quote title, authors, and year from the response. If the call failed, say the status and stop.
