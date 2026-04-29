# MethodPro Google Ads AI Suite — User Guide
### Conversational Tools + Autonomous Agents for Google Ads

Welcome. This guide walks you through using **MethodPro's in-house Google Ads intelligence platform** — a custom-built system that combines two pieces of advanced tech:

1. **A conversational AI layer** — talk to Claude in plain English, and it pulls live data, builds reports, drafts ad copy, and (with your confirmation) makes changes in Google Ads.
2. **A fleet of autonomous AI agents** — three specialized bots that run on a schedule, scan every account on autopilot, and post their findings to Zoho Cliq while you sleep.

You don't need to know how either works under the hood. The agents do their job whether you're online or not. The conversational layer is there whenever you want to dig in.

---

## What is this, exactly?

We've built a private system that connects Claude (the AI) directly to our Google Ads manager account, **plus** a separate fleet of always-on agents monitoring all 40 accounts in the background. Most agencies copy-paste numbers from Google Ads into spreadsheets and ask ChatGPT to interpret them. We skipped that whole step — and added autonomous monitoring on top.

### The two halves

**Half 1 — Conversational tools (you initiate):**

When you ask Claude *"how is Apex Dental performing this week?"* — behind the scenes:

1. Claude figures out which client account you mean
2. Calls our **MCP server** (Model Context Protocol — a private bridge sitting on your laptop)
3. Which talks to **our cloud backend** running on AWS
4. Which queries the **Google Ads API** in real time
5. Caches the result in a high-speed in-memory store (Redis)
6. And streams the answer back to Claude

1–3 seconds. You just see the answer.

**Half 2 — Autonomous agents (run themselves):**

Three specialized AI agents run on a cron schedule on the cloud backend, with no human in the loop:

- **Budget Pacing Monitor** — every morning, scans every account for over/underspending campaigns
- **Performance Anomaly Detector** — every Monday, compares week-over-week metrics across all 40 accounts and flags abnormal drops or spikes
- **Search Terms Agent** — every Monday, uses AI to classify wasted-spend search terms across the entire portfolio

Each one posts its findings to a dedicated Zoho Cliq channel. You wake up Monday morning to a complete portfolio health report you didn't have to ask for.

This is faster, more proactive, and more powerful than anything off-the-shelf. It's also entirely ours — no third-party AI tool sees our client data.

---

## One-time setup

You only do this once. After that, you just open Claude Desktop and start asking questions.

### Step 1: Install Claude Desktop

If you don't have it: download from https://claude.ai/download. Sign in with your MethodPro Google account.

### Step 2: Install the MCP bridge on your laptop

The "MCP bridge" is a tiny program that lives on your laptop and connects Claude to our backend. Ask the engineering team for:
- The repo link / install package
- The `claude_desktop_config.json` file pre-filled for your machine

### Step 3: Drop the config file into place

The config file tells Claude *"hey, when someone asks about Google Ads, route it through this bridge."*

**Where the file goes (Windows):**
```
C:\Users\<YourUsername>\AppData\Roaming\Claude\claude_desktop_config.json
```

**Where the file goes (Mac):**
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

The file looks roughly like this:

```json
{
  "mcpServers": {
    "google-ads": {
      "command": "C:/Path/To/Python/python.exe",
      "args": ["-m", "mcp_server.server"],
      "env": {
        "BACKEND_URL": "http://184.33.29.155:8001",
        "PYTHONPATH": "C:/Path/To/google_ads_mcp"
      }
    }
  }
}
```

The engineering team will give you a version of this file pre-customized for your laptop. Just paste it in.

### Step 4: Restart Claude Desktop

**Important:** closing the window isn't enough. Right-click the Claude icon in your system tray (bottom-right on Windows, top bar on Mac) → **Quit**. Then reopen.

### Step 5: Confirm it works

Open a new chat in Claude Desktop and type:

> *List all our Google Ads accounts*

If you see a list of MethodPro's clinics come back, you're connected. If you get an error, ping engineering — usually a path or firewall issue.

---

## How to use it (the actual fun part)

You don't memorize commands. You don't write SQL. You just **talk to Claude in plain English**.

Some examples that work right out of the gate:

| What you type | What happens |
|---|---|
| *"How is Apex Dental performing this month?"* | Pulls live spend, clicks, conversions, conversion rate |
| *"Show me a campaign breakdown for Cassidy Smiles last 7 days"* | Lists every campaign with CTR, CPA, daily budget |
| *"Generate the YTD report for all accounts"* | Builds a full month-by-month performance table for every client |
| *"Download the YTD report as Excel"* | Saves a formatted .xlsx to your Downloads folder |
| *"What search terms are wasting budget for Jaeger Orthodontics?"* | Finds high-spend zero-conversion search terms |
| *"Add 'free dental' as a negative keyword for Jaeger Ortho"* | Previews the change first, asks for confirmation, then executes |
| *"Which campaigns are overspending right now?"* | Projects end-of-month spend across every account, flags the issues |
| *"Write 15 headlines for Invisalign in San Diego"* | AI-generates Google Ads-compliant ad copy, validated against character limits |

You don't need to know the customer ID — say the clinic name and Claude figures it out.

---

## The 12 tools, demystified

Under the hood, Claude has access to 12 specialized tools. You'll never call them by name — Claude picks the right one based on what you ask. But here's what's available so you know the full surface area.

### Reporting & analytics

#### 1. `list_accounts`
Lists every clinic in our MCC. *"Show me all our accounts"* triggers this.

#### 2. `get_account_summary`
High-level metrics for one or all accounts: impressions, clicks, spend, conversions, conversion rate. Supports any date range (LAST_7_DAYS, LAST_30_DAYS, THIS_MONTH, LAST_MONTH).

> *"How did all clients do last month?"*
> *"Apex Dental performance this week"*

#### 3. `get_campaign_report`
Drills into one account and breaks performance down by campaign. Shows CTR, CPA, daily budget, conversions per campaign.

> *"Campaign breakdown for Cassidy Smiles"*

#### 4. `generate_ytd_report`
The big one. Pulls **year-to-date performance for every client account**, broken out month-by-month. One row per account per month: Clicks, Impressions, CTR, Conversions, Cost, CR, CPL. Current month is marked as in-progress.

> *"Generate the YTD report"*

#### 5. `download_ytd_report`
Same as above, but instead of displaying, it saves a fully formatted Excel file to your Downloads folder.

> *"Export the YTD report to Excel"*

### Optimization signals

#### 6. `get_search_term_report`
Pulls actual search terms users typed to trigger ads. **Auto-flags terms with high spend and zero conversions** as suggested negatives — the kind of analysis that takes hours manually.

> *"What search terms are wasting money for Jaeger Orthodontics?"*

#### 7. `get_keyword_performance`
Keyword-level data including **Quality Score** and **impression share**. Flags low-QS keywords (<5) and high-spend zero-conversion ones.

> *"Show me low quality score keywords for Apex Dental"*

#### 8. `get_budget_pacing`
Projects each campaign's end-of-month spend based on current daily run rate. Tags every campaign as **UNDERSPENDING / ON_TRACK / OVERSPENDING**.

> *"Which campaigns are off pace this month?"*

### Write actions (with safety)

These tools **make actual changes** in Google Ads. To prevent accidents, every one of them works in two steps:
- **Preview** — Claude shows you exactly what it's about to do
- **Confirm** — only then does it execute

You'll never accidentally blow up a campaign.

#### 9. `add_negative_keywords`
Adds negative keywords at the campaign or account level.

> *"Add 'cheap', 'free', and 'cost' as phrase-match negatives for Jaeger Ortho"*

#### 10. `update_campaign_budget`
Changes a campaign's daily budget. Hard safety limit: **no more than 3× increase per call**.

> *"Increase the budget on Apex Dental's brand campaign to $50/day"*

#### 11. `create_campaign`
Creates a brand-new Search campaign with ad groups and keywords. **Always starts paused** so nothing goes live without you reviewing it first.

> *"Create a new campaign for Cassidy Smiles targeting 'teeth whitening San Diego' at $30/day"*

### AI ad copy

#### 12. `generate_ad_variations`
Uses GPT to write **15 headlines and 4 descriptions** for a given service + location. All output is validated against Google Ads' character limits (30 chars / 90 chars) so it's RSA-ready. Saved to our database for reuse.

> *"Write Google Ads copy for dental implants in Houston, mention same-day appointments and insurance accepted"*

---

## The autonomous agents (the heavy lifters)

This is the part that sets the system apart. Three AI agents run on the cloud backend 24/7, with no human in the loop. They each scan **all 40 accounts**, draw conclusions, and post structured reports to Zoho Cliq.

You don't trigger them. You don't configure them. They just run.

### Agent 1 — Budget Pacing Monitor 🚨
- **Schedule:** Every day at 8 AM UTC
- **Channel:** `#pacingalerts`
- **What it does:** Calculates each campaign's current run-rate against its monthly budget. Projects end-of-month spend. Flags any campaign more than **15% off pace** as either UNDERSPENDING or OVERSPENDING. Sorts by severity (🚨 severe, ⚠️ moderate). Splits the report across multiple Cliq messages if it exceeds the channel's character limit.
- **Why it matters:** Catches blown budgets and stalled campaigns the same day they go sideways — not at end-of-month review when the damage is done.

### Agent 2 — Performance Anomaly Detector 🔴
- **Schedule:** Every Monday at 8 AM UTC
- **Channel:** `#performancealerts`
- **What it does:** Pulls last week's metrics for every account and compares against the **trailing 4-week average**. Flags any account where CPC, CTR, or conversion rate has moved more than **20%** from baseline. Color-codes severity: 🔴 (>40% deviation) vs 🟡 (20–40%). Sorts by impact so the worst offenders are at the top.
- **Why it matters:** Surfaces silent regressions — when a campaign's CPC quietly doubles or conversions drop off a cliff — without anyone needing to manually compare reports.

### Agent 3 — Search Terms AI Classifier 🧠
- **Schedule:** Every Monday at 9 AM UTC
- **Channel:** `#searchtermsreview`
- **What it does:** Pulls every search term that triggered ads across all accounts. Combines two analyses:
  1. **Rule-based** — terms with high spend and zero conversions
  2. **AI-based** — calls GPT to classify each term's intent (job seekers, freebie seekers, DIY queries, irrelevant industries, etc.)
  Outputs each flagged term with a verdict (HIGH / MEDIUM / LOW priority) and a one-line reason.
- **Why it matters:** Manual search-term review across 40 accounts is a multi-hour weekly slog. The agent does it in ~3 minutes and presents a prioritized worklist.

### What you do with the output

Each Cliq message lists the issues, severity-ranked. Typical workflow:

1. Read the alert
2. Open Claude Desktop
3. Tell Claude *"add these as negatives for Jaeger Ortho: …"* or *"increase the budget on this campaign to …"*
4. Claude previews, you confirm, done.

The agents flag, you act. Two halves of the same loop.

---

## Pro tips

**Be specific about time.** *"This month"*, *"last 7 days"*, *"YTD"* all work. If you don't say, it defaults to LAST_30_DAYS.

**Use clinic names, not IDs.** Type *"Apex Dental"*, not *"8785895348"*. Claude resolves it.

**Ask for analysis, not just data.** Don't stop at *"show me Apex Dental performance"* — follow up with *"why is conversion rate down vs last month?"* Claude reads the data and tells you.

**Always say "preview first" for write actions.** Even though they preview by default, explicitly saying it makes the conversation cleaner. Then say *"yes, confirm"* to execute.

**The cache is 3 hours.** If you ran a report 30 minutes ago, the second call returns instantly from cache. To force fresh data, say *"refresh"* or *"pull fresh data"*.

**Big reports take a few seconds.** YTD across 40 accounts pulls a lot of data. 10-30 seconds is normal.

---

## Troubleshooting

**"I don't see Google Ads tools available"** → Claude Desktop wasn't fully quit before reopen. Right-click tray icon → Quit → reopen.

**"It says it can't reach the backend"** → Either you're off VPN, your laptop's offline, or our cloud server is down. Try `curl http://184.33.29.155:8001/health` in a terminal — if that fails, ping engineering.

**"It returned the wrong account"** → Be more specific. *"Apex Dental Group"* beats *"Apex"* (we have multiple accounts with similar names).

**"I want to undo a change I made"** → Every write action is logged in our `change_log` table. Engineering can roll it back. Don't panic.

**Anything else** → Slack the engineering channel. Include:
- What you typed
- What Claude responded
- Time it happened (for log lookup)

---

## What's next

We're already building:
- **Per-user attribution** — every change tagged with who triggered it
- **A read-only web dashboard** — recent agent runs, change log, rate-limit status
- **Auto-rollback** — if a campaign creation fails partway through, the system cleans up automatically
- **More AI agents** — bid strategy recommendations, audience expansion suggestions, competitor monitoring

This is just v1. The system is designed to grow.

---

*Built by MethodPro engineering. Internal use only — do not share screenshots or exports outside the company.*
