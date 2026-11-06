# Connect LinkedIn analytics (optional depth, needs LinkedIn approval)

Buffer gives advanced analytics for LinkedIn **Pages** and basic ones for **personal profiles**.
This adds:
- **Personal profile posts** (`r_member_postAnalytics`): saves, sends, link clicks, members reached,
  followers gained and profile views driven by each post.
- **Pages** (`rw_organization_admin`): unique impressions and clicks per post, follower count over time,
  follower demographics (function, seniority, industry, country, company size).

**The catch:** both scopes belong to LinkedIn's **Community Management API**, which LinkedIn reviews.
You need a LinkedIn Page for the app, and LinkedIn generally approves registered businesses (not
individuals). Approval can take days to weeks. If you're not approved, Buffer's LinkedIn analytics
are what you have — everything else in this project still works.

## 1. App and access (once)
1. https://www.linkedin.com/developers/apps → **Create app** → associate it with your company Page →
   verify the Page (a Page admin approves the request).
2. **Products** tab → request **Community Management API** → fill in the access form (use case:
   "analytics for our own Page and posts"). Wait for approval.
3. **Auth** tab → **Authorized redirect URLs** → add `http://localhost:8765/callback` exactly.
   Copy **Client ID** and **Client Secret**.

## 2. Connect
```bash
uv run sma setup keys --only LINKEDIN_CLIENT_ID,LINKEDIN_CLIENT_SECRET

# personal profile posts (sign in as that person)
uv run sma connect linkedin <slug> --mode member

# a Page you administer (sign in as a Page admin); org id = the number in the Page admin URL
uv run sma connect linkedin <slug> --mode org --org-id 12345678

uv run sma sync <slug>
```
The connector reads post URNs from the Buffer posts already synced for that account (Buffer's post
link contains `urn:li:share:…` / `urn:li:ugcPost:…`), so link the LinkedIn channels in Buffer and run
`sma sync` first. Posts published outside Buffer aren't covered.

## Tokens
Access tokens last **60 days**. LinkedIn issues refresh tokens only to some approved apps; if yours
has one, `sync` refreshes automatically. Otherwise `sma setup status` / sync will tell you to rerun
`sma connect linkedin …` when it expires. `LINKEDIN_API_VERSION` (default `202610`, format YYYYMM)
pins the API version — LinkedIn sunsets versions after ~1 year.

## Rate/volume
Member analytics take one call per metric per post (10 per post); `sync` handles the 100 most recent
posts. Page analytics batch 20 posts per call. Data covers the last 12 months (LinkedIn's window).
