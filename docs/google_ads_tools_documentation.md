# Google Ads MCP — Tools Documentation

All tools are defined in `mcp_server/server.py` and dispatched to the FastAPI backend at `backend/main.py`.  
Transport: **stdio**. All tools accept a `refresh` boolean to bypass the Redis cache.

---

## Table of Contents

1. [list_accounts](#1-list_accounts)
2. [get_account_summary](#2-get_account_summary)
3. [get_campaign_report](#3-get_campaign_report)
4. [generate_ytd_report](#4-generate_ytd_report)
5. [get_search_term_report](#5-get_search_term_report)
6. [get_keyword_performance](#6-get_keyword_performance)
7. [get_budget_pacing](#7-get_budget_pacing)
8. [add_negative_keywords](#8-add_negative_keywords)
9. [update_campaign_budget](#9-update_campaign_budget)
10. [create_campaign](#10-create_campaign)
11. [generate_ad_variations](#11-generate_ad_variations)

### Automated Agents

12. [Budget Pacing Monitor](#12-budget-pacing-monitor) — Daily alert when any account is 15%+ off pace
13. [Performance Anomaly Detector](#13-performance-anomaly-detector) — Weekly flag when CPC, CTR, or conversion rate deviates 20%+ from 4-week average
14. [Search Terms Flagging Agent](#14-search-terms-flagging-agent) — Weekly Claude-powered review of search terms across all accounts with suggested negatives

---

## 1. `list_accounts`

List all client accounts registered in the database.

**Backend route:** `GET /accounts`

**Parameters:** None

**Example call:**
```
"Show me all client accounts"
```

**Example output:**
```
Client Accounts

- Apex Dental Group       |  `8785895348`
- Fibonacci Smile Dental  |  `3241109872`
- Jaeger Orthodontics     |  `5510238841`
```

**Notes:**
- Reads from the `client_accounts` Postgres table — no Google Ads API call, always fast.
- Inactive accounts are shown with `[inactive]` suffix.

---

## 2. `get_account_summary`

High-level performance metrics for one account or all accounts.

**Backend route:** `GET /accounts/summary` (single) / `GET /accounts/summary/all` (all)

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | No | — | Clinic name (e.g. `"Apex Dental"`) or 10-digit customer ID. Omit for all accounts. |
| `date_range` | string | No | `LAST_30_DAYS` | Google Ads date range constant: `LAST_30_DAYS`, `LAST_7_DAYS`, `THIS_MONTH`, `LAST_MONTH` |
| `refresh` | boolean | No | `false` | Bypass Redis cache and fetch live data |

**Example calls:**
```
"Show me account summary for Apex Dental last 7 days"
"Get account summary for all clients this month"
```

**Example output:**
```
Apex Dental Group
- Impressions:    16,970
- Clicks:         275
- Cost:           $706.00
- Conversions:    24
- Conv. Rate:     8.73%
```

**Notes:**
- Cache TTL: 3 hours.
- When `customer_id` is a name, it is fuzzy-matched against the `client_accounts` table via `backend/resolver.py`.

---

## 3. `get_campaign_report`

Campaign-level performance breakdown for a specific account.

**Backend route:** `GET /accounts/{customer_id}/campaigns`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | Yes | — | Clinic name or 10-digit customer ID |
| `date_range` | string | No | `LAST_30_DAYS` | Google Ads date range constant |
| `campaign_status` | string | No | `ENABLED` | `ENABLED`, `PAUSED`, or `REMOVED` |
| `refresh` | boolean | No | `false` | Bypass Redis cache |

**Example calls:**
```
"Show me campaign report for Jaeger Orthodontics"
"Get paused campaigns for 5510238841"
```

**Example output:**
```
Campaign Report — 5510238841 (4 campaigns)

Campaign                                  Budget      Spend   Clicks    CTR    Conv        CPA
Implants - Ahmedabad                     $50.00    $706.00      275  12.3%    24.0     $29.43
Whitening - San Diego                    $30.00    $412.50      180   9.1%    12.0     $34.38
```

**Notes:**
- Cache TTL: 3 hours.
- Sorted by spend descending.

---

## 4. `generate_ytd_report`

Full year-to-date performance report across **all** client accounts, broken down by month.

**Backend route:** `GET /reports/ytd`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `year` | integer | No | Current year (2026) | Year to report on |
| `refresh` | boolean | No | `false` | Bypass Redis cache |

**Example calls:**
```
"Generate the YTD report"
"Show me 2025 YTD performance"
```

**Example output:**
```
YTD Performance Report — 2026

==================================================================================================
APEX DENTAL GROUP
--------------------------------------------------------------------------------------------------
Month              Clicks    Impr.      CTR    Conv.        Cost   Conv%        CPL
January 2026          275   16,970    1.62%    24.00     $706.00   6.15%     $29.43
February 2026      12,141  148,737    8.16%    28.00     $771.22   0.18%     $27.54
March 2026 *        1,170   36,167    3.23%    22.00     $537.73   1.57%     $24.44

* = current month (data in progress)
```

**Notes:**
- Cache TTL: 1 hour for current month, 24 hours for completed months.
- Accounts fetched concurrently in batches of 10.
- CPL shows `-` when conversions = 0.
- Current month row is marked with `*`.

---

## 5. `get_search_term_report`

Search terms that triggered ads for an account, with automatic negative keyword suggestions.

**Backend route:** `GET /accounts/{customer_id}/search-terms`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | Yes | — | Clinic name or 10-digit customer ID |
| `date_range` | string | No | `LAST_30_DAYS` | Google Ads date range constant |
| `campaign_id` | string | No | — | Filter to a specific campaign ID |
| `min_impressions` | integer | No | `10` | Minimum impressions to include |
| `refresh` | boolean | No | `false` | Bypass Redis cache |

**Example calls:**
```
"Pull the search terms report for Perry Family Dentistry"
"Show search terms for campaign 9876543 with at least 50 impressions"
```

**Example output:**
```
Search Term Report — 5510238841 (142 terms)

Search Term                              Campaign                   Impr  Clicks    Cost  Conv
dental implants cost                     Implants - Ahmedabad       1245     87   $312.40   8.0
cheap teeth whitening near me            Whitening - San Diego        892     54   $198.20   0.0
...

Suggested Negative Keywords (3 terms with spend but 0 conversions):
  - cheap teeth whitening near me
  - free dental cleaning
  - dental school near me
```

**Notes:**
- Cache TTL: 3 hours.
- Terms with spend > $0 and conversions = 0 are automatically surfaced as `suggested_negatives`.
- Output capped at 50 rows in chat; full data available via backend API.
- Pairs naturally with `add_negative_keywords` — Claude can chain these in one conversation.

---

## 6. `get_keyword_performance`

Keyword-level metrics including Quality Score, impression share, spend, and conversions.

**Backend route:** `GET /accounts/{customer_id}/keywords`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | Yes | — | Clinic name or 10-digit customer ID |
| `date_range` | string | No | `LAST_30_DAYS` | Google Ads date range constant |
| `campaign_id` | string | No | — | Filter to a specific campaign |
| `min_quality_score` | integer | No | — | Show only keywords with QS below this value (e.g. `5`) |
| `refresh` | boolean | No | `false` | Bypass Redis cache |

**Example calls:**
```
"Show keyword performance for Apex Dental"
"Get keywords with Quality Score below 5 for Jaeger Orthodontics"
```

**Example output:**
```
Keyword Performance — 5510238841 (87 keywords)

Keyword                             Match    QS    Impr  Clicks    Cost  Conv  ImpShr  Flags
dental implants ahmedabad           PHRASE    8    2340     142  $412.40  12.0   45.2%
cheap dental implants               BROAD     3     890      34  $198.20   0.0   12.1%  LOW_QS, NO_CONV
teeth whitening cost                EXACT     6    1120      89  $267.10   8.0   38.4%
```

**Flags:**
- `LOW_QS` — Quality Score below 5
- `NO_CONV` — High spend with zero conversions

**Notes:**
- Cache TTL: 3 hours.
- Output capped at 50 rows in chat.

---

## 7. `get_budget_pacing`

Check how each campaign is tracking against its monthly budget. Works for one account or all accounts.

**Backend route:** `GET /accounts/{customer_id}/budget-pacing` (single) / `GET /budget-pacing/all` (all)

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | No | — | Clinic name or 10-digit customer ID. Omit for all accounts. |
| `refresh` | boolean | No | `false` | Bypass Redis cache |

**Example calls:**
```
"Check budget pacing for all clients"
"How is LJDW pacing this month?"
```

**Example output:**
```
Budget Pacing — Apex Dental Group

Campaign                                 Daily Bdgt   MTD Spend   Projected   Pacing%  Status
Implants - Ahmedabad                        $50.00     $412.00     $640.00     64.0%  [LOW] UNDERSPENDING
Whitening - San Diego                       $30.00     $310.00     $481.55    110.1%  [OK] ON_TRACK
Braces - General                            $25.00     $290.00     $450.00    140.0%  [HIGH] OVERSPENDING
```

**Status values:**
- `UNDERSPENDING` — Projected end-of-month spend is below 85% of budget
- `ON_TRACK` — Projected spend is within 85–115% of budget
- `OVERSPENDING` — Projected spend exceeds 115% of budget

**Notes:**
- Cache TTL: 3 hours.
- Projection formula: `(spend_mtd / days_elapsed) × days_in_month`.

---

## 8. `add_negative_keywords`

Add negative keywords to a campaign or at account level. Always previews first — requires explicit confirmation to execute.

**Backend route:** `POST /accounts/{customer_id}/negative-keywords`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | Yes | — | Clinic name or 10-digit customer ID |
| `keywords` | array of strings | Yes | — | Negative keyword strings to add |
| `match_type` | string | No | `PHRASE` | `EXACT`, `PHRASE`, or `BROAD` |
| `campaign_id` | string | No | — | Add to this campaign. Omit for account-level negatives. |
| `confirm` | boolean | No | `false` | `false` = preview only, `true` = execute |

**Two-step workflow:**

**Step 1 — Preview (confirm=false):**
```
"Add 'free dental', 'dental school' as negatives to Jaeger Orthodontics"
```
```
Preview — Add Negative Keywords
Will add 2 negative keywords (PHRASE match) at account level for 5510238841.

Keywords:
  - free dental
  - dental school

To apply, call again with confirm=true.
```

**Step 2 — Execute (confirm=true):**
```
"Yes, go ahead"
```
```
Done — Added 2 negative keyword(s) (PHRASE match) at account level.
Keywords: free dental, dental school
```

**Notes:**
- Omit `campaign_id` to add account-level negatives (apply to all campaigns).
- Pass `campaign_id` to scope negatives to one campaign.
- Pairs naturally with `get_search_term_report` — use suggested negatives from that tool as input here.

---

## 9. `update_campaign_budget`

Update the daily budget for a campaign. Always previews first — requires explicit confirmation to execute.

**Backend route:** `POST /accounts/{customer_id}/campaigns/{campaign_id}/budget`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | Yes | — | Clinic name or 10-digit customer ID |
| `campaign_id` | string | Yes | — | Campaign ID to update |
| `new_daily_budget` | number | Yes | — | New daily budget in account currency |
| `confirm` | boolean | No | `false` | `false` = preview only, `true` = execute |

**Two-step workflow:**

**Step 1 — Preview (confirm=false):**
```
"Update Implants - Ahmedabad campaign budget to $75/day for Jaeger Orthodontics"
```
```
Preview — Budget Update
Campaign 'Implants - Ahmedabad': $50.00/day → $75.00/day (+50%)

To apply, call again with confirm=true.
```

**Step 2 — Execute (confirm=true):**
```
Done — Budget updated for 'Implants - Ahmedabad'.
$50.00/day → $75.00/day
```

**Notes:**
- Safety limit: max 3× increase per single call. Larger increases must be done in steps.
- Budget is applied immediately in Google Ads once confirmed.

---

## 10. `create_campaign`

Create a new Search campaign with an ad group and keywords. Campaign starts **PAUSED** for safety.

**Backend route:** `POST /accounts/{customer_id}/campaigns`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | Yes | — | Clinic name or 10-digit customer ID |
| `campaign_name` | string | Yes | — | Name for the new campaign |
| `daily_budget` | number | Yes | — | Daily budget in account currency |
| `ad_group_name` | string | Yes | — | Name for the initial ad group |
| `keywords` | array of strings | Yes | — | Keywords to add to the ad group |
| `match_type` | string | No | `PHRASE` | `EXACT`, `PHRASE`, or `BROAD` |
| `target_locations` | array of strings | No | — | Location names to target (e.g. `["San Diego", "La Jolla"]`) |
| `confirm` | boolean | No | `false` | `false` = preview only, `true` = create |

**Two-step workflow:**

**Step 1 — Preview (confirm=false):**
```
"Create a teeth whitening campaign for Apex Dental with $40/day budget,
 keywords: teeth whitening, teeth whitening near me, professional teeth whitening"
```
```
Preview — Create Campaign
Will create campaign 'Teeth Whitening - San Diego' for account 8785895348.
Daily budget: $40.00 | Ad group: 'Whitening General' | Match type: PHRASE

Keywords (3):
  - teeth whitening
  - teeth whitening near me
  - professional teeth whitening

To create, call again with confirm=true.
```

**Step 2 — Execute (confirm=true):**
```
Done — Campaign created.
- Name: Teeth Whitening - San Diego
- Campaign ID: 1234567890
- Daily budget: $40.00
- Keywords added: 3
- Status: PAUSED (enable in Google Ads UI when ready)
```

**Notes:**
- Creates: Campaign → Ad Group → Keywords (in sequence).
- Does **not** create ads. Add Responsive Search Ads manually in the Google Ads UI, or use `generate_ad_variations` to draft copy first.
- Campaign is always created as PAUSED — must be manually enabled.

---

## 11. `generate_ad_variations`

Generate Google Ads RSA-ready ad copy using AI — 15 headlines and 4 descriptions. All outputs are validated against Google's character limits.

**Backend route:** `POST /accounts/{customer_id}/ad-copy`

**Parameters:**

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `customer_id` | string | Yes | — | Clinic name or 10-digit customer ID |
| `service` | string | Yes | — | Dental service to advertise (e.g. `"teeth whitening"`, `"dental implants"`) |
| `location` | string | Yes | — | City or area to target (e.g. `"San Diego"`, `"Ahmedabad"`) |
| `campaign_id` | string | No | — | Associate generated copy with a specific campaign |
| `unique_selling_points` | array of strings | No | — | USPs to emphasise (e.g. `["same-day appointments", "insurance accepted"]`) |

**Example call:**
```
"Generate ad copy for dental implants in Ahmedabad for Jaeger Orthodontics,
 USPs: 20 years experience, free consultation, EMI available"
```

**Example output:**
```
Ad Copy — Dental Implants | Ahmedabad (Jaeger Orthodontics)

Headlines (15/15 — max 30 chars each)
--------------------------------------------------
 1. Dental Implants Ahmedabad  [27 chars]
 2. Free Implant Consultation  [26 chars]
 3. 20 Yrs Implant Experience  [26 chars]
 4. Same-Day Implant Consult   [25 chars]
 5. Affordable Dental Implants [28 chars]
 ...

Descriptions (4/4 — max 90 chars each)
--------------------------------------------------
1. Replace missing teeth with permanent implants. Free consultation. EMI available.  [83 chars]
2. Trusted implant dentist in Ahmedabad with 20+ years experience. Book today.  [77 chars]
...

Saved to database. Copy-paste directly into Google Ads RSA editor.
```

**Notes:**
- Character limits enforced: headlines ≤ 30 chars, descriptions ≤ 90 chars.
- Any violations are auto-truncated and flagged in a warnings section.
- All generated copy is saved to the `generated_ad_copy` Postgres table for future reference.
- History is retrievable via `GET /accounts/{customer_id}/ad-copy/history`.

---

## Name Resolution

All tools that accept `customer_id` support **clinic name input** — you don't need to know the 10-digit ID.

The resolver (`backend/resolver.py`) uses:
1. Exact substring match (highest priority)
2. Fuzzy string matching via `SequenceMatcher`
3. Minimum score threshold of 0.4 — below that, returns a "did you mean?" error with the top 5 closest matches

**Examples:**
- `"Apex"` → resolves to `Apex Dental Group`
- `"jaeger"` → resolves to `Jaeger Orthodontics`
- `"8785895348"` → direct numeric lookup, no fuzzy matching

---

## Cache Reference

| Tool | TTL | Notes |
|---|---|---|
| `list_accounts` | No cache | DB query only, always fast |
| `get_account_summary` | 3 hours | |
| `get_campaign_report` | 3 hours | |
| `generate_ytd_report` | 1h (current month) / 24h (past months) | |
| `get_search_term_report` | 3 hours | |
| `get_keyword_performance` | 3 hours | |
| `get_budget_pacing` | 3 hours | |
| Write tools | No cache | Always live |

Pass `refresh: true` on any read tool to bypass cache and force a live Google Ads API call.
