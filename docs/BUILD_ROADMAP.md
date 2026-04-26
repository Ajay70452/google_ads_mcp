# Google Ads AI Automation — Technical Build Roadmap

> MCP Server for Claude Desktop | 18-20 Dental Clinic Accounts | Google Ads Manager (MCC)

---

## Phase 0: Pre-Development (Day 1-2)

**Goal:** Get the longest-lead-time items moving before writing a single line of code.

### 0.1 — Apply for Google Ads Developer Token

- Log into the MCC (Manager) account at `ads.google.com`
- Navigate to **Tools & Settings > API Center**
- Submit the developer token application
- **This takes 5-7 business days for approval** — must be done first
- While pending, you get a **test account token** (works against test accounts only)

### 0.2 — Create Google Cloud Project & OAuth Credentials

- Go to [Google Cloud Console](https://console.cloud.google.com)
- Create a new project (e.g., `ga-auto-mcp`)
- Enable the **Google Ads API** under APIs & Services
- Configure **OAuth Consent Screen** (Internal type if using Google Workspace, otherwise External)
- Create **OAuth 2.0 Client ID** → choose **Desktop App** type
- Download `client_secret.json` — store securely, never commit to repo

### 0.3 — Generate OAuth Refresh Token

- Use the `google-ads` Python library's built-in auth helper:
  ```bash
  pip install google-ads
  python -m google_ads.auth.generate_refresh_token \
    --client_id=YOUR_CLIENT_ID \
    --client_secret=YOUR_CLIENT_SECRET
  ```
- Complete the browser-based OAuth flow (login with MCC admin account)
- Save the returned `refresh_token` — this is a long-lived credential

### 0.4 — Collect All Credential Values

| Credential          | Source                                   | Storage Target                       |
| ------------------- | ---------------------------------------- | ------------------------------------ |
| Developer Token     | Google Ads API Center                    | AWS Secrets Manager / `.env` (local) |
| OAuth Client ID     | Google Cloud Console                     | AWS Secrets Manager / `.env` (local) |
| OAuth Client Secret | Google Cloud Console                     | AWS Secrets Manager / `.env` (local) |
| Refresh Token       | OAuth flow output                        | AWS Secrets Manager / `.env` (local) |
| MCC Customer ID     | Google Ads account (10-digit, no dashes) | Environment variable                 |

**Deliverables:**

- [ ] Developer token application submitted
- [ ] Google Cloud project created with Ads API enabled
- [ ] OAuth Desktop App credentials downloaded
- [ ] Refresh token generated and stored
- [ ] MCC Customer ID noted

---

## Phase 1: Project Scaffolding & Local Infrastructure (Day 3-5)

**Goal:** Repo, dependencies, Docker services, database, and a running FastAPI skeleton.

### 1.1 — Initialize Repository

```
google-ads-mcp/
├── mcp_server/
│   ├── __init__.py
│   ├── server.py
│   ├── client.py
│   └── tools/
│       ├── __init__.py
│       ├── reporting.py
│       ├── search_terms.py
│       ├── keywords.py
│       ├── campaigns.py
│       ├── ad_copy.py
│       └── budgets.py
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models/
│   │   └── schemas.py
│   └── google_ads/
│       ├── __init__.py
│       ├── auth.py
│       ├── campaigns.py
│       ├── keywords.py
│       ├── reporting.py
│       └── ad_groups.py
├── tests/
│   ├── test_tools.py
│   └── test_backend.py
├── .env.example
├── .gitignore
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
└── claude_desktop_config.json
```

### 1.2 — pyproject.toml & Dependencies

```toml
[project]
name = "google-ads-mcp"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.0.0",
    "fastapi>=0.110.0",
    "uvicorn>=0.29",
    "google-ads>=24.0.0",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "redis>=5.0",
    "boto3>=1.34",
    "pydantic>=2.0",
    "httpx>=0.27",
    "python-dotenv>=1.0",
    "alembic>=1.13",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "ruff"]
```

### 1.3 — Docker Compose (Local Dev)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ga_auto
      POSTGRES_USER: ga_user
      POSTGRES_PASSWORD: localdev
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

### 1.4 — Database Schema (PostgreSQL via SQLAlchemy + Alembic)

**Table: `client_accounts`**
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| customer_id | VARCHAR(10) UNIQUE | Google Ads customer ID |
| name | VARCHAR(255) | Clinic name |
| city | VARCHAR(100) | |
| monthly_budget | NUMERIC(10,2) | |
| is_active | BOOLEAN DEFAULT TRUE | |
| created_at | TIMESTAMPTZ | |

**Table: `campaign_snapshots`**
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| customer_id | VARCHAR(10) FK | |
| campaign_id | VARCHAR(20) | |
| campaign_name | VARCHAR(255) | |
| snapshot_date | DATE | |
| impressions | INTEGER | |
| clicks | INTEGER | |
| cost_micros | BIGINT | Cost in micros (÷1,000,000 for currency) |
| conversions | NUMERIC(10,2) | |
| ctr | NUMERIC(5,4) | |
| cpa | NUMERIC(10,2) | |

**Index:** `(customer_id, snapshot_date)`

**Table: `change_log`**
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| customer_id | VARCHAR(10) | |
| action | VARCHAR(50) | e.g., `update_budget`, `add_negative_kw` |
| entity_type | VARCHAR(50) | campaign, keyword, ad_group |
| entity_id | VARCHAR(50) | |
| before_payload | JSONB | State before change |
| after_payload | JSONB | State after change |
| confirmed_by | VARCHAR(100) | Who approved |
| executed_at | TIMESTAMPTZ | |

**Index:** `(customer_id, executed_at DESC)`

**Table: `generated_ad_copy`**
| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| customer_id | VARCHAR(10) | |
| campaign_id | VARCHAR(20) | |
| service | VARCHAR(100) | e.g., "teeth whitening" |
| location | VARCHAR(100) | e.g., "Ahmedabad" |
| headlines | JSONB | Array of up to 15 headlines |
| descriptions | JSONB | Array of up to 4 descriptions |
| created_at | TIMESTAMPTZ | |

### 1.5 — FastAPI Skeleton

- Create `backend/main.py` with health check (`GET /health`)
- Set up SQLAlchemy async engine + session middleware
- Set up Redis connection pool
- Confirm DB connection on startup
- Run with: `uvicorn backend.main:app --reload --port 8000`

### 1.6 — Google Ads Auth Module

- `backend/google_ads/auth.py`:
  - Load credentials from `.env` locally (Secrets Manager in prod)
  - Initialize `GoogleAdsClient` from the official library
  - Expose a `get_google_ads_client()` dependency
  - Validate connection by listing accessible customer IDs under MCC

**Deliverables:**

- [ ] Repo initialized with full folder structure
- [ ] `docker-compose up` runs Postgres + Redis
- [ ] Alembic migrations create all 4 tables
- [ ] `GET /health` returns 200
- [ ] Google Ads client authenticates and lists MCC child accounts

---

## Phase 2: MCP Server Skeleton + First Read Tool (Day 6-9)

**Goal:** Wire up the MCP server, connect it to FastAPI, and ship the first working tool end-to-end through Claude Desktop.

### 2.1 — MCP Server Entry Point

- `mcp_server/server.py`:
  - Use `mcp` library to create a stdio-based MCP server
  - Register tool definitions (name, description, input schema, handler)
  - Each handler calls the FastAPI backend via `httpx`
- `mcp_server/client.py`:
  - Async HTTP client wrapper for `http://localhost:8000`
  - Handles retries, timeouts, error formatting

### 2.2 — Tool: `get_account_summary`

**Why first:** Broadest scope, validates the entire pipeline (MCP → FastAPI → Google Ads API → response formatting).

**Input Schema:**

```json
{
  "customer_id": "string (optional — omit for all accounts)",
  "date_range": "string (default: LAST_30_DAYS)"
}
```

**Backend GAQL Query:**

```sql
SELECT
  customer.descriptive_name,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.conversions_from_interactions_rate
FROM customer
WHERE segments.date DURING LAST_30_DAYS
```

**Response:** Formatted table with spend, conversions, ROAS per account.

### 2.3 — Tool: `get_campaign_report`

**Input Schema:**

```json
{
  "customer_id": "string (required)",
  "date_range": "string (default: LAST_30_DAYS)",
  "campaign_status": "string (default: ENABLED)"
}
```

**Backend GAQL Query:**

```sql
SELECT
  campaign.name,
  campaign.status,
  campaign_budget.amount_micros,
  metrics.impressions,
  metrics.clicks,
  metrics.ctr,
  metrics.cost_micros,
  metrics.conversions,
  metrics.cost_per_conversion
FROM campaign
WHERE campaign.status = 'ENABLED'
  AND segments.date DURING LAST_30_DAYS
ORDER BY metrics.cost_micros DESC
```

### 2.4 — Redis Caching Layer

- Cache GAQL query results in Redis with **3-hour TTL**
- Cache key format: `gaql:{customer_id}:{query_hash}`
- Prevents hitting the 15,000 requests/day rate limit
- Add `?refresh=true` query param to bypass cache

### 2.5 — Claude Desktop Integration

- Create `claude_desktop_config.json`:
  ```json
  {
    "mcpServers": {
      "google-ads": {
        "command": "python",
        "args": ["-m", "mcp_server.server"],
        "cwd": "/path/to/google-ads-mcp",
        "env": {
          "BACKEND_URL": "http://localhost:8000",
          "PYTHONPATH": "/path/to/google-ads-mcp"
        }
      }
    }
  }
  ```
- Copy to Claude Desktop config directory
- Restart Claude Desktop — verify hammer icon appears
- Test: Ask Claude "Show me account summary for last 30 days"

**Deliverables:**

- [ ] MCP server starts via stdio and registers tools
- [ ] `get_account_summary` works end-to-end through Claude Desktop
- [ ] `get_campaign_report` works end-to-end
- [ ] Redis caching active with 3-hour TTL
- [ ] Claude Desktop shows the hammer icon and lists available tools

---

## Phase 3: Remaining Read-Only Tools + YTD Report (Day 10-14)

**Goal:** Complete all 5 read-only tools, with the monthly YTD report being the centrepiece. After this phase, the marketing team can do all reporting through Claude.

---

### 3.1 — Tool: `generate_ytd_report` ⭐ (Primary Reporting Tool)

This is the main report the marketing team will use daily. It pulls all accounts, aggregates by month, and renders a formatted table in Claude's chat.

**Input:**

```json
{
  "year": "integer (default: current year — 2026)"
}
```

No `customer_id` input — always runs across **all active accounts** in the `client_accounts` table.

**What it produces:**

For each active account × each elapsed month in the year, one row:

| Account | Month | Clicks | Impressions | CTR | Conversions | Cost | Conv. Rate | CPL |
|---|---|---|---|---|---|---|---|---|
| Apex Dental Group | January 2026 | 275 | 16,970 | 1.62% | 24 | $706.00 | 6.15% | $29.43 |
| Apex Dental Group | February 2026 | 12,141 | 148,737 | 8.16% | 28 | $771.22 | 0.18% | $27.54 |
| **Apex Dental Group** | **March 2026 *** | **1,170** | **36,167** | **3.23%** | **22** | **$537.73** | **1.57%** | **$24.44** |

Current month rows are marked with `*` (in-progress data).

**How it works — Backend Logic:**

```
1. Fetch all active customer_ids from client_accounts table
2. For each month from January to current month:
   - Build GAQL query with segments.month filter
   - Execute against each customer_id (batched, not sequential)
   - Aggregate: sum all campaigns under the customer_id
3. Compute derived metrics:
   - CTR       = clicks / impressions
   - Conv. Rate = conversions / clicks
   - CPL        = cost / conversions  (null-safe: show "-" if conversions = 0)
4. Format as markdown table grouped by account, sorted by account name
5. Append current month label with " *" marker
```

**GAQL Query (run per customer_id per month):**

```sql
SELECT
  segments.month,
  metrics.clicks,
  metrics.impressions,
  metrics.cost_micros,
  metrics.conversions,
  metrics.interactions
FROM campaign
WHERE campaign.status = 'ENABLED'
  AND segments.month = '{YYYY-MM-01}'
ORDER BY segments.month
```

> Note: `segments.month` returns the first day of the month (e.g., `2026-01-01`). Run this query once per month per account. The backend sums `clicks`, `impressions`, `cost_micros`, `conversions` across all campaign rows returned for that month.

**Computed Fields:**

| Field | Formula | Notes |
|---|---|---|
| CTR | `clicks / impressions × 100` | Format as `X.XX%` |
| Conversions | raw from API | Sum across all campaigns |
| Cost | `cost_micros / 1,000,000` | Format as `$X.XX` |
| Conv. Rate | `conversions / interactions × 100` | Use `interactions` not `clicks` (matches Google Ads UI) |
| CPL | `cost / conversions` | Show `"-"` if conversions = 0 |

**Caching Strategy:**

- Past months (fully elapsed): cache in Redis with **24-hour TTL** — data won't change
- Current month: cache with **1-hour TTL** — data is still accumulating
- Cache key: `ytd:{customer_id}:{YYYY-MM}`
- `?refresh=true` bypasses cache for all months

**Claude Chat Output Format:**

```
📊 YTD Performance Report — 2026 (Jan–Mar)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APEX DENTAL GROUP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Month          Clicks   Impr.    CTR    Conv.  Cost      Conv%   CPL
January 2026    275     16,970   1.62%   24    $706.00   6.15%  $29.43
February 2026  12,141  148,737   8.16%   28    $771.22   0.18%  $27.54
March 2026 *    1,170   36,167   3.23%   22    $537.73   1.57%  $24.44

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIBONACCI SMILE DENTAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Month          Clicks   Impr.    CTR    Conv.  Cost      Conv%   CPL
January 2026    234      4,624   5.06%   46    $593.00  18.55%  $12.89
...

* = current month (data in progress)
```

**Performance consideration:** With 18-20 accounts × up to 12 months = up to 240 GAQL queries. Mitigate with:
- Parallel execution (asyncio gather, batches of 10)
- Redis cache (past months almost always cached after first call)
- Typical runtime target: < 8 seconds on warm cache, < 30 seconds cold

---

### 3.2 — Tool: `get_search_term_report`

**Input:**

```json
{
  "customer_id": "string (required)",
  "campaign_id": "string (optional — filter to one campaign)",
  "date_range": "string (default: LAST_30_DAYS)",
  "min_impressions": "integer (default: 10)"
}
```

**GAQL Query:**

```sql
SELECT
  search_term_view.search_term,
  campaign.name,
  ad_group.name,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions
FROM search_term_view
WHERE segments.date DURING LAST_30_DAYS
  AND metrics.impressions > 10
ORDER BY metrics.cost_micros DESC
```

**Special Logic:**

- Flag search terms with **high cost + zero conversions** as negative keyword candidates
- Return a `suggested_negatives` array in the response
- This directly feeds into the `add_negative_keywords` write tool later

---

### 3.3 — Tool: `get_keyword_performance`

**Input:**

```json
{
  "customer_id": "string (required)",
  "campaign_id": "string (optional)",
  "min_quality_score": "integer (optional — filter below this)",
  "date_range": "string (default: LAST_30_DAYS)"
}
```

**GAQL Query:**

```sql
SELECT
  ad_group_criterion.keyword.text,
  ad_group_criterion.keyword.match_type,
  ad_group_criterion.quality_info.quality_score,
  ad_group_criterion.quality_info.creative_quality_score,
  ad_group_criterion.quality_info.post_click_quality_score,
  ad_group_criterion.quality_info.search_predicted_ctr,
  metrics.impressions,
  metrics.clicks,
  metrics.cost_micros,
  metrics.conversions,
  metrics.search_impression_share,
  metrics.search_top_impression_percentage,
  metrics.first_page_cpc
FROM keyword_view
WHERE segments.date DURING LAST_30_DAYS
ORDER BY metrics.cost_micros DESC
```

**Special Logic:**

- Highlight keywords with Quality Score < 5
- Flag keywords with high spend but low conversion rate
- Include impression share data to identify growth opportunities

---

### 3.4 — Tool: `get_budget_pacing`

**Input:**

```json
{
  "customer_id": "string (optional — omit for all accounts)",
  "date_range": "string (default: THIS_MONTH)"
}
```

**Logic:**

1. Query current month-to-date spend per campaign
2. Query daily budget setting per campaign
3. Calculate: `expected_spend = daily_budget × days_elapsed`
4. Calculate: `projected_spend = (spend_so_far / days_elapsed) × days_in_month`
5. Flag campaigns as:
   - **UNDERSPENDING** if projected < 85% of monthly budget
   - **ON_TRACK** if projected is 85-115%
   - **OVERSPENDING** if projected > 115% of monthly budget

---

### 3.5 — Snapshot Storage

- After `generate_ytd_report` runs, persist each month's aggregated row into `campaign_snapshots` table
- Allows historical queries without re-hitting the Google Ads API
- Run as background task — does not block the tool response

---

### 3.6 — End-to-End Testing

- Run `generate_ytd_report` and verify numbers match Google Ads UI for at least 3 accounts
- Verify past-month rows are served from Redis cache on second call
- Verify current month marker `*` appears correctly
- Test other tools against at least 3 different client accounts
- Test edge cases: account with zero spend in a month, account with zero conversions (CPL = "-")

**Deliverables:**

- [ ] `generate_ytd_report` returns all accounts × all 2026 months in Claude chat
- [ ] Past months cached 24h, current month cached 1h
- [ ] CPL shows `"-"` when conversions = 0
- [ ] Current month marked with `*`
- [ ] `get_search_term_report` with negative keyword suggestions
- [ ] `get_keyword_performance` with Quality Score analysis
- [ ] `get_budget_pacing` with over/under-spend flags
- [ ] Numbers verified against Google Ads UI for 3+ accounts
- [ ] Snapshot storage running as background task

---

## Phase 4: Write Tools — Negative Keywords & Budget Updates (Day 15-18)

**Goal:** Enable the first write operations with full safety controls (dry-run/confirm pattern, change logging).

### 4.1 — Confirmation Pattern (Shared Infrastructure)

All write tools follow the same two-step pattern:

```
Step 1: Claude calls tool with confirm=false
  → Backend returns a PREVIEW of what will change
  → Claude shows preview to user

Step 2: User says "yes, do it"
  → Claude calls tool again with confirm=true
  → Backend executes the change
  → Change is logged to change_log table
  → Confirmation returned
```

Implement this as a shared decorator/utility in the backend.

### 4.2 — Tool: `add_negative_keywords`

**Input:**

```json
{
  "customer_id": "string (required)",
  "campaign_id": "string (optional — omit for account-level)",
  "keywords": ["string array of negative keywords"],
  "match_type": "EXACT | PHRASE | BROAD (default: PHRASE)",
  "confirm": "boolean (default: false)"
}
```

**Workflow:**

1. `confirm=false` → Return preview: "Will add 12 negative keywords (PHRASE match) to campaign 'Implants - Ahmedabad'"
2. `confirm=true` → Execute via Google Ads API `CampaignCriterionService` or `CustomerNegativeCriterionService`
3. Log to `change_log` with `action=add_negative_keywords`

**Ties into:** Search term report's `suggested_negatives` output — Claude can chain these tools naturally.

### 4.3 — Tool: `update_campaign_budget`

**Input:**

```json
{
  "customer_id": "string (required)",
  "campaign_id": "string (required)",
  "new_daily_budget": "number (in account currency)",
  "confirm": "boolean (default: false)"
}
```

**Workflow:**

1. `confirm=false` → Fetch current budget, return preview: "Campaign 'Implants - Ahmedabad': ₹1,500/day → ₹2,000/day (+33%)"
2. `confirm=true` → Execute via `CampaignBudgetService.mutate()`
3. Log to `change_log` with `before_payload={budget: 1500}`, `after_payload={budget: 2000}`

**Safety:** Reject changes > 200% increase in a single call (configurable threshold).

### 4.4 — Change Log API

- `GET /changes?customer_id=X&limit=20` — View recent changes
- Enables Claude to answer: "What changes did we make to Robeck Dental's account this week?"

**Deliverables:**

- [ ] Dry-run/confirm pattern implemented as reusable backend utility
- [ ] `add_negative_keywords` with preview + execute + logging
- [ ] `update_campaign_budget` with preview + execute + logging + safety threshold
- [ ] Change log queryable via API
- [ ] Both tools tested end-to-end through Claude Desktop

---

## Phase 5: Write Tools — Campaign Creation & Ad Copy (Day 19-22)

**Goal:** Complete the remaining write tools. After this phase, all 9 tools are functional.

### 5.1 — Tool: `create_campaign`

**Input:**

```json
{
  "customer_id": "string (required)",
  "campaign_name": "string (required)",
  "daily_budget": "number (required)",
  "target_locations": ["string array (optional)"],
  "ad_group_name": "string (required)",
  "keywords": ["string array (required)"],
  "match_type": "EXACT | PHRASE | BROAD (default: PHRASE)",
  "confirm": "boolean (default: false)"
}
```

**Workflow:**

1. `confirm=false` → Return full preview of campaign structure
2. `confirm=true` → Execute in sequence:
   - Create `CampaignBudget`
   - Create `Campaign` (type: SEARCH, network: SEARCH only)
   - Create `AdGroup`
   - Create `AdGroupCriterion` for each keyword
3. Log all created entity IDs to `change_log`

**Note:** Does NOT create ads (responsive search ads) — that's a manual step or future enhancement. The tool sets up the campaign structure + keywords.

### 5.2 — Tool: `generate_ad_variations`

**Input:**

```json
{
  "customer_id": "string (required)",
  "campaign_id": "string (optional)",
  "service": "string (required, e.g., 'teeth whitening')",
  "location": "string (required, e.g., 'Ahmedabad')",
  "unique_selling_points": ["string array (optional)"]
}
```

**Workflow:**

1. Use Claude API (Anthropic SDK) internally to generate:
   - **15 headlines** (max 30 chars each — Google Ads RSA limit)
   - **4 descriptions** (max 90 chars each)
2. Validate all outputs against character limits
3. Store in `generated_ad_copy` table
4. Return formatted for easy copy-paste into Google Ads UI

**Prompt Engineering:** The backend sends a structured prompt to Claude API with:

- Service type and location
- Character limits as hard constraints
- Dental industry context
- USPs if provided
- Request for variety (emotional, factual, urgency, trust-based)

### 5.3 — Full Workflow Integration Test

Test the complete marketing workflow through Claude Desktop:

1. "Show me the account summary for all clients" → `get_account_summary`
2. "Which campaigns are overspending?" → `get_budget_pacing`
3. "Pull the search term report for [client]" → `get_search_term_report`
4. "Add those irrelevant terms as negatives" → `add_negative_keywords` (preview → confirm)
5. "Create a new campaign for teeth whitening in Ahmedabad" → `create_campaign`
6. "Generate ad copy for that campaign" → `generate_ad_variations`

**Deliverables:**

- [ ] `create_campaign` with full structure creation + logging
- [ ] `generate_ad_variations` with Claude API + character validation
- [ ] All 9 tools functional end-to-end
- [ ] Full marketing workflow tested through Claude Desktop
- [ ] Ad copy stored in DB for future reference

---

## Phase 6: Hardening, Error Handling & Client Account Registry (Day 23-25)

**Goal:** Make the system production-ready for daily use across all 18-20 accounts.

### 6.1 — Client Account Registry

- Populate `client_accounts` table with all 18-20 dental clinic accounts
- Enable Claude to resolve clinic names to customer IDs:
  - "Show me Robeck Dental's campaigns" → looks up customer_id from registry
- Add `GET /accounts` endpoint for listing all active clients
- Add an MCP tool or extend existing tools to accept clinic names (not just IDs)

### 6.2 — Error Handling

- **Google Ads API errors:** Parse error codes, return human-readable messages
  - `AUTHORIZATION_ERROR` → "Check credentials / account access"
  - `QUOTA_ERROR` → "Rate limit hit, try again in X minutes"
  - `INVALID_CUSTOMER_ID` → "Customer ID not found under MCC"
- **Network errors:** Retry with exponential backoff (max 3 retries)
- **Empty results:** Return helpful messages, not empty arrays
- **Validation:** Pydantic models on all inputs at both MCP and FastAPI layers

### 6.3 — Rate Limit Management

- Track API calls per day in Redis (`api_calls:{date}` counter)
- Warn at 80% of 15,000 daily limit
- Block non-essential calls at 95%
- Dashboard endpoint: `GET /rate-limit-status`

### 6.4 — Logging & Observability

- Structured JSON logging (Python `logging` + `structlog`)
- Log every: tool invocation, GAQL query, API call, cache hit/miss, error
- Correlation ID per tool invocation for tracing

**Deliverables:**

- [ ] All 18-20 client accounts registered in DB
- [ ] Name-to-ID resolution working in Claude conversations
- [ ] Comprehensive error handling with user-friendly messages
- [ ] Rate limit tracking and warnings
- [ ] Structured logging across all components

---

## Phase 7: AWS Deployment (Day 26-30)

**Goal:** Deploy the FastAPI backend to AWS for reliable, always-on access.

### 7.1 — Docker Image

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install .
COPY backend/ backend/
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- Build and push to **ECR** (Elastic Container Registry)

### 7.2 — AWS Infrastructure

| Service               | Config            | Purpose                       |
| --------------------- | ----------------- | ----------------------------- |
| **ECS Fargate**       | 0.5 vCPU, 1GB RAM | FastAPI backend               |
| **RDS PostgreSQL**    | db.t3.micro, 20GB | Database                      |
| **ElastiCache Redis** | cache.t3.micro    | Query cache                   |
| **Secrets Manager**   | 4 secrets         | Google Ads credentials        |
| **S3 Bucket**         | Standard          | Report exports, keyword files |
| **ALB**               | HTTPS             | Load balancer for ECS         |
| **VPC**               | Private subnets   | Network isolation             |

### 7.3 — Secrets Manager Setup

Store these secrets (NOT in environment variables):

```
google_ads/developer_token
google_ads/client_id
google_ads/client_secret
google_ads/refresh_token
```

- Update `backend/google_ads/auth.py` to fetch from Secrets Manager in prod
- Fall back to `.env` in local dev

### 7.4 — ECS Task Definition

- Set environment variables: `DATABASE_URL`, `REDIS_URL`, `MCC_CUSTOMER_ID`, `AWS_REGION`
- IAM role with permissions: Secrets Manager read, S3 read/write, RDS access
- Health check: `GET /health` every 30s
- Auto-scaling: min 1, max 3 tasks (scale on CPU > 70%)

### 7.5 — Update MCP Server Config for Production

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "BACKEND_URL": "https://your-alb-domain.com"
      }
    }
  }
}
```

- MCP server still runs locally (stdio)
- But now calls the deployed FastAPI backend instead of localhost

### 7.6 — Load Testing

- Test all 9 tools against all 18-20 accounts
- Verify Redis cache reduces API calls by >60%
- Verify response times: read tools < 3s, write tools < 5s
- Monitor RDS connection pool under concurrent queries

**Deliverables:**

- [ ] Docker image in ECR
- [ ] ECS Fargate service running
- [ ] RDS PostgreSQL provisioned with schema
- [ ] ElastiCache Redis running
- [ ] Secrets Manager configured
- [ ] ALB with HTTPS
- [ ] MCP server pointing to production backend
- [ ] Load tested across all client accounts
- [ ] All 9 tools working in production

---

## Phase Summary

| Phase       | Days  | What You Get                                                 |
| ----------- | ----- | ------------------------------------------------------------ |
| **Phase 0** | 1-2   | Credentials ready, developer token applied                   |
| **Phase 1** | 3-5   | Repo, Docker, DB, FastAPI running, Google Ads auth working   |
| **Phase 2** | 6-9   | MCP server + Claude Desktop connected, 2 read tools live     |
| **Phase 3** | 10-14 | All 5 read tools live — full reporting through Claude        |
| **Phase 4** | 15-18 | Negative keywords + budget updates with safety controls      |
| **Phase 5** | 19-22 | All 9 tools live — campaign creation + ad copy generation    |
| **Phase 6** | 23-25 | Production-hardened, all accounts registered, error handling |
| **Phase 7** | 26-30 | Deployed on AWS, load tested, production-ready               |

---

## Key Technical Decisions

1. **stdio transport** — MCP server runs as a local subprocess of Claude Desktop. Zero network exposure, automatic lifecycle.
2. **Thin MCP / Fat Backend** — MCP tools only handle schema + orchestration. All business logic lives in FastAPI (reusable for future Next.js dashboard).
3. **Dry-run by default** — Every write tool requires explicit user confirmation. No accidental budget changes.
4. **3-hour Redis TTL** — Balances freshness vs. API rate limits (15,000/day).
5. **Change log everything** — Every write operation is auditable with before/after snapshots.
6. **Secrets Manager over env vars** — Credentials never live in code, config files, or plain environment variables in production.

---

## Future Scope (Post v1)

- **Multi-user HTTP transport** — Replace stdio with HTTP-based MCP for team-wide access
- **Next.js dashboard** — Client-facing reporting UI consuming the same FastAPI backend
- **Automated alerts** — Slack notifications for budget pacing anomalies
- **Scheduled reports** — Daily/weekly summaries pushed to email or Slack
- **Conversion tracking audit** — Verify conversion tags are firing correctly
- **Bid strategy optimization** — Suggest and apply bid strategy changes
