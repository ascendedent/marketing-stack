# Google data connector

A small read-only MCP server (stdio) for GA4 and Search Console. Its tokens only carry the `analytics.readonly` and `webmasters.readonly` scopes, so Google refuses changes.

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.lock
.venv/bin/python server.py /path/to/service-account-key.json
```

Grant the service account access to your GA4 properties and Search Console sites. Keep the key outside this repo.

| Tool | Use |
|---|---|
| `ga4_list_properties` | List readable GA4 properties |
| `ga4_run_report` | Run a GA4 report |
| `ga4_list_key_events` | List the events marked as key events on a property |
| `gsc_list_sites` | List readable Search Console sites |
| `gsc_query` | Get clicks, impressions, CTR and position |
| `gsc_inspect_url` | Get one URL's index status |
