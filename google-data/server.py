"""Read-only Google Analytics 4 and Search Console tools over MCP stdio.

Usage: server.py <service-account-key.json>

Tokens only ever carry read-only scopes, so Google refuses any change even if a
tool were misused.
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from google.auth.transport.requests import Request
from google.oauth2 import service_account

KEY = sys.argv[1]
GA_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
creds = {}


def google(scope, url, body=None):
    c = creds.setdefault(scope, service_account.Credentials.from_service_account_file(KEY, scopes=[scope]))
    if not c.valid:
        c.refresh(Request())
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {c.token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Google returned HTTP {e.code}: {e.read().decode(errors='replace')[:800]}") from e


def ga4_list_properties(_):
    return google(GA_SCOPE, "https://analyticsadmin.googleapis.com/v1beta/accountSummaries?pageSize=200")


def ga4_run_report(a):
    body = {
        "dateRanges": [{"startDate": a["start_date"], "endDate": a["end_date"]}],
        "metrics": [{"name": m} for m in a["metrics"]],
        "dimensions": [{"name": d} for d in a.get("dimensions", [])],
        "limit": a.get("limit", 1000),
    }
    return google(GA_SCOPE, f"https://analyticsdata.googleapis.com/v1beta/properties/{a['property_id']}:runReport", body)


def ga4_list_key_events(a):
    url = f"https://analyticsadmin.googleapis.com/v1beta/properties/{a['property_id']}/keyEvents?pageSize=200"
    return google(GA_SCOPE, url)


def gsc_list_sites(_):
    return google(GSC_SCOPE, "https://www.googleapis.com/webmasters/v3/sites")


def gsc_query(a):
    body = {
        "startDate": a["start_date"],
        "endDate": a["end_date"],
        "dimensions": a.get("dimensions", []),
        "rowLimit": a.get("row_limit", 1000),
    }
    site = urllib.parse.quote(a["site_url"], safe="")
    return google(GSC_SCOPE, f"https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query", body)


def gsc_inspect_url(a):
    body = {"inspectionUrl": a["url"], "siteUrl": a["site_url"]}
    return google(GSC_SCOPE, "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect", body)


def schema(required, **props):
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


STR = {"type": "string"}
DATE = {"type": "string", "description": "YYYY-MM-DD, or for GA4 also 7daysAgo, yesterday, today"}
LIST = {"type": "array", "items": {"type": "string"}}
READ_ONLY = {"readOnlyHint": True, "destructiveHint": False}
TOOLS = {
    "ga4_list_properties": (ga4_list_properties, "List the GA4 accounts and properties this account can read.", schema([])),
    "ga4_run_report": (
        ga4_run_report,
        "Run a GA4 report for one property. Metrics and dimensions use GA4 Data API names, such as sessions, totalUsers, keyEvents, date, sessionSource.",
        schema(["property_id", "start_date", "end_date", "metrics"], property_id=STR, start_date=DATE, end_date=DATE, metrics=LIST, dimensions=LIST, limit={"type": "integer"}),
    ),
    "ga4_list_key_events": (
        ga4_list_key_events,
        "List the events marked as key events on one GA4 property. An empty result means none are defined.",
        schema(["property_id"], property_id=STR),
    ),
    "gsc_list_sites": (gsc_list_sites, "List the Search Console properties this account can read.", schema([])),
    "gsc_query": (
        gsc_query,
        "Get Search Console clicks, impressions, CTR and position. Dimensions can be query, page, country, device, date. Use the site_url exactly as gsc_list_sites returns it.",
        schema(["site_url", "start_date", "end_date"], site_url=STR, start_date=DATE, end_date=DATE, dimensions=LIST, row_limit={"type": "integer"}),
    ),
    "gsc_inspect_url": (
        gsc_inspect_url,
        "Get Google's index status for one URL. Use the site_url exactly as gsc_list_sites returns it.",
        schema(["site_url", "url"], site_url=STR, url=STR),
    ),
}


def tool_list():
    return [{"name": n, "description": t[1], "inputSchema": t[2], "annotations": READ_ONLY} for n, t in TOOLS.items()]


def handle(msg):
    method, params = msg.get("method"), msg.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "google-data", "version": "1"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": tool_list()}
    if method == "tools/call":
        try:
            result = TOOLS[params["name"]][0](params.get("arguments") or {})
            return {"content": [{"type": "text", "text": json.dumps(result)}]}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
    raise LookupError(method)


if __name__ == "__main__":
    if KEY == "--list-tools":
        print(json.dumps(tool_list()))
        raise SystemExit
    for line in sys.stdin:
        msg = json.loads(line)
        if "id" not in msg:
            continue
        try:
            out = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except LookupError as e:
            out = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": f"Unknown method: {e}"}}
        print(json.dumps(out), flush=True)
