# Facebook Ads — Implementation Plan

_How to add Facebook Ads to the existing Google Ads MCP server_

---

## 1. What We're Building

Three agents from `new_plan.md` require Facebook data:

| Agent | Data Needed |
|---|---|
| Ad Fatigue Monitor | Ad set frequency, campaign objective, spend |
| Creative Performance Ranker | Ad-level CTR, cost-per-result, creative name/ID |
| Weekly Paid Traffic Digest | Account-level spend, clicks, conversions (cross-platform) |

All three follow the same pattern as the Google Ads tools: read-only data pull → format → return text to Claude. No write operations needed for Facebook in Phase 1.

---

## 2. Architecture — How Facebook Fits In

The Facebook layer slots into the exact same two-layer architecture already in place:

```
Claude (MCP)
    │  stdio
    ▼
mcp_server/server.py        ← add 4 new tool definitions here
    │  HTTP
    ▼
backend/main.py             ← add Facebook routes here
    │
    ├── Redis               ← same cache layer, same TTL pattern
    ├── PostgreSQL          ← add fb_ad_accounts table (see Section 5)
    └── Facebook Graph API  ← new: backend/facebook/ module
```

Nothing about the transport, caching, or MCP layer changes. Facebook is just another set of routes in the FastAPI backend.

---

## 3. Facebook Graph API — What We Need

**SDK:** `facebook-sdk` Python package (or raw `httpx` — the Graph API is simple REST, no gRPC).  
**Auth:** Long-lived System User token tied to the MethodPro Business Manager. One token covers all client ad accounts under the BM. Store in `.env` as `FB_ACCESS_TOKEN`.  
**API version:** v21.0 (current stable as of April 2026).  
**Rate limits:** Graph API uses a points-based system. At agency scale (~20 accounts) with 3-hour cache TTL, we stay well under the per-account limit.

Add to `pyproject.toml`:
```
facebook-sdk>=3.1
```

Or skip the SDK entirely — the Graph API is just `GET` requests. The `httpx` client we already have in `mcp_server/client.py` is sufficient.

---

## 4. New Backend Module: `backend/facebook/`

Mirror the structure of `backend/google_ads/`:

```
backend/facebook/
    __init__.py
    auth.py          ← returns configured Graph API base URL + token header
    reporting.py     ← ad account summary, ad set frequency, creative performance
```

### `auth.py`
```python
import os

FB_BASE = "https://graph.facebook.com/v21.0"

def get_headers() -> dict:
    token = os.environ["FB_ACCESS_TOKEN"]
    return {"Authorization": f"Bearer {token}"}
```

### `reporting.py` — three functions needed

**`get_ad_account_summary(ad_account_id, date_range)`**  
Endpoint: `GET /{ad_account_id}/insights`  
Fields: `impressions, clicks, spend, actions` (conversions), `ctr`  
Used by: Weekly Digest tool

**`get_adset_frequency(ad_account_id, date_range)`**  
Endpoint: `GET /{ad_account_id}/adsets?fields=name,status,objective,insights{frequency,impressions,spend}`  
Returns: list of ad sets with frequency, spend, objective  
Used by: Ad Fatigue Monitor tool

**`get_creative_performance(ad_account_id, date_range)`**  
Endpoint: `GET /{ad_account_id}/ads?fields=name,creative{id,name},insights{ctr,cost_per_result,impressions,spend}`  
Returns: list of ads ranked by CTR / cost-per-result  
Used by: Creative Performance Ranker tool

---

## 5. Database — One New Table

The `client_accounts` table currently stores Google Ads `customer_id`. Facebook uses a separate `ad_account_id` (format: `act_XXXXXXXXXX`). One clinic may have both.

**New table: `fb_ad_accounts`**

```sql
CREATE TABLE fb_ad_accounts (
    id              SERIAL PRIMARY KEY,
    client_account_id INTEGER REFERENCES client_accounts(id),
    ad_account_id   VARCHAR(30) UNIQUE NOT NULL,  -- e.g. act_1234567890
    name            VARCHAR(255),
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

Add the corresponding SQLAlchemy model to `backend/models/schemas.py`.  
Add an Alembic migration.

The resolver stays simple: given a clinic name → look up both `customer_id` (Google) and `ad_account_id` (Facebook) from the DB.

---

## 6. New FastAPI Routes in `backend/main.py`

```
GET  /fb/accounts/{ad_account_id}/summary          → ad account spend/clicks/conv
GET  /fb/accounts/{ad_account_id}/adset-frequency  → frequency per ad set
GET  /fb/accounts/{ad_account_id}/creative-performance → ads ranked by CTR / CPR
GET  /fb/accounts/fatigue/all                       → frequency check across all accounts
```

All routes follow the existing `_cached(key, ttl, refresh, fn)` pattern.  
TTL: 3 hours for all Facebook data (same as Google Ads default).

---

## 7. New MCP Tools in `mcp_server/server.py`

Add four tool definitions to the `list_tools()` return list, and four branches to `_dispatch()`:

| Tool Name | Maps To |
|---|---|
| `get_fb_account_summary` | `GET /fb/accounts/{id}/summary` |
| `get_fb_adset_frequency` | `GET /fb/accounts/{id}/adset-frequency` |
| `get_fb_creative_performance` | `GET /fb/accounts/{id}/creative-performance` |
| `get_fb_fatigue_all` | `GET /fb/accounts/fatigue/all` |

All tools accept `customer_id` (clinic name or numeric Google ID — the resolver looks up the linked Facebook ad account), `date_range`, and `refresh`.  
`get_fb_fatigue_all` takes optional `frequency_threshold` (default: 7 for awareness, 3.5 for conversion).

---

## 8. Resolver Update

`backend/resolver.py` needs one new function:

```python
async def resolve_fb_ad_account(identifier: str, db: AsyncSession) -> tuple[str, str]:
    """
    Given a clinic name or Google customer_id, return (ad_account_id, account_name).
    Looks up fb_ad_accounts joined to client_accounts.
    """
```

Same fuzzy-match logic as `resolve_customer_id` — just queries `fb_ad_accounts` instead.

---

## 9. Build Order

1. **Add `facebook-sdk` or confirm raw `httpx` is sufficient** — 30 min
2. **Write `backend/facebook/auth.py` + `reporting.py`** — 1 day (three API functions, test against one real account)
3. **DB migration** — add `fb_ad_accounts` table + seed data for existing clients — 2 hours
4. **FastAPI routes** — 4 routes following existing pattern — 2 hours
5. **MCP tool definitions + dispatcher branches** — 4 tools — 1 hour
6. **Resolver update** — 1 hour
7. **End-to-end test** — ask Claude "get ad fatigue for Apex Dental" and verify the chain — 1 hour

**Total: ~2 days of focused work.**

---

## 10. What This Unlocks

Once Facebook is wired in, the three remaining agents from `new_plan.md` become schedulable:

- **Ad Fatigue Monitor** → cron job calls `get_fb_fatigue_all`, posts Cliq alert when frequency > threshold
- **Creative Performance Ranker** → cron job calls `get_fb_creative_performance` per account, posts weekly rankings
- **Weekly Paid Traffic Digest** → cron job calls both `get_account_summary` (Google) and `get_fb_account_summary` (Facebook), Claude summarizes cross-platform into one digest per client

The MCP tools also immediately work interactively — Pooja can ask "what's the frequency on LJDW's Facebook campaigns right now?" before the scheduled agents are even built.
