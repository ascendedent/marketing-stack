"""Descript route: upload an editor package as a ready-to-edit Descript project.

Two ways to authenticate, both supported:

1. Official Descript MCP (OAuth, plugin `descript@descript`): the agent calls
   `import_media` with descript-import.json (minus local_path), saves the
   returned `upload_urls` to a file, and runs `reel descript-put` to upload the
   bytes, then polls `wait_for_job`.
2. REST API token (DESCRIPT_TOKEN in the env or .env.reel): `reel descript`
   does the whole import here and prints the project link.

REST details follow Descript's public API (https://descriptapi.com/v1,
OpenAPI v1.2) as documented by Descript and by alexaiarchitect/descript-skills.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import die, info, read_json, write_json

API = os.environ.get("DESCRIPT_API_URL", "https://descriptapi.com/v1")


def _token():
    tok = os.environ.get("DESCRIPT_TOKEN")
    if not tok:
        die("DESCRIPT_TOKEN is not set. Create one in Descript > Settings > API tokens and add it to .env.reel,\n"
            "or use the MCP route (see SKILL.md, route B).")
    return tok


def _req(path, method="GET", body=None, tries=4):
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(tries):
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": f"Bearer {_token()}", "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="ignore")[:400]
            if e.code == 429 and attempt + 1 < tries:
                time.sleep(int(e.headers.get("Retry-After", "5")))
                continue
            hint = {401: "token invalid or expired", 402: "out of media minutes or AI credits",
                    403: "not allowed (admin setting?)"}.get(e.code, "")
            die(f"Descript API {method} {path} -> {e.code} {hint}\n{msg}")
    die("Descript API kept rate limiting; try again later")


def put_file(url, path):
    p = Path(path)
    size = p.stat().st_size
    with open(p, "rb") as f:
        req = urllib.request.Request(url, data=f, method="PUT", headers={
            "Content-Type": "application/octet-stream", "Content-Length": str(size)})
        with urllib.request.urlopen(req, timeout=600) as r:
            if r.status >= 300:
                die(f"upload of {p.name} failed: HTTP {r.status}")
    return size


def put_uploads(pkg, upload_urls):
    """upload_urls: {media_name: {upload_url, ...}} as returned by import_media (API or MCP)."""
    manifest = read_json(Path(pkg) / "descript-import.json")
    if not manifest:
        die(f"no descript-import.json in {pkg} (run `reel export` first)")
    media = manifest["add_media"]
    missing = [k for k in media if k not in upload_urls]
    if missing:
        die(f"no upload URL for: {', '.join(missing)}")
    failed = []
    for name, spec in media.items():
        try:
            size = put_file(upload_urls[name]["upload_url"], Path(pkg) / spec["local_path"])
            info(f"  uploaded {name} ({size / 1e6:.1f} MB)")
        except (urllib.error.URLError, OSError) as e:
            failed.append(name)
            info(f"  FAILED {name}: {getattr(e, 'reason', e)}")
    if failed:
        die("some uploads failed. With the MCP route, call report_upload_status (status 'failed') for each of:\n  "
            + "\n  ".join(failed) + "\nthen wait for the job to stop and import those files again into the same project.\n"
            "A proxy or firewall that blocks storage.googleapis.com causes this.")


def payload_for_api(pkg):
    m = read_json(Path(pkg) / "descript-import.json")
    m = {k: v for k, v in m.items() if not k.startswith("_")}
    m["add_media"] = {k: {kk: vv for kk, vv in v.items() if kk != "local_path"} for k, v in m["add_media"].items()}
    return m


def wait_job(job_id, label="job", timeout=1800):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        j = _req(f"/jobs/{job_id}")
        prog = j.get("progress") or {}
        line = f"  {label}: {j.get('job_state')} {prog.get('label', '')} {prog.get('percent', '')}"
        if line != last:
            info(line)
            last = line
        if j.get("job_state") in ("stopped", "cancelled"):
            return j
        time.sleep(5)
    die(f"{label} still running after {timeout}s; check it in Descript (job {job_id})")


def upload(sb, dry_run=False):
    pkg = sb.dir / "out" / f"{sb.slug}-package"
    body = payload_for_api(pkg)
    total_mb = sum(v["file_size"] for v in body["add_media"].values()) / 1e6
    secs = read_json(pkg / "plan.json")["total"]
    info(f"Descript import: project '{body['project_name']}', {len(body['add_media'])} clips, "
         f"{total_mb:.0f} MB, about {secs:.0f}s of media minutes")
    if dry_run:
        print(json.dumps(body, indent=1))
        return
    job = _req("/jobs/import/project_media", "POST", body)
    write_json(pkg / "descript-job.json", {k: v for k, v in job.items() if k != "upload_urls"})
    put_uploads(pkg, job.get("upload_urls") or {})
    done = wait_job(job["job_id"], "import")
    res = done.get("result") or {}
    info(f"import {res.get('status')}: {job.get('project_url')}")
    for c in res.get("created_compositions") or []:
        info(f"  composition: {c.get('name')} ({c.get('id')})")
    write_json(pkg / "descript-job.json", {"import": {k: v for k, v in job.items() if k != "upload_urls"},
                                           "result": res})
    if res.get("status") != "success":
        die(f"import finished with status {res.get('status')}: {json.dumps(res.get('media_status', {}))[:400]}")


def polish(sb, prompt_file=None, model="auto", yes=False):
    """Run the Underlord prompt on the imported project (costs AI credits)."""
    pkg = sb.dir / "out" / f"{sb.slug}-package"
    rec = read_json(pkg / "descript-job.json") or {}
    imp = rec.get("import") or {}
    pid = imp.get("project_id")
    if not pid:
        die("no imported project recorded; run `reel descript` first (or pass the project in Descript yourself)")
    comps = (rec.get("result") or {}).get("created_compositions") or []
    prompt = Path(prompt_file).read_text() if prompt_file else (pkg / "underlord-prompt.md").read_text()
    body = {"project_id": pid, "prompt": prompt, "model": model}
    if comps:
        body["composition_id"] = comps[0]["id"]
    if not yes:
        info("This runs Underlord and spends AI credits (a caption pass is usually a few credits).")
        info("Prompt:\n" + prompt)
        info("Re-run with --yes to send it.")
        return
    job = _req("/jobs/agent", "POST", body)
    done = wait_job(job["job_id"], "underlord")
    res = done.get("result") or {}
    info(f"underlord {res.get('status')}, credits used: {res.get('ai_credits_used')}")
    if res.get("agent_response"):
        info(res["agent_response"])
    rec["agent"] = {"job_id": job["job_id"], "conversation_id": res.get("conversation_id"),
                    "credits": res.get("ai_credits_used"), "status": res.get("status")}
    write_json(pkg / "descript-job.json", rec)
