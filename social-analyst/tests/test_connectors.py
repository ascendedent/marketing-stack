"""Offline tests: connectors against faked API responses, store merging, report, TikTok import.

Run: uv run --extra dev pytest -q
"""

import json
import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    (tmp_path / "accounts").mkdir()
    shutil.copytree(ROOT / "accounts/_template", tmp_path / "accounts/_template")
    monkeypatch.setenv("SMA_ROOT", str(tmp_path))
    import importlib
    import sma.config, sma.store
    importlib.reload(sma.config)
    importlib.reload(sma.store)
    for m in ("sma.connectors.youtube", "sma.connectors.instagram", "sma.connectors.tiktok_import", "sma.analyze"):
        importlib.reload(importlib.import_module(m))
    from sma import cli
    importlib.reload(cli)
    cli.main(["account", "new", "acme", "--name", "Acme"])
    return tmp_path


class Resp:
    def __init__(self, data, status=200):
        self._d, self.status_code, self.headers, self.text = data, status, {"content-type": "application/json"}, json.dumps(data)

    def json(self):
        return self._d


def test_youtube_sync(sandbox, monkeypatch):
    from sma import config, store
    from sma.connectors import youtube
    acct = config.load_account("acme")
    acct["connectors"] = {"youtube": {"channel_id": "UC1"}}
    config.save_account("acme", acct)

    class Creds:
        token = "t"
    monkeypatch.setattr(youtube, "_credentials", lambda slug: Creds())
    now = "2026-10-20T10:00:00Z"

    def fake_get(url, params=None, headers=None, timeout=None, **kw):
        p = params or {}
        if url.endswith("/channels"):
            return Resp({"items": [{"id": "UC1", "snippet": {"title": "Acme", "customUrl": "@acme"},
                                    "statistics": {"subscriberCount": "1200", "viewCount": "50000", "videoCount": "2"},
                                    "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}]})
        if url.endswith("/playlistItems"):
            return Resp({"items": [{"contentDetails": {"videoId": "v1", "videoPublishedAt": now}},
                                   {"contentDetails": {"videoId": "v2", "videoPublishedAt": now}}]})
        if url.endswith("/videos"):
            return Resp({"items": [
                {"id": "v1", "snippet": {"title": "Short one #shorts", "publishedAt": now}, "statistics": {"viewCount": "900", "likeCount": "50", "commentCount": "5"}, "contentDetails": {"duration": "PT30S"}},
                {"id": "v2", "snippet": {"title": "Long one", "publishedAt": now}, "statistics": {"viewCount": "300", "likeCount": "9", "commentCount": "1"}, "contentDetails": {"duration": "PT8M"}}]})
        if "youtubeanalytics" in url:
            dims = p.get("dimensions")
            if dims == "video":
                return Resp({"columnHeaders": [{"name": n} for n in ["video", "views", "estimatedMinutesWatched", "averageViewDuration", "averageViewPercentage", "likes", "comments", "shares", "subscribersGained"]],
                             "rows": [["v1", 1000, 300, 18, 60.0, 55, 5, 7, 3], ["v2", 310, 900, 174, 36.2, 9, 1, 0, 1]]})
            if dims == "elapsedVideoTimeRatio":
                return Resp({"columnHeaders": [{"name": "elapsedVideoTimeRatio"}, {"name": "audienceWatchRatio"}],
                             "rows": [[r / 100, max(0.1, 1 - r / 120)] for r in range(1, 101)]})
            if dims == "day":
                return Resp({"columnHeaders": [{"name": n} for n in ["day", "views", "estimatedMinutesWatched", "subscribersGained", "subscribersLost"]],
                             "rows": [["2026-10-20", 100, 40, 3, 1]]})
            return Resp({"columnHeaders": [], "rows": []})
        if url.endswith("/jobs"):
            return Resp({"jobs": []})
        if url.endswith("/jobs/J1/reports"):
            return Resp({"reports": [{"id": "r1", "createTime": "2026-10-21T00:00:00Z",
                                      "downloadUrl": "https://youtubereporting.googleapis.com/v1/media/r1"},
                                     {"id": "evil", "createTime": "2026-10-22T00:00:00Z",
                                      "downloadUrl": "https://evil.example.com/steal"}]})
        if url.endswith("/media/r1"):
            r = Resp({})
            r.text = ("date,channel_id,video_id,country_code,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
                      "20261020,UC1,v1,US,800,0.05\n20261020,UC1,v1,GB,200,0.10\n20261021,UC1,v2,US,500,0.02\n")
            return r
        if "evil" in url:
            raise AssertionError("token sent to a non-Google host")
        raise AssertionError(url)

    def fake_post(url, json=None, headers=None, timeout=None):
        assert url.endswith("/jobs") and json["reportTypeId"] == "channel_reach_basic_a1"
        return Resp({"id": "J1"})
    monkeypatch.setattr(youtube.httpx, "get", fake_get)
    monkeypatch.setattr(youtube.httpx, "post", fake_post)
    res = youtube.sync("acme", days=60)
    assert res["reach"]["reports_ingested"] == 1 and res["reach"]["reports_skipped"] == 1, res
    assert res["reach"]["video_days"] == 2, res
    assert res["videos"] == 2 and res["with_analytics"] == 2 and res["with_retention"] == 2, res
    db = store.connect()
    m = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='youtube:v1'")}
    assert m["views"] == 1000 and m["averageTimeWatched"] == 18 and "retentionHook" in m and m["follows"] == 3
    assert db.execute("SELECT post_type FROM posts WHERE id='youtube:v1'").fetchone()[0] == "short"
    assert db.execute("SELECT value FROM account_metrics WHERE metric='followers'").fetchone()[0] == 1200
    m = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='youtube:v1'")}
    assert m["impressions"] == 1000 and round(m["thumbnailCtr"], 2) == 6.0   # (800*.05+200*.10)/1000
    assert config.load_account("acme")["connectors"]["youtube"]["reach_job_id"] == "J1"


def test_native_merges_into_buffer_post(sandbox):
    from sma import store
    db = store.connect()
    store.upsert_post(db, {"id": "buf1", "channelId": "c1", "channelService": "youtube", "status": "sent", "text": "x",
                           "sentAt": "2026-10-01T00:00:00Z", "externalLink": "https://youtube.com/watch?v=abc123",
                           "metrics": [{"type": "views", "value": 10, "unit": "count"}]}, "acme")
    pid = store.upsert_native_post(db, account="acme", service="youtube", native_id="abc123", channel_id="c1",
                                   sent_at=None, text=None, url=None, post_type="video", media_kind="video",
                                   metrics={"averageViewPercentage": 41.0})
    assert pid == "buf1"
    assert db.execute("SELECT count(*) FROM posts").fetchone()[0] == 1


def test_instagram_sync(sandbox, monkeypatch):
    from sma import config, store
    from sma.connectors import instagram
    config.write_private(instagram._token_path("acme"), json.dumps(
        {"access_token": "tok-123456789", "host": "instagram", "user_id": "17841", "username": "acme", "refreshed_at": store.now()}))

    def fake_get(url, params=None, timeout=None):
        p = params or {}
        if url.endswith("/me"):
            return Resp({"username": "acme", "followers_count": 5000, "follows_count": 10, "media_count": 2})
        if url.endswith("/17841/media"):
            return Resp({"data": [
                {"id": "m1", "caption": "Reel #tips?", "media_type": "VIDEO", "media_product_type": "REELS", "permalink": "https://www.instagram.com/reel/AAA/", "timestamp": "2026-10-25T12:00:00+0000", "like_count": 40, "comments_count": 4},
                {"id": "m2", "caption": "Carousel", "media_type": "CAROUSEL_ALBUM", "media_product_type": "FEED", "permalink": "https://www.instagram.com/p/BBB/", "timestamp": "2026-10-24T12:00:00+0000", "like_count": 20, "comments_count": 2}]})
        if url.endswith("/insights") and "/m" in url:
            names = p["metric"].split(",")
            if "ig_reels_video_view_total_time" in names and len(names) > 1:  # simulate version drift
                return Resp({"error": {"message": "invalid metric"}}, 400)
            if names == ["ig_reels_video_view_total_time"]:
                return Resp({"error": {"message": "invalid metric"}}, 400)
            vals = {"views": 2000, "reach": 1500, "saved": 30, "shares": 12, "total_interactions": 90, "likes": 40, "comments": 4, "ig_reels_avg_watch_time": 7500}
            return Resp({"data": [{"name": n, "values": [{"value": vals[n]}]} for n in names if n in vals]})
        if url.endswith("/17841/insights"):
            if p.get("metric") == "follower_demographics":
                return Resp({"data": [{"total_value": {"breakdowns": [{"results": [{"dimension_values": ["25-34"], "value": 400}]}]}}]})
            return Resp({"data": []})
        raise AssertionError(url)
    monkeypatch.setattr(instagram.httpx, "get", fake_get)
    res = instagram.sync("acme", days=60, probe_duration=False)
    assert res["media"] == 2
    assert any("ig_reels_video_view_total_time" in w for w in res["warnings"])
    db = store.connect()
    m = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='instagram:AAA'")}
    assert m["saves"] == 30 and m["averageTimeWatched"] == 7.5 and round(m["engagementRate"], 1) == 6.0
    assert db.execute("SELECT media_kind, post_type FROM posts WHERE id='instagram:BBB'").fetchone()[:] == ("carousel", "carousel")
    assert db.execute("SELECT value FROM account_metrics WHERE metric='audience:age:25-34'").fetchone()[0] == 400


def test_tiktok_import_and_report(sandbox):
    from sma import analyze, store
    from sma.connectors import tiktok_import
    csv = sandbox / "Content.csv"
    rows = ["Video title,Video link,Post time,Total views,Total likes,Total comments,Total shares,Average watch time,Watched full video (%)"]
    for i in range(8):
        rows.append(f'"Video {i}",https://www.tiktok.com/@acme/video/{1000 + i},2026-09-{10 + i:02d} 18:30,{1000 * (i + 1)},{50 * (i + 1)},5,3,0:0{i + 1},{20 + i}%')
    csv.write_text("\n".join(rows))
    res = tiktok_import.import_file("acme", str(csv))
    assert res["kind"] == "content" and res["videos"] == 8
    assert {"views", "likes", "averageTimeWatched", "completionRate"} <= set(res["mapped"].values())
    db = store.connect()
    v = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='tiktok:1003'")}
    assert v["views"] == 4000 and v["averageTimeWatched"] == 4 and v["completionRate"] == 23
    r = analyze.report("acme", days=400, kpi="views")
    assert r["posts_scored"] == 8 and r["channels"][0]["service"] == "tiktok"


def test_setup_status_shape(sandbox):
    from sma import setup
    st = setup.status()
    assert {"complete", "next_step", "steps"} <= set(st)
    assert any(s["id"] == "first_account" and s["ok"] for s in st["steps"])
    assert "NEXT" in setup.brief(st) or "complete" in setup.brief(st).lower()


def test_competitor_metrics_kept_apart(sandbox, monkeypatch):
    from sma import analyze, discover, store
    fake = {"service": "youtube", "source": "yt-dlp", "url": "u", "handle": "@rival", "name": "Rival", "bio": "",
            "followers": 99999, "posts": []}
    monkeypatch.setattr(discover, "ytdlp_profile", lambda url, limit: dict(fake))
    discover.discover("https://www.youtube.com/@rival", "acme", competitor=True)
    db = store.connect()
    assert db.execute("SELECT count(*) FROM account_metrics WHERE account='acme'").fetchone()[0] == 0
    assert db.execute("SELECT count(*) FROM account_metrics WHERE account='competitor:acme'").fetchone()[0] == 1
    assert analyze.report("acme")["account_level"] == {}


def _buffer_post(db, store, pid, service, link, ctype="profile", cid="c1"):
    db.execute("INSERT OR REPLACE INTO channels (id, account, login, service, type, name) VALUES (?,?,?,?,?,?)",
               (cid, "acme", "default", service, ctype, "chan"))
    store.upsert_post(db, {"id": pid, "channelId": cid, "channelService": service, "status": "sent", "text": "hello",
                           "sentAt": "2026-10-20T10:00:00Z", "externalLink": link, "metrics": []}, "acme")


def test_x_sync(sandbox, monkeypatch):
    import time
    from sma import store
    from sma.connectors import oauth, x
    db = store.connect()
    _buffer_post(db, store, "buf-x", "twitter", "https://x.com/acme/status/111")
    db.commit()
    oauth.save_token("x", "acme", {"access_token": "xtok-123456789", "user_id": "42", "username": "acme",
                                   "expires_at": int(time.time()) + 3600})
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(params or {})
        if url.endswith("/users/me"):
            return Resp({"data": {"id": "42", "public_metrics": {"followers_count": 321, "following_count": 5, "tweet_count": 99}}})
        if url.endswith("/users/42/tweets"):
            private = "non_public_metrics" in params["tweet.fields"]
            if private:
                return Resp({"data": [
                    {"id": "111", "text": "with buffer", "created_at": "2026-10-20T10:00:00Z",
                     "public_metrics": {"like_count": 10, "reply_count": 2, "retweet_count": 1, "quote_count": 0, "bookmark_count": 3, "impression_count": 400},
                     "non_public_metrics": {"impression_count": 500, "url_link_clicks": 7, "user_profile_clicks": 4}},
                    {"id": "222", "text": "native only", "created_at": "2026-10-21T10:00:00Z",
                     "public_metrics": {"like_count": 1, "reply_count": 0, "retweet_count": 0, "quote_count": 0, "bookmark_count": 0, "impression_count": 50}}]})
            return Resp({"data": [{"id": "333", "text": "old", "created_at": "2026-08-01T10:00:00Z",
                                   "public_metrics": {"like_count": 5, "reply_count": 0, "retweet_count": 0, "quote_count": 0, "bookmark_count": 0, "impression_count": 90}}]})
        raise AssertionError(url)
    monkeypatch.setattr(x.httpx, "get", fake_get)
    res = x.sync("acme", days=120)
    assert res["posts"] == 3
    tl = [c for c in calls if "tweet.fields" in c]
    assert "non_public_metrics" in tl[0]["tweet.fields"] and "non_public_metrics" not in tl[1]["tweet.fields"]
    m = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='buf-x'")}
    assert m["impressions"] == 500 and m["clicks"] == 7 and m["saves"] == 3       # merged into the Buffer post
    assert db.execute("SELECT count(*) FROM posts WHERE id IN ('twitter:222','twitter:333')").fetchone()[0] == 2


def test_linkedin_member_and_org(sandbox, monkeypatch):
    import time
    from sma import config, store
    from sma.connectors import linkedin, oauth
    db = store.connect()
    _buffer_post(db, store, "buf-li", "linkedin", "https://www.linkedin.com/feed/update/urn:li:share:7001", "profile", "cp")
    _buffer_post(db, store, "buf-pg", "linkedin", "https://www.linkedin.com/feed/update/urn:li:ugcPost:8001", "page", "cg")
    _buffer_post(db, store, "buf-pg2", "linkedin", "https://www.linkedin.com/feed/update/urn:li:ugcPost:8002", "page", "cg")
    db.commit()
    for name, extra in (("linkedin_member", {}), ("linkedin_org", {"org_id": "555"})):
        oauth.save_token(name, "acme", {"access_token": f"li-{name}-123456", "expires_at": int(time.time()) + 30 * 86400, **extra})
    acct = config.load_account("acme")
    acct["connectors"] = {"linkedin_member": {"mode": "member"}, "linkedin_org": {"mode": "org", "org_id": "555"}}
    config.save_account("acme", acct)
    seen = []

    def fake_get(url, timeout=None, headers=None):
        seen.append(url)
        assert headers["linkedin-version"] and headers["x-restli-protocol-version"] == "2.0.0"
        if "memberCreatorPostAnalytics" in url:
            assert "entity=(share:urn%3Ali%3Ashare%3A7001)" in url
            q = url.split("queryType=")[1].split("&")[0]
            return Resp({"elements": [{"count": {"IMPRESSION": 1000, "REACTION": 30, "POST_SAVE": 4}.get(q, 1), "metricType": q}]})
        if "organizationalEntityShareStatistics" in url:
            assert "ugcPosts=List(urn%3Ali%3AugcPost%3A8001,urn%3Ali%3AugcPost%3A8002)" in url
            return Resp({"elements": [{"ugcPost": "urn:li:ugcPost:8001", "totalShareStatistics": {
                "impressionCount": 2000, "uniqueImpressionsCount": 1500, "clickCount": 40, "likeCount": 20,
                "commentCount": 3, "shareCount": 1, "engagement": 0.032}}]})
        if "networkSizes" in url:
            return Resp({"firstDegreeSize": 4321})
        if "organizationalEntityFollowerStatistics" in url:
            return Resp({"elements": [{"followerCountsBySeniority": [{"seniority": "urn:li:seniority:5", "followerCounts": {"organicFollowerCount": 70, "paidFollowerCount": 2}}]}]})
        raise AssertionError(url)
    monkeypatch.setattr(linkedin.httpx, "get", fake_get)
    res = linkedin.sync("acme")
    assert res["member"]["posts"] == 1 and res["org"]["posts"] == 2, res
    m = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='buf-li'")}
    assert m["impressions"] == 1000 and m["saves"] == 4
    pg2 = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='buf-pg2'")}
    assert pg2["impressions"] == 0                                  # omitted by LinkedIn = no activity
    pg = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='buf-pg'")}
    assert round(pg["engagementRate"], 1) == 3.2
    assert db.execute("SELECT value FROM account_metrics WHERE metric='followers'").fetchone()[0] == 4321
    assert db.execute("SELECT value FROM account_metrics WHERE metric='audience:seniority:5'").fetchone()[0] == 72


def test_threads_sync(sandbox, monkeypatch):
    from sma import config, store
    from sma.connectors import threads
    config.write_private(threads._token_path("acme"), json.dumps(
        {"access_token": "th-123456789", "user_id": "9", "username": "acme", "refreshed_at": store.now()}))

    class R(Resp):
        def __init__(self, d, status=200):
            super().__init__(d, status)
            self.headers = {"content-type": "application/json"}

    def fake_get(url, params=None, timeout=None):
        if url.endswith("/me/threads"):
            return R({"data": [{"id": "t1", "text": "hello?", "media_type": "TEXT_POST", "permalink": "https://www.threads.net/@acme/post/SC1",
                                "timestamp": "2026-10-25T12:00:00+0000", "shortcode": "SC1"},
                               {"id": "t2", "media_type": "REPOST_FACADE", "timestamp": "2026-10-24T12:00:00+0000"}]})
        if url.endswith("/t1/insights"):
            return R({"data": [{"name": "views", "values": [{"value": 300}]}, {"name": "likes", "values": [{"value": 9}]},
                               {"name": "replies", "values": [{"value": 3}]}]})
        if url.endswith("/me/threads_insights"):
            if params.get("metric") == "follower_demographics":
                return R({"error": {"message": "needs 100 followers"}}, 400)
            return R({"data": [{"name": "followers_count", "total_value": {"value": 77}},
                               {"name": "views", "values": [{"value": 10, "end_time": "2026-10-25T07:00:00+0000"}]},
                               {"name": "clicks", "total_value": {"value": 5}}]})
        raise AssertionError(url)
    monkeypatch.setattr(threads.httpx, "get", fake_get)
    res = threads.sync("acme", days=30)
    db = store.connect()
    m = {r["metric"]: r["value"] for r in db.execute("SELECT metric, value FROM post_metrics WHERE post_id='threads:SC1'")}
    assert m["views"] == 300 and round(m["engagementRate"], 1) == 4.0
    assert db.execute("SELECT count(*) FROM posts WHERE service='threads'").fetchone()[0] == 1   # repost facade skipped
    assert db.execute("SELECT value FROM account_metrics WHERE metric='followers'").fetchone()[0] == 77
    assert any("demographics" in w for w in res["warnings"])


def test_oauth_loopback_flow(sandbox, monkeypatch, capsys):
    """Simulate the browser: open the authorize URL's redirect with the right state + code."""
    import socket
    import threading
    import urllib.request
    from urllib.parse import parse_qs, urlparse
    from sma import config
    from sma.connectors import oauth
    s = socket.socket(); s.bind(("127.0.0.1", 0)); free = s.getsockname()[1]; s.close()
    monkeypatch.setitem(config._ENV, "SMA_OAUTH_PORT", str(free))
    posted = {}

    def fake_browser(url):
        q = parse_qs(urlparse(url).query)
        assert q["code_challenge_method"] == ["S256"] and q["redirect_uri"] == [f"http://localhost:{free}/callback"]
        threading.Timer(0.2, lambda: urllib.request.urlopen(
            f"http://127.0.0.1:{free}/callback?code=abc&state={q['state'][0]}").read()).start()
        return True

    def fake_post(url, data=None, auth=None, timeout=None):
        posted.update(data=data, auth=auth)
        return Resp({"access_token": "new-token-123456", "refresh_token": "r", "expires_in": 7200})
    monkeypatch.setattr(oauth.webbrowser, "open", fake_browser)
    monkeypatch.setattr(oauth.httpx, "post", fake_post)
    tok = oauth.authorize(auth_url="https://example.com/auth", token_url="https://example.com/token", client_id="cid",
                          client_secret="sec", scopes=["a", "b"], pkce=True, basic_auth=True, timeout=10)
    assert tok["access_token"] == "new-token-123456"
    assert posted["data"]["code"] == "abc" and "code_verifier" in posted["data"] and posted["auth"] == ("cid", "sec")
    assert "authorize_url" in capsys.readouterr().out
