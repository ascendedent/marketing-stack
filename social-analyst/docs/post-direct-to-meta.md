# Posting straight to Meta (Facebook, Instagram, Threads)

Use this when a scheduler in the middle is not wanted: `scripts/meta_publish.py` talks to Meta's own
APIs. Everything here was done live on 2026-11-16 (Graph API v27.0). Menu names move; the steps hold.

## What you get, and the catch

| Network | What the API can do | The gate a person keeps |
|---|---|---|
| Facebook page | Schedule videos, reels and pictures; comment as the page | Posts wait in Meta Business Suite's planner until their time |
| Instagram | Publish now; comment on your own posts | None at Meta: a post is public the moment it is made |
| Threads | Publish now; reply to your own posts | None at Meta: same |

Instagram and Threads have no draft or scheduled state through the API. If "nothing goes public without
a person" matters, the gate has to live on your side. The script asks for a typed confirmation at a
terminal and refuses when there is none.

## One-time setup

**1. The app** (developers.facebook.com)
- Create App, type Business, attached to the business portfolio. Add the use case
  "Manage everything on your Page"; for Instagram also "Manage messaging & content on Instagram"; for
  Threads also "Access the Threads API".
- Basic settings need a privacy policy URL (any real page of yours).
- Switch the app to **Live**. Posts made by an app in Development mode are only visible to people with a
  role on the app.
- No App Review is needed while the app only touches assets the same portfolio owns.

**2. The system user** (business portfolio → Settings → Users → System users)
- Add one with the Admin role. Assign it the page, the app and the Instagram account, full control.
- The Instagram account must be Business or Creator, linked to the page, and listed under the
  portfolio's Instagram accounts.
- Generate token → pick the app → expiry Never → tick only what is used:
  `pages_show_list`, `pages_manage_posts`, `pages_read_engagement`, `pages_manage_engagement`,
  `pages_read_user_content`, `read_insights`, `business_management`, and for Instagram
  `instagram_basic`, `instagram_content_publish`, `instagram_manage_comments`,
  `instagram_manage_insights`. Leave ads, catalog and messaging permissions off: a leaked token should
  not reach the ad accounts.
- A token made before the Instagram account was assigned does not gain it later. Generate a new one.

**3. Threads is separate**
- The system user token does not work on `graph.threads.net`. Threads needs its own user token.
- In the app's Threads use case → Settings: add the profile as a Threads Tester. The profile's owner
  accepts under Threads → Settings → Account → Website permissions → Invites. Then "User Token
  Generator" on that same Settings page offers the profile. The profile must be public.
- The token lasts about 60 days; `GET graph.threads.net/refresh_access_token?grant_type=th_refresh_token`
  gives a fresh one once it is a day old.

**4. Environment**
```
META_SYSTEM_TOKEN=   # the system user token
META_PAGE_ID=        # the page's numeric id
META_IG_USER_ID=     # GET /{page-id}?fields=instagram_business_account
THREADS_TOKEN=       # from the Threads token generator
```
The person pastes tokens into the env file themselves. Never ask for one in chat, never print one.
The page token every Facebook call needs comes from `GET /{page-id}?fields=access_token` with the system
token; do not store it.

## Checking a token without posting

`GET /me/permissions` lists what was granted. `GET /me/accounts?fields=id,name,tasks` shows the page.
`GET graph.threads.net/v1.0/me?fields=id,username` and `.../me/threads_publishing_limit` prove the
Threads token and that publishing is allowed. All read-only.

## Scheduling Instagram and Threads without a watcher

A polling job is not needed. When a person approves a post, queue one one-time job for its minute
(`at -t YYYYMMDDhhmm` on Linux; `atd` runs a missed job at next boot). Start the job ten minutes early
so the video is fetched and processed, sleep until the minute, publish, then add the comment. Have the
job refuse to post when it starts hours late, and write why to a log beside the media. Record the
approval and the job id next to the media so a second run cannot post twice.
