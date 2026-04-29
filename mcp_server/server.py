"""MCP server — stdio transport, delegates all logic to FastAPI backend."""
import asyncio
from datetime import datetime
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

import mcp_server.client as backend

app = Server("google-ads")


# ── Tool registry ────────────────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_accounts",
            description=(
                "List all client accounts (clinic names + customer IDs) in the registry. "
                "Use this when you need to look up which accounts exist or find a customer ID."
            ),
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        types.Tool(
            name="get_account_summary",
            description=(
                "Get high-level performance metrics (impressions, clicks, spend, conversions, "
                "conversion rate) for one or all Google Ads accounts under the MCC."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Clinic name (e.g. 'Apex Dental') or 10-digit customer ID. Omit for all accounts.",
                    },
                    "date_range": {
                        "type": "string",
                        "description": "Google Ads date range: LAST_30_DAYS, LAST_7_DAYS, THIS_MONTH, LAST_MONTH.",
                        "default": "LAST_30_DAYS",
                    },
                    "refresh": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_campaign_report",
            description=(
                "Get campaign-level performance breakdown for a specific account: "
                "spend, CTR, conversions, CPA, and daily budget per campaign."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "10-digit Google Ads customer ID (no dashes).",
                    },
                    "date_range": {
                        "type": "string",
                        "description": "Google Ads date range constant.",
                        "default": "LAST_30_DAYS",
                    },
                    "campaign_status": {
                        "type": "string",
                        "description": "ENABLED, PAUSED, or REMOVED.",
                        "default": "ENABLED",
                    },
                    "refresh": {"type": "boolean", "default": False},
                },
                "required": ["customer_id"],
            },
        ),
        types.Tool(
            name="generate_ytd_report",
            description=(
                "Generate the full year-to-date performance report across ALL client accounts "
                "as ONE single combined table. Do not split, summarize, or rewrite the output. "
                "Show the table exactly as returned — one row per account per month with "
                "Clicks, Impressions, CTR, Conversions, Cost, Conversion Rate, and CPL. "
                "Current month is marked as in-progress."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Year to report on. Defaults to current year (2026).",
                        "default": 2026,
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": "Bypass cache and fetch fresh data from Google Ads.",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="download_ytd_report",
            description=(
                "Download the year-to-date performance report as an Excel (.xlsx) file. "
                "Saves the workbook to the user's Downloads folder and returns the local file path. "
                "Use this when the user asks to download, export, or save the YTD report as Excel/spreadsheet."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "year": {
                        "type": "integer",
                        "description": "Year to report on. Defaults to current year.",
                    },
                    "refresh": {
                        "type": "boolean",
                        "description": "Bypass cache and fetch fresh data from Google Ads.",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="get_search_term_report",
            description=(
                "Pull search terms that triggered ads for an account. "
                "Automatically flags terms with high spend and zero conversions as "
                "suggested negative keywords."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Clinic name (e.g. 'Jaeger Orthodontics') or 10-digit customer ID."},
                    "date_range": {"type": "string", "default": "LAST_30_DAYS"},
                    "campaign_id": {
                        "type": "string",
                        "description": "Filter to a specific campaign ID. Omit for all campaigns.",
                    },
                    "min_impressions": {
                        "type": "integer",
                        "description": "Minimum impressions to include. Default 10.",
                        "default": 10,
                    },
                    "refresh": {"type": "boolean", "default": False},
                },
                "required": ["customer_id"],
            },
        ),
        types.Tool(
            name="get_keyword_performance",
            description=(
                "Get keyword-level performance including Quality Score, impression share, "
                "spend, and conversions. Flags low Quality Score (<5) and high-spend/zero-conversion keywords."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Clinic name (e.g. 'Jaeger Orthodontics') or 10-digit customer ID."},
                    "date_range": {"type": "string", "default": "LAST_30_DAYS"},
                    "campaign_id": {"type": "string", "description": "Optional campaign filter."},
                    "min_quality_score": {
                        "type": "integer",
                        "description": "Show only keywords with QS below this value (e.g. 5).",
                    },
                    "refresh": {"type": "boolean", "default": False},
                },
                "required": ["customer_id"],
            },
        ),
        types.Tool(
            name="get_budget_pacing",
            description=(
                "Check how each campaign is tracking against its monthly budget. "
                "Projects end-of-month spend and flags campaigns as UNDERSPENDING, ON_TRACK, or OVERSPENDING. "
                "Omit customer_id to check all accounts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Clinic name (e.g. 'Fibonacci Smile') or 10-digit customer ID. Omit for all accounts.",
                    },
                    "refresh": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        ),
        types.Tool(
            name="add_negative_keywords",
            description=(
                "Add negative keywords to a campaign or at account level. "
                "Always previews first (confirm=false). Call again with confirm=true to execute. "
                "Tip: use get_search_term_report first to get suggested negatives."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Clinic name (e.g. 'Jaeger Orthodontics') or 10-digit customer ID."},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of negative keyword strings to add.",
                    },
                    "match_type": {
                        "type": "string",
                        "description": "EXACT, PHRASE, or BROAD. Default PHRASE.",
                        "default": "PHRASE",
                    },
                    "campaign_id": {
                        "type": "string",
                        "description": "Add to this campaign. Omit for account-level negatives.",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "false = preview only, true = execute the change.",
                        "default": False,
                    },
                },
                "required": ["customer_id", "keywords"],
            },
        ),
        types.Tool(
            name="update_campaign_budget",
            description=(
                "Update the daily budget for a campaign. "
                "Always previews the change first (confirm=false). "
                "Call again with confirm=true to apply. Safety limit: max 3× increase per call."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Clinic name (e.g. 'Jaeger Orthodontics') or 10-digit customer ID."},
                    "campaign_id": {"type": "string", "description": "Campaign ID to update."},
                    "new_daily_budget": {
                        "type": "number",
                        "description": "New daily budget in account currency.",
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": "false = preview only, true = execute.",
                        "default": False,
                    },
                },
                "required": ["customer_id", "campaign_id", "new_daily_budget"],
            },
        ),
        types.Tool(
            name="create_campaign",
            description=(
                "Create a new Search campaign with an ad group and keywords. "
                "Campaign starts PAUSED for safety. Preview first with confirm=false, "
                "then call again with confirm=true to create."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "string", "description": "Clinic name (e.g. 'Jaeger Orthodontics') or 10-digit customer ID."},
                    "campaign_name": {"type": "string"},
                    "daily_budget": {"type": "number"},
                    "ad_group_name": {"type": "string"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "match_type": {"type": "string", "default": "PHRASE"},
                    "target_locations": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional location names to target.",
                    },
                    "confirm": {"type": "boolean", "default": False},
                },
                "required": [
                    "customer_id", "campaign_name", "daily_budget",
                    "ad_group_name", "keywords",
                ],
            },
        ),
        types.Tool(
            name="generate_ad_variations",
            description=(
                "Generate Google Ads RSA-ready ad copy using AI — 15 headlines and 4 descriptions "
                "for a given service and location. All outputs are validated against Google's "
                "character limits (30 chars headlines, 90 chars descriptions). "
                "Results are saved to the database for future reference."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Clinic name or 10-digit customer ID.",
                    },
                    "service": {
                        "type": "string",
                        "description": "The dental service to advertise, e.g. 'teeth whitening', 'dental implants', 'Invisalign'.",
                    },
                    "location": {
                        "type": "string",
                        "description": "City or area to target, e.g. 'San Diego', 'Ahmedabad'.",
                    },
                    "campaign_id": {
                        "type": "string",
                        "description": "Optional campaign ID to associate this copy with.",
                    },
                    "unique_selling_points": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional USPs to emphasise, e.g. ['same-day appointments', 'insurance accepted', '20 years experience'].",
                    },
                },
                "required": ["customer_id", "service", "location"],
            },
        ),
    ]


# ── Tool dispatcher ──────────────────────────────────────────────────────────────

@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    try:
        text = await _dispatch(name, arguments)
    except Exception as e:
        text = f"Error calling {name}: {e}"
    return [types.TextContent(type="text", text=text)]


async def _dispatch(name: str, args: dict) -> str:
    if name == "list_accounts":
        result = await backend.get("/accounts")
        lines = ["**Client Accounts**\n"]
        for a in result:
            active = "" if a.get("is_active") else " [inactive]"
            lines.append(f"- {a['name']}{active}  |  `{a['customer_id']}`")
        return "\n".join(lines)

    if name == "get_account_summary":
        customer_id = args.get("customer_id")
        date_range = args.get("date_range", "LAST_30_DAYS")
        refresh = args.get("refresh", False)
        if customer_id:
            result = await backend.get(
                "/accounts/summary",
                params={"customer_id": customer_id, "date_range": date_range, "refresh": refresh},
            )
            return _fmt_account_summary(result)
        else:
            results = await backend.get(
                "/accounts/summary/all",
                params={"date_range": date_range, "refresh": refresh},
            )
            if not results:
                return "No accounts found."
            return "\n\n".join(_fmt_account_summary(r) for r in results)

    elif name == "get_campaign_report":
        result = await backend.get(
            f"/accounts/{args['customer_id']}/campaigns",
            params={
                "date_range": args.get("date_range", "LAST_30_DAYS"),
                "campaign_status": args.get("campaign_status", "ENABLED"),
                "refresh": args.get("refresh", False),
            },
        )
        return _fmt_campaign_report(result, args["customer_id"])

    elif name == "generate_ytd_report":
        result = await backend.get(
            "/reports/ytd",
            params={"year": args.get("year", 2026), "refresh": args.get("refresh", False)},
        )
        return _fmt_ytd_report(result)

    elif name == "download_ytd_report":
        params = {"refresh": args.get("refresh", False)}
        if args.get("year") is not None:
            params["year"] = args["year"]
        xlsx_bytes = await backend.get_bytes("/reports/ytd/excel", params=params)
        return _save_ytd_excel(xlsx_bytes, params.get("year"))

    elif name == "get_search_term_report":
        result = await backend.get(
            f"/accounts/{args['customer_id']}/search-terms",
            params={
                "date_range": args.get("date_range", "LAST_30_DAYS"),
                "campaign_id": args.get("campaign_id"),
                "min_impressions": args.get("min_impressions", 10),
                "refresh": args.get("refresh", False),
            },
        )
        return _fmt_search_terms(result, args["customer_id"])

    elif name == "get_keyword_performance":
        result = await backend.get(
            f"/accounts/{args['customer_id']}/keywords",
            params={
                "date_range": args.get("date_range", "LAST_30_DAYS"),
                "campaign_id": args.get("campaign_id"),
                "min_quality_score": args.get("min_quality_score"),
                "refresh": args.get("refresh", False),
            },
        )
        return _fmt_keywords(result, args["customer_id"])

    elif name == "get_budget_pacing":
        customer_id = args.get("customer_id")
        refresh = args.get("refresh", False)
        if customer_id:
            result = await backend.get(
                f"/accounts/{customer_id}/budget-pacing",
                params={"refresh": refresh},
            )
            return _fmt_budget_pacing(result, customer_id)
        else:
            results = await backend.get("/budget-pacing/all", params={"refresh": refresh})
            return _fmt_budget_pacing_all(results)

    elif name == "add_negative_keywords":
        result = await backend.post(
            f"/accounts/{args['customer_id']}/negative-keywords",
            body={
                "keywords": args["keywords"],
                "match_type": args.get("match_type", "PHRASE"),
                "campaign_id": args.get("campaign_id"),
                "confirm": args.get("confirm", False),
            },
        )
        return _fmt_negative_keywords(result)

    elif name == "update_campaign_budget":
        result = await backend.post(
            f"/accounts/{args['customer_id']}/campaigns/{args['campaign_id']}/budget",
            body={
                "new_daily_budget": args["new_daily_budget"],
                "confirm": args.get("confirm", False),
            },
        )
        return _fmt_budget_update(result)

    elif name == "create_campaign":
        result = await backend.post(
            f"/accounts/{args['customer_id']}/campaigns",
            body={
                "campaign_name": args["campaign_name"],
                "daily_budget": args["daily_budget"],
                "ad_group_name": args["ad_group_name"],
                "keywords": args["keywords"],
                "match_type": args.get("match_type", "PHRASE"),
                "target_locations": args.get("target_locations"),
                "confirm": args.get("confirm", False),
            },
        )
        return _fmt_create_campaign(result)

    elif name == "generate_ad_variations":
        result = await backend.post(
            f"/accounts/{args['customer_id']}/ad-copy",
            body={
                "service": args["service"],
                "location": args["location"],
                "campaign_id": args.get("campaign_id"),
                "unique_selling_points": args.get("unique_selling_points"),
            },
        )
        return _fmt_ad_copy(result)

    else:
        return f"Unknown tool: {name}"


# ── Formatters ───────────────────────────────────────────────────────────────────

def _save_ytd_excel(content: bytes, year: int | None) -> str:
    downloads = Path.home() / "Downloads"
    target_dir = downloads if downloads.is_dir() else Path.home()
    year_part = year if year is not None else datetime.now().year
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = target_dir / f"ytd_report_{year_part}_{timestamp}.xlsx"
    path.write_bytes(content)
    size_kb = len(content) / 1024
    return (
        f"**YTD Report Downloaded**\n"
        f"- Saved to: `{path}`\n"
        f"- Size: {size_kb:,.1f} KB\n"
        f"- Year: {year_part}\n\n"
        f"Open it from your Downloads folder."
    )


def _fmt_account_summary(d: dict) -> str:
    if "message" in d:
        return d["message"]
    return (
        f"**{d.get('account_name', d['customer_id'])}**\n"
        f"- Impressions:    {d['impressions']:,}\n"
        f"- Clicks:         {d['clicks']:,}\n"
        f"- Cost:           ${d['cost']:,.2f}\n"
        f"- Conversions:    {d['conversions']}\n"
        f"- Conv. Rate:     {d['conversion_rate']}%"
    )


def _fmt_campaign_report(campaigns: list, customer_id: str) -> str:
    if not campaigns:
        return f"No campaigns found for account {customer_id}."
    lines = [f"**Campaign Report — {customer_id}** ({len(campaigns)} campaigns)\n"]
    lines.append(
        f"{'Campaign':<40} {'Budget':>10} {'Spend':>10} {'Clicks':>7} "
        f"{'CTR':>6} {'Conv':>6} {'CPA':>10}"
    )
    lines.append("-" * 97)
    for c in campaigns:
        lines.append(
            f"{c['campaign_name'][:40]:<40} "
            f"${c['daily_budget']:>9,.0f} "
            f"${c['cost']:>9,.2f} "
            f"{c['clicks']:>7,} "
            f"{c['ctr']:>5.1f}% "
            f"{c['conversions']:>6.1f} "
            f"${c['cpa']:>9,.2f}"
        )
    return "\n".join(lines)


def _fmt_ytd_report(data: dict) -> str:
    year = data["year"]
    accounts = data["accounts"]
    if not accounts:
        return "No accounts found."

    lines = [
        f"# YTD Performance Report — {year}",
        "",
        "Single combined report for all client accounts. One row per account per month.",
        "",
        "| Account | Month | Clicks | Impressions | CTR | Conversions | Cost | Conv. Rate | CPL |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for account in accounts:
        name = account["account_name"]
        for row in account["months"]:
            month_label = row["month"] + (" *" if row["is_current"] else "")
            cpl = f"${row['cpl']:,.2f}" if row["cpl"] is not None else "—"
            lines.append(
                f"| {name} "
                f"| {month_label} "
                f"| {row['clicks']:,} "
                f"| {row['impressions']:,} "
                f"| {row['ctr']:.2f}% "
                f"| {row['conversions']:.2f} "
                f"| ${row['cost']:,.2f} "
                f"| {row['conv_rate']:.2f}% "
                f"| {cpl} |"
            )

    lines.append("")
    lines.append("`*` = current month (data in progress)")
    return "\n".join(lines)


def _fmt_search_terms(data: dict, customer_id: str) -> str:
    terms = data.get("terms", [])
    negatives = data.get("suggested_negatives", [])

    if not terms:
        return f"No search terms found for account {customer_id}."

    lines = [f"**Search Term Report — {customer_id}** ({len(terms)} terms)\n"]
    lines.append(
        f"{'Search Term':<40} {'Campaign':<25} {'Impr':>6} {'Clicks':>6} "
        f"{'Cost':>8} {'Conv':>6}"
    )
    lines.append("-" * 100)
    for t in terms[:50]:  # cap at 50 rows in chat
        lines.append(
            f"{t['search_term'][:40]:<40} "
            f"{t['campaign'][:25]:<25} "
            f"{t['impressions']:>6,} "
            f"{t['clicks']:>6,} "
            f"${t['cost']:>7,.2f} "
            f"{t['conversions']:>6.1f}"
        )

    if len(terms) > 50:
        lines.append(f"\n... and {len(terms) - 50} more terms.")

    if negatives:
        lines.append(f"\n**Suggested Negative Keywords** ({len(negatives)} terms with spend but 0 conversions):")
        for kw in negatives[:20]:
            lines.append(f"  - {kw}")

    return "\n".join(lines)


def _fmt_keywords(keywords: list, customer_id: str) -> str:
    if not keywords:
        return f"No keywords found for account {customer_id}."

    lines = [f"**Keyword Performance — {customer_id}** ({len(keywords)} keywords)\n"]
    lines.append(
        f"{'Keyword':<35} {'Match':>7} {'QS':>4} {'Impr':>7} "
        f"{'Clicks':>6} {'Cost':>8} {'Conv':>6} {'ImpShr':>7} {'Flags'}"
    )
    lines.append("-" * 105)
    for k in keywords[:50]:
        flags = []
        if k.get("flag_low_qs"):
            flags.append("LOW_QS")
        if k.get("flag_high_spend_low_conv"):
            flags.append("NO_CONV")
        flag_str = ", ".join(flags)
        lines.append(
            f"{k['keyword'][:35]:<35} "
            f"{k['match_type'][:7]:>7} "
            f"{k['quality_score']:>4} "
            f"{k['impressions']:>7,} "
            f"{k['clicks']:>6,} "
            f"${k['cost']:>7,.2f} "
            f"{k['conversions']:>6.1f} "
            f"{k['impression_share']:>6.1f}% "
            f"{flag_str}"
        )

    if len(keywords) > 50:
        lines.append(f"\n... and {len(keywords) - 50} more keywords.")

    return "\n".join(lines)


def _fmt_budget_pacing(campaigns: list, customer_id: str) -> str:
    if not campaigns:
        return f"No active campaigns found for account {customer_id}."

    status_icon = {"ON_TRACK": "OK", "UNDERSPENDING": "LOW", "OVERSPENDING": "HIGH"}
    lines = [f"**Budget Pacing — {customer_id}**\n"]
    lines.append(
        f"{'Campaign':<40} {'Daily Bdgt':>11} {'MTD Spend':>11} "
        f"{'Projected':>11} {'Pacing%':>8} {'Status'}"
    )
    lines.append("-" * 100)
    for c in campaigns:
        icon = status_icon.get(c["status"], "?")
        lines.append(
            f"{c['campaign_name'][:40]:<40} "
            f"${c['daily_budget']:>10,.2f} "
            f"${c['spend_mtd']:>10,.2f} "
            f"${c['projected_spend']:>10,.2f} "
            f"{c['pacing_pct']:>7.1f}% "
            f"[{icon}] {c['status']}"
        )
    return "\n".join(lines)


def _fmt_budget_pacing_all(accounts: list) -> str:
    if not accounts:
        return "No accounts found."
    lines = []
    for a in accounts:
        lines.append(_fmt_budget_pacing(a["campaigns"], a["account_name"]))
        lines.append("")
    return "\n".join(lines)


def _fmt_negative_keywords(result: dict) -> str:
    if result.get("preview"):
        return (
            f"**Preview — Add Negative Keywords**\n"
            f"{result['message']}\n\n"
            f"Keywords:\n" + "\n".join(f"  - {kw}" for kw in result["keywords"]) +
            "\n\nTo apply, call again with confirm=true."
        )
    return (
        f"**Done** — Added {result['added_count']} negative keyword(s) "
        f"({result['match_type']} match) at {result['level']} level.\n"
        f"Keywords: {', '.join(result['keywords'])}"
    )


def _fmt_budget_update(result: dict) -> str:
    if result.get("preview"):
        return (
            f"**Preview — Budget Update**\n"
            f"{result['message']}\n\n"
            f"To apply, call again with confirm=true."
        )
    return (
        f"**Done** — Budget updated for '{result['campaign_name']}'.\n"
        f"${result['previous_daily_budget']:,.2f}/day → ${result['new_daily_budget']:,.2f}/day"
    )


def _fmt_create_campaign(result: dict) -> str:
    if result.get("preview"):
        return (
            f"**Preview — Create Campaign**\n"
            f"{result['message']}\n\n"
            f"Keywords ({result['keyword_count']}):\n"
            + "\n".join(f"  - {kw}" for kw in result["keywords"]) +
            "\n\nTo create, call again with confirm=true."
        )
    return (
        f"**Done** — Campaign created.\n"
        f"- Name: {result['campaign_name']}\n"
        f"- Campaign ID: {result['campaign_id']}\n"
        f"- Daily budget: ${result['daily_budget']:,.2f}\n"
        f"- Keywords added: {result['keywords_added']}\n"
        f"- Status: PAUSED (enable in Google Ads UI when ready)"
    )


def _fmt_ad_copy(result: dict) -> str:
    account = result.get("account_name", "")
    service = result["service"]
    location = result["location"]
    headlines = result["headlines"]
    descriptions = result["descriptions"]
    violations = result.get("violations", [])

    lines = [
        f"**Ad Copy — {service.title()} | {location}**"
        + (f" ({account})" if account else ""),
        "",
        f"**Headlines** ({len(headlines)}/15 — max 30 chars each)",
        "-" * 50,
    ]
    for i, h in enumerate(headlines, 1):
        lines.append(f"{i:>2}. {h}  [{len(h)} chars]")

    lines += [
        "",
        f"**Descriptions** ({len(descriptions)}/4 — max 90 chars each)",
        "-" * 50,
    ]
    for i, d in enumerate(descriptions, 1):
        lines.append(f"{i}. {d}  [{len(d)} chars]")

    if violations:
        lines += ["", "**Warnings (auto-truncated):**"]
        for v in violations:
            lines.append(f"  - {v}")

    lines += ["", "_Saved to database. Copy-paste directly into Google Ads RSA editor._"]
    return "\n".join(lines)


# ── Entry point ──────────────────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream, write_stream, app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
