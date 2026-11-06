"""Web edition: report.py must run stdlib-only on connector JSON and messy exports; dist must be fresh."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "web/shared/report.py"


def run(*args, cwd):
    # -I -S: isolated, no site-packages — proves it works in a bare code-interpreter sandbox
    r = subprocess.run([sys.executable, "-I", "-S", str(REPORT), *args], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def days_ago(n, hour=15):
    return (datetime.now(timezone.utc) - timedelta(days=n)).replace(hour=hour, minute=0, second=0, microsecond=0)


def test_buffer_connector_json(tmp_path):
    posts = []
    for i in range(12):
        posts.append({"id": f"p{i}", "text": f"Post {i} " + ("question?" if i % 3 == 0 else "statement"),
                      "sentAt": days_ago(3 + i * 4).isoformat().replace("+00:00", "Z"), "channelService": "linkedin",
                      "channel": {"name": "acme-page", "service": "linkedin"},
                      "externalLink": f"https://www.linkedin.com/feed/update/urn:li:share:{i}",
                      "assets": [{"type": "image"}] if i % 2 else [],
                      "metrics": [{"type": "impressions", "value": 1000 + i * 50}, {"type": "engagementRate", "value": 0.4 + i * 0.05},
                                  {"type": "reactions", "value": i}]})
    f = tmp_path / "buffer.json"
    f.write_text(json.dumps({"posts": posts}))
    out = run(str(f), "--days", "90", "--json", cwd=tmp_path)
    r = json.loads(out)
    assert r["posts_scored"] == 12 and r["channels"][0]["channel"] == "acme-page"
    assert r["notes"] == []                                   # connector ER < 1% must NOT be rescaled
    assert r["channels"][0]["kpi_median"] < 1
    assert {"image", "text"} <= set(r["by_media"])


def test_messy_linkedin_style_export(tmp_path):
    rows = ["Post analytics export,,,,,", "Post title,Post link,Created date,Impressions,Clicks,Likes,Comments,Engagement rate"]
    for i in range(10):
        d = days_ago(5 + i * 3).strftime("%m/%d/%Y")
        rows.append(f'"Title {i} #growth #b2b",https://lnkd.in/x{i},{d},{2000 + i * 100},{10 + i},{20 + i},{i},0.0{2 + i % 5}')
    f = tmp_path / "linkedin.csv"
    f.write_text("\n".join(rows))
    out = run(str(f), "--days", "120", cwd=tmp_path)
    assert "10 posts scored" in out and "converted to percent" in out
    assert "## Hashtags used 3+ times" in out


def test_tiktok_style_export_with_kpi_choice(tmp_path):
    rows = ["Video title,Video link,Post time,Total views,Total likes,Total comments,Total shares,Average watch time,Watched full video (%)"]
    for i in range(8):
        rows.append(f'"Clip {i}",https://www.tiktok.com/@a/video/{i},{days_ago(4 + i * 5).strftime("%Y-%m-%d %H:%M")},{1000 * (i + 1)},{50 * (i + 1)},5,3,0:0{i + 1},{20 + i}%')
    f = tmp_path / "tiktok.csv"
    f.write_text("\n".join(rows))
    r = json.loads(run(str(f), "--kpi", "views", "--json", cwd=tmp_path))
    assert r["posts_scored"] == 8
    r2 = json.loads(run(str(f), "--kpi", "completionRate", "--json", cwd=tmp_path))
    assert r2["posts_scored"] == 8
    out = run(str(f), "--kpi", "saves", cwd=tmp_path)
    assert "No post had the KPI 'saves'" in out and "views" in out


def test_dist_is_fresh_and_fits_limits():
    r = subprocess.run([sys.executable, str(ROOT / "web/build.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
    for p in ("chatgpt", "grok"):
        assert len((ROOT / f"web/dist/{p}/instructions.md").read_text()) <= 8000
