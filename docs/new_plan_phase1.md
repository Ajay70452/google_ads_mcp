# Phase 1 — Automated Google Ads Agents

## Overview

Three automated agents that eliminate daily/weekly manual checks for the MethodPro team. Each agent runs on a schedule, queries the Google Ads API, and posts alerts to Zoho Cliq only when action is needed.

---

## What Already Exists

The following backend infrastructure is **fully built and working**:

| Component | File | Status |
|---|---|---|
| FastAPI backend + all 11 MCP tools | `backend/main.py` | Done |
| Google Ads API client + auth | `backend/google_ads/auth.py` | Done |
| Budget pacing query (all accounts) | `backend/google_ads/reporting.py` → `get_budget_pacing()` | Done |
| Search terms query (per account) | `backend/google_ads/reporting.py` → `get_search_term_report()` | Done |
| Account summary metrics (CTR, Conv Rate, Cost) | `backend/google_ads/reporting.py` → `get_account_summary()` | Done |
| All-accounts MCC listing | `backend/google_ads/reporting.py` → `list_child_accounts()` | Done |
| Claude API integration | `backend/google_ads/ad_copy.py` | Done |
| Redis caching | `backend/main.py` → `_cached()` | Done |
| PostgreSQL + Alembic schema | `backend/database.py`, `alembic/` | Done |

---

## What Needs to Be Built

### Shared Infrastructure (needed by all 3 agents)

| # | Component | Description | File to create |
|---|---|---|---|
| S1 | **Zoho Cliq notifier** | `send_cliq_alert(message, channel)` — HTTP POST to Cliq incoming webhook | `backend/notifications/cliq.py` |
| S2 | **Agent runner / scheduler** | Python script that runs agents on a cron schedule using APScheduler | `agents/scheduler.py` |
| S3 | **Agent base class** | Shared error handling, retry logic, and logging wrapper | `agents/base.py` |

---

## Agent 1 — Budget Pacing Monitor

**Schedule:** Daily, 8:00 AM  
**Channel:** Zoho Cliq `#pacing-alerts`  
**Trigger:** Any campaign 15%+ off expected pace (same threshold as existing `UNDERSPENDING`/`OVERSPENDING` status)

### What's already done
- `get_budget_pacing()` in `reporting.py` already calculates `pacing_pct` and `status` for every campaign across all accounts
- The `/budget-pacing/all` FastAPI endpoint works end-to-end
- Alert threshold logic (85–115% = ON_TRACK, outside = flag) already computed

### What needs to be built

| # | Task | Detail |
|---|---|---|
| A1-1 | **Agent script** | Loop over all accounts, filter campaigns where `status != "ON_TRACK"`, format Cliq message | `agents/budget_pacing_monitor.py` |
| A1-2 | **Alert formatter** | Format the alert string: `⚠️ LJDW — Budget Pacing Alert \| Day 8 of 30 \| Expected: $1,200 \| Actual: $640 \| 47% under pace` | inside `budget_pacing_monitor.py` |
| A1-3 | **Cliq integration** | Call `send_cliq_alert()` from S1 | depends on S1 |
| A1-4 | **Scheduler entry** | Register as daily 8 AM job in `scheduler.py` | depends on S2 |

### Data flow
```
scheduler.py (8 AM)
  → budget_pacing_monitor.py
    → GET /budget-pacing/all  (hits FastAPI backend)
      → reporting.py → get_budget_pacing() → Google Ads API
    → filter: pacing_pct < 85 or pacing_pct > 115
    → format alert per flagged campaign
    → send_cliq_alert()  →  Zoho Cliq #pacing-alerts
```

**Estimated build time:** 2–3 hours (mostly S1 + S2 shared work)

---

## Agent 2 — Performance Anomaly Detector

**Schedule:** Weekly, Monday 8:00 AM  
**Channel:** Zoho Cliq `#performance-alerts`  
**Trigger:** Any metric (CPC, CTR, conversion rate) more than 20% outside the trailing 4-week average

### What's already done
- `get_account_summary()` returns clicks, cost, conversions, CTR, conversion rate for any date range
- Claude API wired up (can be used to generate the summary message)

### What needs to be built

| # | Task | Detail |
|---|---|---|
| A2-1 | **Custom date range support in reporting** | `get_account_summary_custom(client, customer_id, start_date, end_date)` — the existing function uses built-in constants (`LAST_30_DAYS` etc.); need a variant that accepts `BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'` | `backend/google_ads/reporting.py` |
| A2-2 | **4-week history fetcher** | Pull metrics for each of the last 4 individual weeks (Mon–Sun) per account | `agents/anomaly_detector.py` |
| A2-3 | **Anomaly calculation** | Compute: `this_week_value / avg(4_week_values) - 1`. Flag if > 20% deviation. Metrics: CPC (`cost/clicks`), CTR, conversion rate | inside `anomaly_detector.py` |
| A2-4 | **Prioritised alert formatter** | Sort flagged accounts by severity, format per-account block | inside `anomaly_detector.py` |
| A2-5 | **Cliq integration** | Call `send_cliq_alert()` | depends on S1 |
| A2-6 | **Scheduler entry** | Register as weekly Monday 8 AM job | depends on S2 |

### Data flow
```
scheduler.py (Monday 8 AM)
  → anomaly_detector.py
    → for each of last 4 weeks: get_account_summary_custom(start, end)
    → compute weekly CPC, CTR, conv_rate
    → calculate 4-week averages
    → compare this week vs average → flag if |deviation| > 20%
    → format prioritised alert list
    → send_cliq_alert()  →  Zoho Cliq #performance-alerts
```

**Estimated build time:** 4–5 hours (A2-1 custom date range is the main new work)

---

## Agent 3 — Search Terms Flagging Agent

**Schedule:** Weekly, Monday 9:00 AM (after Agent 2)  
**Channel:** Zoho Cliq `#search-terms-review`  
**Output:** One message per client with Claude-identified irrelevant/low-intent terms to add as negatives

### What's already done
- `get_search_term_report()` pulls all search terms per account with impressions, clicks, cost, conversions
- Rule-based flagging already surfaces `suggested_negatives` (spend > $0, conversions = 0)
- Claude API is wired up in `ad_copy.py` — same pattern can be reused

### What needs to be built

| # | Task | Detail |
|---|---|---|
| A3-1 | **All-accounts search terms loop** | Iterate `list_child_accounts()`, call `get_search_term_report()` per account, collect results | `agents/search_terms_agent.py` |
| A3-2 | **Claude classifier** | Send the search terms list to Claude with a prompt: *"You are a dental PPC expert. Identify search terms that are irrelevant or low-intent for a dental clinic..."* — returns a ranked list of terms to add as negatives with reason | `backend/google_ads/search_term_classifier.py` |
| A3-3 | **Output formatter** | Format per-client block: account name, list of flagged terms + reason, count of terms reviewed | inside `search_terms_agent.py` |
| A3-4 | **Cliq integration** | Post one message per client (or one batched message if accounts are many) | depends on S1 |
| A3-5 | **Scheduler entry** | Register as weekly Monday 9 AM job | depends on S2 |

### Data flow
```
scheduler.py (Monday 9 AM)
  → search_terms_agent.py
    → list_child_accounts()  →  all active accounts
    → for each account:
        → get_search_term_report(customer_id, LAST_7_DAYS)
        → search_term_classifier.py
            → Claude API: "which of these are irrelevant/low-intent?"
            → returns: [{term, reason, priority}]
        → format per-account output
    → send_cliq_alert() per account  →  Zoho Cliq #search-terms-review
```

**Estimated build time:** 3–4 hours (A3-2 Claude classifier is the main new work)

---

## Build Order

```
Week 1
├── S1  Zoho Cliq notifier          (shared, do first)
├── S2  Scheduler + base agent      (shared, do second)
├── A1  Budget Pacing Monitor       (data ready, quickest win)
└── A3  Search Terms Agent          (Claude pattern reusable from ad_copy.py)

Week 2
└── A2  Performance Anomaly         (needs custom date range work first)
```

---

## New Files to Create

```
agents/
├── __init__.py
├── base.py                          # Shared: error handling, logging
├── scheduler.py                     # APScheduler — registers all 3 agents
├── budget_pacing_monitor.py         # Agent 1
├── anomaly_detector.py              # Agent 2
└── search_terms_agent.py            # Agent 3

backend/
├── notifications/
│   ├── __init__.py
│   └── cliq.py                      # Zoho Cliq webhook sender
└── google_ads/
    └── search_term_classifier.py    # Claude-powered classifier for Agent 3
```

Custom date range support added to existing:
```
backend/google_ads/reporting.py      # Add get_account_summary_custom()
```

---

## Environment Variables to Add to `.env`

```
CLIQ_WEBHOOK_URL_PACING=https://cliq.zoho.com/api/v2/...
CLIQ_WEBHOOK_URL_PERFORMANCE=https://cliq.zoho.com/api/v2/...
CLIQ_WEBHOOK_URL_SEARCH_TERMS=https://cliq.zoho.com/api/v2/...
```
