"""Post to a Facebook page, an Instagram account and a Threads profile straight through Meta's APIs.

usage: python scripts/meta_publish.py facebook-video FILE --at 2026-01-06T17:00:00Z [--text-file F] [--comment-file F]
       python scripts/meta_publish.py facebook-photo FILE --at 2026-01-06T17:00:00Z [--text-file F]
       python scripts/meta_publish.py instagram-reel URL [--text-file F] [--comment-file F]
       python scripts/meta_publish.py threads-video  URL [--text-file F] [--comment-file F]

Facebook is only ever SCHEDULED: the post waits in Meta Business Suite's planner, where a person can edit,
move or delete it, and goes out at --at. A video of 90 seconds or less goes up as a reel. --comment-file is
posted as the page's comment while the video is still scheduled, so it is there when the video goes live.

Instagram and Threads have no draft or scheduled state: a post is public the moment it is made. Those two
commands prepare the post, then ask a person at a keyboard to type "post"; run by an agent or a script they
stop there and nothing is posted. Both take the video from a public web link (URL), not a local file.
To post one at a set time, a person queues this same command with `at` after reading what it will post.

Setup and the facts behind each call: docs/post-direct-to-meta.md. Needs in the environment:
META_SYSTEM_TOKEN and META_PAGE_ID (Facebook), plus META_IG_USER_ID (Instagram), THREADS_TOKEN (Threads).
Prints the ids of what it made as JSON. It keeps no record: the caller must not run it twice for one post.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

G = "https://graph.facebook.com/"
TH = "https://graph.threads.net/v1.0/"
# IPv4 only: on a machine whose IPv6 route to Meta is dead every call waits about 20 seconds before falling back
HTTP = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"), timeout=900)


def call(method, url, token, **kw):
    r = HTTP.request(method, url, headers={"Authorization": "Bearer " + token, **kw.pop("headers", {})}, **kw)
    out = r.json()
    assert r.is_success and "error" not in out, f"Meta refused {method} {url.split('?')[0]}: {json.dumps(out)[:600]}"
    return out


def page_token():
    return call("GET", G + os.environ["META_PAGE_ID"], os.environ["META_SYSTEM_TOKEN"], params={"fields": "access_token"})["access_token"]


def read(path):
    return Path(path).read_text().strip() if path else ""


def facebook_video(a):
    page, tok, video, text = os.environ["META_PAGE_ID"], page_token(), Path(a.media), read(a.text_file)
    secs = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
                                check=True, capture_output=True, text=True).stdout)
    if secs <= 90:  # the Reels API takes 90 seconds at most
        start = call("POST", f"{G}{page}/video_reels", tok, data={"upload_phase": "start"})
        vid = start["video_id"]
        call("POST", start["upload_url"], tok, content=video.read_bytes(),
             headers={"Authorization": "OAuth " + tok, "offset": "0", "file_size": str(video.stat().st_size)})
        call("POST", f"{G}{page}/video_reels", tok, data={"upload_phase": "finish", "video_id": vid, "video_state": "SCHEDULED",
                                                         "scheduled_publish_time": a.when, "description": text})
    else:  # sent in pieces: one request for a whole 300 MB video is refused
        up = f"https://graph-video.facebook.com/{page}/videos"
        part = call("POST", up, tok, data={"upload_phase": "start", "file_size": video.stat().st_size})
        vid, session = part["video_id"], part["upload_session_id"]
        with open(video, "rb") as f:
            while int(part["start_offset"]) < int(part["end_offset"]):
                f.seek(int(part["start_offset"]))
                piece = f.read(int(part["end_offset"]) - int(part["start_offset"]))
                part = call("POST", up, tok, data={"upload_phase": "transfer", "upload_session_id": session, "start_offset": part["start_offset"]},
                            files={"video_file_chunk": piece})
        call("POST", up, tok, data={"upload_phase": "finish", "upload_session_id": session, "description": text,
                                    "published": "false", "scheduled_publish_time": a.when})
    seen = call("GET", G + vid, tok, params={"fields": "published,scheduled_publish_time"})
    out = {"video_id": vid, "type": "reel" if secs <= 90 else "video", "scheduled_for": seen.get("scheduled_publish_time")}
    print(json.dumps(out))  # printed before the check, so the id is known even when the check fails
    assert seen.get("published") is False, f"video {vid} is not waiting as scheduled ({seen}): delete it in Business Suite now"
    if a.comment_file:
        print(json.dumps({"comment_id": call("POST", f"{G}{vid}/comments", tok, data={"message": read(a.comment_file)})["id"]}))


def facebook_photo(a):
    page, tok = os.environ["META_PAGE_ID"], page_token()
    with open(a.media, "rb") as f:
        pid = call("POST", f"{G}{page}/photos", tok, files={"source": f}, data={"published": "false", "temporary": "true"})["id"]
    # a page post holding the picture: a picture scheduled on its own never shows in Business Suite's Scheduled list
    post = call("POST", f"{G}{page}/feed", tok, data={"message": read(a.text_file), "published": "false", "scheduled_publish_time": a.when,
                                                     "unpublished_content_type": "SCHEDULED", "attached_media[0]": json.dumps({"media_fbid": pid})})["id"]
    print(json.dumps({"post_id": post}))
    assert call("GET", G + post, tok, params={"fields": "is_published"})["is_published"] is False, f"post {post} is not waiting as scheduled: delete it now"


def wait(url, token, field):
    for _ in range(90):
        state = call("GET", url, token, params={"fields": field})
        if state[field] == "FINISHED":
            return
        assert state[field] == "IN_PROGRESS", f"Meta could not process the video: {state}"
        time.sleep(10)
    raise SystemExit("Meta was still processing the video after 15 minutes; nothing was posted")


def typed_go(what):
    """The gate: a person at a keyboard. Anything else posts nothing."""
    if not sys.stdin.isatty():
        raise SystemExit(f"ready, NOT posted: {what} is public the moment it goes out, so a person must start this at a terminal")
    if input(f"This makes {what} public right now. Type post to go ahead: ").strip() != "post":
        raise SystemExit("nothing was posted")


def instagram_reel(a):
    ig, tok = os.environ["META_IG_USER_ID"], os.environ["META_SYSTEM_TOKEN"]
    box = call("POST", f"{G}{ig}/media", tok, data={"media_type": "REELS", "video_url": a.media, "caption": read(a.text_file), "share_to_feed": "true"})["id"]
    wait(G + box, tok, "status_code")
    typed_go("the Instagram reel")
    media = call("POST", f"{G}{ig}/media_publish", tok, data={"creation_id": box})["id"]
    print(json.dumps({"media_id": media}))
    if a.comment_file:
        print(json.dumps({"comment_id": call("POST", f"{G}{media}/comments", tok, data={"message": read(a.comment_file)})["id"]}))


def threads_video(a):
    tok, text = os.environ["THREADS_TOKEN"], read(a.text_file)
    assert len(text) <= 500, f"Threads takes 500 characters and this text is {len(text)}"
    box = call("POST", TH + "me/threads", tok, data={"media_type": "VIDEO", "video_url": a.media, "text": text})["id"]
    wait(TH + box, tok, "status")
    typed_go("the Threads post")
    post = call("POST", TH + "me/threads_publish", tok, data={"creation_id": box})["id"]
    print(json.dumps({"post_id": post}))
    if a.comment_file:  # Threads has no comments: a reply to your own post does the job
        r = call("POST", TH + "me/threads", tok, data={"media_type": "TEXT", "text": read(a.comment_file)[:500], "reply_to_id": post})["id"]
        print(json.dumps({"reply_id": call("POST", TH + "me/threads_publish", tok, data={"creation_id": r})["id"]}))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["facebook-video", "facebook-photo", "instagram-reel", "threads-video"])
    ap.add_argument("media", help="a local file for Facebook, a public web link for Instagram and Threads")
    ap.add_argument("--at", help="Facebook only: when it goes out, like 2026-01-06T17:00:00Z")
    ap.add_argument("--text-file", help="file holding the caption")
    ap.add_argument("--comment-file", help="file holding the first comment (a reply on Threads)")
    a = ap.parse_args()
    if a.what.startswith("facebook"):
        assert a.at, "Facebook posts are only ever scheduled: give --at"
        when = dt.datetime.fromisoformat(a.at.replace("Z", "+00:00"))
        assert when > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=20), f"{a.at} is too soon: Facebook needs a time at least 20 minutes away"
        a.when = int(when.timestamp())
    {"facebook-video": facebook_video, "facebook-photo": facebook_photo, "instagram-reel": instagram_reel, "threads-video": threads_video}[a.what](a)


if __name__ == "__main__":
    main()
