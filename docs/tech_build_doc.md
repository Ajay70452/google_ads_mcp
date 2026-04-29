# Google Ads MCP + Agents — Technical Build Doc

A high-level engineering view of how the system is built. Aimed at someone joining the codebase or evaluating the architecture — not a full reference. For deployment specifics see [deployment_plan.md](deployment_plan.md); for end-user behavior see [usage_doc.md](usage_doc.md).

---

## 1. What it is

Two integrated systems sharing one cloud backend:

**System A — Conversational MCP layer.** Connects Claude Desktop to MethodPro's entire Google Ads MCC (40 client accounts). Users ask Claude questions in plain English; the system fetches live data, runs analysis, and — for write actions — applies changes through the Google Ads API after a preview/confirm step.

**System B — Autonomous agent platform.** Three scheduled AI agents run on the cloud backend without human intervention. They scan every account on a cron schedule, run statistical and AI-based analysis, and post structured reports to Zoho Cliq channels:

- **Budget Pacing Monitor** (daily 08:00 UTC) — flags campaigns >15% off monthly pace
- **Performance Anomaly Detector** (Monday 08:00 UTC) — week-over-week deviation analysis vs trailing 4-week baseline
- **Search Terms AI Classifier** (Monday 09:00 UTC) — combines spend rules + GPT classification for negative-keyword triage

Both systems share the same `backend/google_ads/*` modules, the same Postgres + Redis instances, the same auth layer. The split is **transport, not logic** — System A reaches the data via FastAPI HTTP, System B imports the modules directly. One source of truth, two access patterns.

---

## 2. System architecture

Three layers, deployed in different places:

```
┌──────────────────────────────┐
│  USER LAPTOP                 │
│  Claude Desktop              │
│       │ (stdio)              │
│       ▼                      │
│  MCP server (Python)         │──── HTTPS/HTTP ──┐
└──────────────────────────────┘                  │
                                                  ▼
                            ┌─────────────────────────────────────┐
                            │  AWS EC2 (docker-compose)           │
                            │  ┌────────────────────────────┐     │
                            │  │  FastAPI backend           │─────┼──→ Google Ads API
                            │  │  Scheduler (APScheduler)   │─────┼──→ OpenAI (gpt-4o-mini)
                            │  │  Postgres 16               │─────┼──→ Zoho Cliq webhooks
                            │  │  Redis 7                   │     │
                            │  └────────────────────────────┘     │
                            └─────────────────────────────────────┘
```

**Why this split:** The MCP server has to live on the user's laptop because Claude Desktop launches it as a stdio subprocess — that's how the MCP spec works. Everything else (logic, secrets, state) lives in the cloud where it belongs.

---

## 3. The three layers

### 3.1 MCP server (laptop side)

A thin Python process. Claude Desktop launches it on startup via the user's [`claude_desktop_config.json`](deployment_plan.md#L280-L292). All it does:

- Registers **12 tools** with Claude (the contract is in [mcp_server/server.py](../mcp_server/server.py))
- Translates each tool call into an HTTP request to the cloud backend
- Formats the JSON response back into markdown that reads well in chat

It owns no business logic. No Google Ads SDK, no DB connection, no caching. It's a stdio↔HTTP bridge with formatting. This means the MCP server stays small, and we can update business logic on the server without redistributing anything to users.

The HTTP client is wrapped with 3-retry logic and a 30s timeout — defends against transient network blips on the user's laptop.

### 3.2 FastAPI backend (cloud)

The brain. Runs on EC2 in a Docker container. Responsibilities:

- Holds the cached `GoogleAdsClient` (singleton — auth tokens are expensive)
- Exposes ~15 HTTP endpoints, one per logical operation
- All read endpoints check Redis first, fall back to Google Ads API on miss
- All write endpoints implement **preview/confirm** — first call returns simulated diff, second call (with `confirm=True`) executes
- Logs every write to the `change_log` table for auditability
- Tracks daily API call count against the 15k/day quota

Key submodules under [`backend/google_ads/`](../backend/google_ads/):

| Module                      | Job                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `auth.py`                   | Singleton `GoogleAdsClient`, OAuth2 refresh token loop                                                       |
| `reporting.py`              | All read GAQL queries — account summaries, campaigns, keywords, search terms, budget pacing, YTD aggregation |
| `campaigns.py`              | Campaign creation, budget updates                                                                            |
| `keywords.py`               | Negative keyword adds                                                                                        |
| `ad_copy.py`                | Calls OpenAI to generate 15 headlines + 4 descriptions, validates char limits                                |
| `search_term_classifier.py` | Calls OpenAI to classify irrelevant search terms with HIGH/MEDIUM/LOW priority                               |

**Caching strategy** (Redis): keys are `MD5(customer_id, query_type, params)`. TTL varies by recency — 1 hour for current-month data (changes throughout the day), 24 hours for historical data (immutable), 3 hours default. Every cache write also increments a daily counter so we know when we're approaching the quota.

**Write safety:** the preview/confirm pattern is enforced at the endpoint level. The MCP tool descriptions tell Claude to always preview first, but even if Claude tries to skip, the backend rejects writes without `confirm=True`. There's also a hard cap of **3× budget increase per call** to prevent a runaway "increase to $10,000/day" mistake.

### 3.3 Scheduled agents

Separate Python process running APScheduler in the same Docker stack. Three jobs:

| Agent                            | Cron             | What it does                                                                  | Posts to             |
| -------------------------------- | ---------------- | ----------------------------------------------------------------------------- | -------------------- |
| **Budget Pacing Monitor**        | Daily 08:00 UTC  | Flags campaigns >15% off expected monthly pace                                | `#pacingalerts`      |
| **Performance Anomaly Detector** | Monday 08:00 UTC | Compares last week vs trailing 4-week avg, flags >20% deviation in CPC/CTR/CR | `#performancealerts` |
| **Search Terms Agent**           | Monday 09:00 UTC | AI-classifies wasted-spend search terms across all accounts                   | `#searchtermsreview` |

All three inherit a `BaseAgent` base class that provides retry-with-backoff (3 attempts, 5s delay), structured logging, and a uniform `execute()` entrypoint.

The agents don't go through FastAPI — they call the same `backend/google_ads/*` modules directly. Same code, different transport.

---

## 4. Data model

PostgreSQL 16, four tables. Schema lives in alembic migration `45c2e0ad6e5c_initial_schema.py`.

| Table                | Purpose                                                                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `client_accounts`    | Registry of every customer ID under our MCC. Synced from Google Ads via [`scripts/seed_accounts.py`](../scripts/seed_accounts.py)   |
| `campaign_snapshots` | Daily metrics per campaign — used by anomaly detection to compare current vs trailing weeks without re-querying Google Ads          |
| `change_log`         | Audit trail for every write op. Stores `before_payload` and `after_payload` as JSONB so changes can be reconstructed or rolled back |
| `generated_ad_copy`  | History of OpenAI-generated headlines/descriptions, indexed by service + location for reuse                                         |

SQLAlchemy 2.0 async + asyncpg driver. No ORM models for read paths (raw SQL via `text()`); ORM is mostly there for migrations and the few write paths.

---

## 5. AI integration

Two distinct OpenAI calls, both `gpt-4o-mini` for cost.

**Ad copy generation** (`generate_ad_variations` tool):

- Input: clinic name, service, location, optional USPs
- Output: 15 headlines (≤30 chars) + 4 descriptions (≤90 chars), validated against Google Ads RSA limits
- Stateless; result also written to `generated_ad_copy` for future reuse

**Search term classification** (Search Terms Agent):

- Input: a list of search terms with their spend/conversion stats
- Output: per-term verdict — `IRRELEVANT / MAYBE / KEEP`, plus a reason and priority
- Combined with rule-based "high spend, zero conversions" filter to produce the weekly Cliq report

No long-running threads or memory — every call is stateless prompt → JSON response. Keeps OpenAI cost at ~$2/month.

---

## 6. External integrations

| Service            | How                                                                          |
| ------------------ | ---------------------------------------------------------------------------- |
| **Google Ads API** | `google-ads` SDK v24+, OAuth2 (dev token + refresh token), MCC login pattern |
| **OpenAI**         | `openai` SDK 1.30+, `gpt-4o-mini` only, JSON-mode responses                  |
| **Zoho Cliq**      | Outbound webhooks (`zapikey` + `company_id` URL params), three channels      |
| **AWS S3**         | (Planned) — `boto3` is in deps for the daily `pg_dump` backup script         |

Notably **no third-party AI middleware** (no LangChain, no Pinecone, no Zapier). All integrations are direct SDK calls. Easier to debug, fewer moving parts.

---

## 7. Tech stack

| Layer            | Choice                                          | Reason                                           |
| ---------------- | ----------------------------------------------- | ------------------------------------------------ |
| Language         | Python 3.11                                     | Required by `google-ads` SDK + ecosystem         |
| Web              | FastAPI 0.110 + Uvicorn                         | Async, automatic OpenAPI, pydantic validation    |
| ORM / DB driver  | SQLAlchemy 2.0 async + asyncpg                  | Standard async stack, no surprises               |
| Cache            | Redis 7 (`redis.asyncio`)                       | Sub-ms reads, atomic counters for quota tracking |
| Scheduler        | APScheduler `BlockingScheduler` + `CronTrigger` | Lighter than Celery for 3 jobs, no broker needed |
| MCP              | `mcp` 1.0 SDK, stdio transport                  | Spec-mandated for Claude Desktop                 |
| Validation       | pydantic 2                                      | Bundled with FastAPI                             |
| HTTP client      | `httpx`                                         | Async, used by MCP client and agents             |
| Migrations       | alembic                                         | Standard SQLAlchemy companion                    |
| Excel export     | `openpyxl`                                      | YTD report `.xlsx` generation                    |
| Containerization | Docker + docker-compose                         | Single EC2, auto-restart on reboot               |
| CI/CD            | GitHub Actions → SSH deploy                     | One workflow file, ~30s deploys on push to main  |

---

## 8. Deployment topology (brief)

Single EC2 `t3.small`, Ubuntu 22.04, ~$17/month all-in. Four containers via [`docker-compose.prod.yml`](../docker-compose.prod.yml): `backend`, `scheduler`, `postgres`, `redis`. All four use `restart: always` so a server reboot brings the stack back automatically. Backend exposes port 8001 directly (demo mode); production would put Caddy in front for HTTPS + a domain.

Full details: [deployment_plan.md](deployment_plan.md).

---

## 9. Architectural decisions worth flagging

A few non-obvious choices that shaped the build:

**1. MCP server as a thin proxy, not a full client.**
Tempting to put Google Ads logic in the MCP server itself — fewer hops, faster responses. We didn't, because every laptop would then need OAuth tokens, the SDK, and DB credentials. Keeping logic server-side means one source of truth for secrets and one place to deploy fixes.

**2. Preview/confirm at the API layer, not in Claude's prompt.**
Claude could theoretically be instructed to always preview first. Instead, the backend rejects un-confirmed writes outright. Belt-and-suspenders — protects against prompt injection or a bad system prompt update.

**3. Two ways to reach Google Ads (FastAPI for users, direct module imports for agents).**
Agents skip HTTP and call `backend/google_ads/*` directly. Saves ~80ms per call and avoids a useless network hop on the same machine. Same code paths either way.

**4. Caching keyed on canonical params, not URL.**
Two requests with different param order hit the same cache entry. Avoids the classic cache-miss-on-equivalent-query bug.

**5. No ORM for read paths.**
Reporting endpoints use raw SQL via SQLAlchemy `text()`. ORM overhead isn't worth it for read-heavy aggregations; the queries are already shaped exactly how Postgres wants them.

---

## 10. Known gaps / next-sprint work

Tracked in [deployment_plan.md §12](deployment_plan.md#L520):

- **Change-log persistence** — table exists and writes log into it, but the `/changes` endpoint currently returns a stub. Need to wire up the read side.
- **Rollback for `create_campaign`** — if keyword creation fails midway, the campaign is left orphaned. Need cleanup-on-failure logic.
- **Per-user attribution on writes** — currently every change is logged, but without "who triggered it." Adding an `X-User-Id` header from the MCP server is the cleanest fix.
- **Secrets to AWS Parameter Store** — `.env.prod` on disk works for one operator; doesn't scale to multiple deployers.
- **Read-only dashboard** — small web UI for the Cliq audience to see recent agent runs, change log, and quota usage. Backend already has the data.

---

_Maintained by MethodPro engineering. For questions, check the codebase first — code is short, comments are minimal but the structure is intentional._
