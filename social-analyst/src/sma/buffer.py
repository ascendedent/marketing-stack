"""Buffer GraphQL client (https://api.buffer.com).

Safety rules baked in:
- Writes default to a Buffer *Idea* (Create board) or a draft post. Never `shareNow` unless the
  caller passes `confirm_publish_now=True`, which the CLI only sets on an explicit `--now --yes`.
- Keys are never printed; every error string is passed through `config.redact`.
- The public API cannot delete an Idea. Do not create probe ideas.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterator

import httpx

from . import config

API = "https://api.buffer.com"

_SERVICES = ["Instagram", "Facebook", "LinkedIn", "Twitter", "Pinterest", "GoogleBusiness",
             "Youtube", "Mastodon", "Tiktok", "Threads", "Bluesky", "Substack"]
_META_TYPE = " ".join(f"... on {s}PostMetadata {{ type }}" for s in _SERVICES)

POST_FIELDS = f"""
  id text status shareMode channelId channelService createdAt dueAt sentAt externalLink
  metricsUpdatedAt metrics {{ type value unit }}
  assets {{ type mimeType source thumbnail }}
  tags {{ id name }}
  metadata {{ __typename {_META_TYPE} }}
"""

# Text limits per service (characters; LinkedIn counts URLs as 24).
LIMITS = {"linkedin": 3000, "twitter": 280, "threads": 500, "bluesky": 300, "instagram": 2200,
          "tiktok": 2200, "facebook": 63206, "pinterest": 500, "mastodon": 500, "youtube": 5000}


class BufferError(RuntimeError):
    pass


@dataclass
class Channel:
    id: str
    login: str
    organization_id: str
    service: str
    type: str
    name: str
    display_name: str | None
    is_disconnected: bool
    timezone: str | None
    external_link: str | None


class Buffer:
    def __init__(self, login: str = "default"):
        logins = config.buffer_logins()
        if login not in logins:
            raise BufferError(
                f"no Buffer key for login '{login}'. Set BUFFER_API_KEY (default) or "
                f"BUFFER_API_KEY_{login.upper()} in .env. Known logins: {sorted(logins) or 'none'}")
        self.login = login
        self._key = logins[login]
        self._http = httpx.Client(timeout=60)

    # ---- transport ---------------------------------------------------------
    def gql(self, query: str, variables: dict | None = None) -> dict:
        for attempt in range(4):
            r = self._http.post(API, json={"query": query, "variables": variables or {}},
                                headers={"authorization": f"Bearer {self._key}"})
            if r.status_code == 429 and attempt < 3:
                time.sleep(min(int(r.headers.get("retry-after", "30")), 120))
                continue
            break
        text = config.redact(r.text)
        try:
            body = r.json()
        except ValueError:
            raise BufferError(f"HTTP {r.status_code}, not JSON: {text[:300]}") from None
        if r.status_code >= 400 or body.get("errors"):
            msg = "; ".join(e.get("message", "?") for e in body.get("errors") or []) or text[:500]
            raise BufferError(config.redact(f"Buffer GraphQL ({self.login}): {msg}"))
        return body["data"]

    # ---- reads -------------------------------------------------------------
    def organizations(self) -> list[dict]:
        return self.gql("{ account { organizations { id name } } }")["account"]["organizations"]

    def channels(self) -> list[Channel]:
        out = []
        for org in self.organizations():
            data = self.gql(
                """query($o: OrganizationId!) { channels(input: { organizationId: $o }) {
                     id name service type displayName isDisconnected organizationId timezone externalLink } }""",
                {"o": org["id"]})
            for c in data["channels"]:
                out.append(Channel(c["id"], self.login, c["organizationId"], c["service"], c["type"], c["name"],
                                   c.get("displayName"), c["isDisconnected"], c.get("timezone"), c.get("externalLink")))
        return out

    def posts(self, organization_id: str, *, channel_ids: list[str] | None = None,
              status: list[str] | None = None, since: str | None = None, until: str | None = None,
              limit: int = 500, page_size: int = 50) -> Iterator[dict]:
        """Newest first. `since`/`until` filter on dueAt (ISO-8601)."""
        flt: dict[str, Any] = {}
        if channel_ids:
            flt["channelIds"] = channel_ids
        if status:
            flt["status"] = status
        if since or until:
            flt["dueAt"] = {k: v for k, v in (("start", since), ("end", until)) if v}
        query = f"""query($o: OrganizationId!, $first: Int, $after: String, $f: PostsFiltersInput) {{
          posts(first: $first, after: $after, input: {{ organizationId: $o, filter: $f,
                sort: [{{ field: dueAt, direction: desc }}] }}) {{
            edges {{ node {{ {POST_FIELDS} }} }} pageInfo {{ hasNextPage endCursor }} }} }}"""
        after, n = None, 0
        while n < limit:
            data = self.gql(query, {"o": organization_id, "first": min(page_size, limit - n),
                                    "after": after, "f": flt or None})["posts"]
            for e in data["edges"] or []:
                yield e["node"]
                n += 1
            if not data["pageInfo"]["hasNextPage"] or not data["pageInfo"]["endCursor"]:
                break
            after = data["pageInfo"]["endCursor"]

    def post(self, post_id: str) -> dict:
        return self.gql(f"query($id: PostId!) {{ post(input: {{ id: $id }}) {{ {POST_FIELDS} }} }}", {"id": post_id})["post"]

    def aggregated_metrics(self, organization_id: str, start: str, end: str,
                           channel_ids: list[str] | None = None) -> dict:
        return self.gql(
            """query($i: AggregatedPostMetricsInput!) { aggregatedPostMetrics(input: $i) {
                 metricsUpdatedAt metrics { type name value unit } } }""",
            {"i": {"organizationId": organization_id, "startDateTime": start, "endDateTime": end,
                   "channelIds": channel_ids}})["aggregatedPostMetrics"]

    def idea_groups(self, organization_id: str) -> list[dict]:
        return self.gql("query($o: ID!) { ideaGroups(input: { organizationId: $o }) { id name } }",
                        {"o": organization_id})["ideaGroups"]

    def posting_schedule(self, channel_id: str) -> dict:
        return self.gql("""query($id: ChannelId!) { channel(input: { id: $id }) {
            name service timezone postingSchedule { day times paused } } }""", {"id": channel_id})["channel"]

    def daily_limits(self, channel_ids: list[str]) -> list[dict]:
        return self.gql("""query($ids: [ChannelId!]!) { dailyPostingLimits(input: { channelIds: $ids }) {
            channelId sent scheduled limit isAtLimit } }""", {"ids": channel_ids})["dailyPostingLimits"]

    # ---- writes ------------------------------------------------------------
    def create_post(self, *, channel_id: str, text: str, mode: str = "addToQueue", due_at: str | None = None,
                    save_to_draft: bool = True, images: list[str] | None = None, videos: list[str] | None = None,
                    metadata: dict | None = None, needs_approval: bool = False,
                    confirm_publish_now: bool = False, dry_run: bool = False) -> dict:
        if mode == "shareNow" and not confirm_publish_now:
            raise BufferError("refusing shareNow without explicit confirmation (--now --yes)")
        if mode == "customScheduled" and not due_at:
            raise BufferError("customScheduled needs due_at (ISO-8601 UTC)")
        assets = [{"image": {"url": u}} for u in images or []] + [{"video": {"url": u}} for u in videos or []]
        inp: dict[str, Any] = {"text": text, "channelId": channel_id, "schedulingType": "automatic", "mode": mode,
                               "saveToDraft": save_to_draft and mode != "shareNow", "needsApproval": needs_approval}
        if due_at:
            inp["dueAt"] = due_at
        if assets:
            inp["assets"] = assets
        if metadata:
            inp["metadata"] = metadata
        if dry_run:
            return {"dry_run": True, "input": inp}
        data = self.gql(f"""mutation($i: CreatePostInput!) {{ createPost(input: $i) {{
            ... on PostActionSuccess {{ post {{ {POST_FIELDS} }} }}
            ... on MutationError {{ message }} }} }}""", {"i": inp})["createPost"]
        if "message" in data:
            raise BufferError(data["message"])
        return data["post"]

    def create_idea(self, *, organization_id: str, text: str, title: str, group_name: str = "In Progress",
                    services: list[str] | None = None, date: str | None = None, tags: list[dict] | None = None,
                    image_urls: list[str] | None = None, dry_run: bool = False) -> dict:
        groups = {g["name"]: g["id"] for g in self.idea_groups(organization_id)}
        if group_name not in groups:
            raise BufferError(f"no Create-board column named '{group_name}' (have: {sorted(groups)})")
        content: dict[str, Any] = {"title": title, "text": text, "aiAssisted": True}
        if services:
            content["services"] = services
        if date:
            content["date"] = date
        if tags:  # each {id, name, color} — an existing tag; never invent tags (orgs have a small tag cap)
            content["tags"] = tags
        if image_urls:
            content["media"] = [{"url": u, "type": "image"} for u in image_urls]
        inp = {"organizationId": organization_id, "content": content, "group": {"groupId": groups[group_name]}}
        if dry_run:
            return {"dry_run": True, "input": inp}
        data = self.gql("""mutation($i: CreateIdeaInput!) { createIdea(input: $i) {
            ... on Idea { id groupId content { title } }
            ... on InvalidInputError { message } ... on UnexpectedError { message } } }""", {"i": inp})["createIdea"]
        if "message" in data:
            raise BufferError(data["message"])
        return data

    def delete_post(self, post_id: str) -> None:
        data = self.gql("""mutation($id: PostId!) { deletePost(input: { id: $id }) {
            ... on DeletePostSuccess { __typename } ... on MutationError { message } } }""", {"id": post_id})["deletePost"]
        if "message" in data:
            raise BufferError(data["message"])


def text_length(service: str, text: str) -> int:
    import re
    if service == "linkedin":
        n = len(text.encode("utf-16-le")) // 2
        for u in re.findall(r"https?://\S+", text):
            n = n - (len(u.encode("utf-16-le")) // 2) + 24
        return n
    return len(text)


def check_length(service: str, text: str) -> None:
    lim = LIMITS.get(service)
    if lim and (n := text_length(service, text)) > lim:
        raise BufferError(f"{service} text is {n} > {lim}. Cut it before it goes on the board.")
