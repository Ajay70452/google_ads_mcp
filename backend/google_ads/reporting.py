"""Google Ads reporting queries — all read-only GAQL."""
import asyncio
import calendar
import hashlib
import json
import os
from datetime import date
from google.ads.googleads.client import GoogleAdsClient


# ── Low-level helpers ───────────────────────────────────────────────────────────

def _query(client: GoogleAdsClient, customer_id: str, gaql: str) -> list:
    ga_service = client.get_service("GoogleAdsService")
    response = ga_service.search_stream(customer_id=customer_id, query=gaql)
    rows = []
    for batch in response:
        for row in batch.results:
            rows.append(row)
    return rows


def cache_key(customer_id: str, query_type: str, params: dict) -> str:
    payload = json.dumps(
        {"customer_id": customer_id, "type": query_type, **params}, sort_keys=True
    )
    return f"gaql:{customer_id}:{hashlib.md5(payload.encode()).hexdigest()}"


# ── Account / MCC helpers ───────────────────────────────────────────────────────

EXCLUDED_NAME_KEYWORDS = ("meta",)


def list_child_accounts(client: GoogleAdsClient) -> list[dict]:
    """Return all active non-manager accounts under the MCC.

    Meta-tagged accounts are excluded — this MCC is Google-Ads-only;
    Meta entries come from cross-platform tracking and shouldn't appear
    in reports.
    """
    mcc_id = os.environ["MCC_CUSTOMER_ID"]
    ga_service = client.get_service("GoogleAdsService")
    gaql = """
        SELECT
          customer_client.id,
          customer_client.descriptive_name,
          customer_client.manager
        FROM customer_client
        WHERE customer_client.status = 'ENABLED'
          AND customer_client.manager = FALSE
    """
    response = ga_service.search(customer_id=mcc_id, query=gaql)
    accounts = [
        {
            "customer_id": str(row.customer_client.id),
            "name": row.customer_client.descriptive_name,
        }
        for row in response
    ]
    return [
        a for a in accounts
        if not any(kw in a["name"].lower() for kw in EXCLUDED_NAME_KEYWORDS)
    ]


# ── Account summary ─────────────────────────────────────────────────────────────

def get_account_summary(
    client: GoogleAdsClient, customer_id: str, date_range: str
) -> dict:
    gaql = f"""
        SELECT
          customer.descriptive_name,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.conversions_from_interactions_rate
        FROM customer
        WHERE segments.date DURING {date_range}
    """
    rows = _query(client, customer_id, gaql)
    if not rows:
        return {"customer_id": customer_id, "message": "No data found for this period"}
    row = rows[0]
    return {
        "customer_id": customer_id,
        "account_name": row.customer.descriptive_name,
        "impressions": row.metrics.impressions,
        "clicks": row.metrics.clicks,
        "cost": round(row.metrics.cost_micros / 1_000_000, 2),
        "conversions": round(row.metrics.conversions, 2),
        "conversion_rate": round(
            row.metrics.conversions_from_interactions_rate * 100, 2
        ),
    }


# ── Account summary (custom date range) ────────────────────────────────────────

def get_account_summary_custom(
    client: GoogleAdsClient, customer_id: str, start_date: str, end_date: str
) -> dict:
    """Like get_account_summary() but accepts explicit YYYY-MM-DD dates.

    Used by the anomaly detector to fetch individual week windows.
    Returns aggregated totals across all rows (one row per day in GAQL).
    """
    gaql = f"""
        SELECT
          customer.descriptive_name,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.interactions
        FROM customer
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
    """
    rows = _query(client, customer_id, gaql)

    totals = {
        "account_name": "",
        "impressions": 0,
        "clicks": 0,
        "cost_micros": 0,
        "conversions": 0.0,
        "interactions": 0,
    }
    for row in rows:
        totals["account_name"] = row.customer.descriptive_name
        totals["impressions"] += row.metrics.impressions
        totals["clicks"] += row.metrics.clicks
        totals["cost_micros"] += row.metrics.cost_micros
        totals["conversions"] += row.metrics.conversions
        totals["interactions"] += row.metrics.interactions

    clicks = totals["clicks"]
    impressions = totals["impressions"]
    cost = round(totals["cost_micros"] / 1_000_000, 2)
    conversions = round(totals["conversions"], 2)

    ctr = round(clicks / impressions * 100, 2) if impressions else 0.0
    conv_rate = round(conversions / clicks * 100, 2) if clicks else 0.0
    cpc = round(cost / clicks, 2) if clicks else 0.0

    return {
        "customer_id": customer_id,
        "account_name": totals["account_name"],
        "impressions": impressions,
        "clicks": clicks,
        "cost": cost,
        "conversions": conversions,
        "ctr": ctr,
        "conv_rate": conv_rate,
        "cpc": cpc,
    }


# ── Campaign report ─────────────────────────────────────────────────────────────

def get_campaign_report(
    client: GoogleAdsClient,
    customer_id: str,
    date_range: str,
    campaign_status: str,
) -> list[dict]:
    gaql = f"""
        SELECT
          campaign.id,
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
        WHERE campaign.status = '{campaign_status}'
          AND segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """
    rows = _query(client, customer_id, gaql)
    results = []
    for row in rows:
        results.append(
            {
                "campaign_id": str(row.campaign.id),
                "campaign_name": row.campaign.name,
                "status": row.campaign.status.name,
                "daily_budget": round(
                    row.campaign_budget.amount_micros / 1_000_000, 2
                ),
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "ctr": round(row.metrics.ctr * 100, 2),
                "cost": round(row.metrics.cost_micros / 1_000_000, 2),
                "conversions": round(row.metrics.conversions, 2),
                "cpa": round(row.metrics.cost_per_conversion / 1_000_000, 2),
            }
        )
    return results


# ── YTD monthly report ──────────────────────────────────────────────────────────

def get_monthly_metrics(
    client: GoogleAdsClient, customer_id: str, year: int, month: int
) -> dict:
    """
    Aggregate all ENABLED campaign metrics for a given account + month.
    Returns summed clicks, impressions, cost, conversions, interactions.
    """
    month_start = f"{year}-{month:02d}-01"
    _, last_day = calendar.monthrange(year, month)
    month_end = f"{year}-{month:02d}-{last_day:02d}"

    gaql = f"""
        SELECT
          metrics.clicks,
          metrics.impressions,
          metrics.cost_micros,
          metrics.conversions,
          metrics.interactions
        FROM campaign
        WHERE segments.date BETWEEN '{month_start}' AND '{month_end}'
    """
    rows = _query(client, customer_id, gaql)

    totals = {
        "clicks": 0,
        "impressions": 0,
        "cost_micros": 0,
        "conversions": 0.0,
        "interactions": 0,
    }
    for row in rows:
        totals["clicks"] += row.metrics.clicks
        totals["impressions"] += row.metrics.impressions
        totals["cost_micros"] += row.metrics.cost_micros
        totals["conversions"] += row.metrics.conversions
        totals["interactions"] += row.metrics.interactions

    cost = round(totals["cost_micros"] / 1_000_000, 2)
    impressions = totals["impressions"]
    clicks = totals["clicks"]
    conversions = round(totals["conversions"], 2)
    interactions = totals["interactions"]

    ctr = round(clicks / impressions * 100, 2) if impressions else 0.0
    conv_rate = (
        round(conversions / interactions * 100, 2) if interactions else 0.0
    )
    cpl = round(cost / conversions, 2) if conversions else None

    return {
        "clicks": clicks,
        "impressions": impressions,
        "ctr": ctr,
        "conversions": conversions,
        "cost": cost,
        "conv_rate": conv_rate,
        "cpl": cpl,
    }


# ── Search term report ──────────────────────────────────────────────────────────

def get_search_term_report(
    client: GoogleAdsClient,
    customer_id: str,
    date_range: str,
    campaign_id: str | None,
    min_impressions: int,
) -> dict:
    campaign_filter = (
        f"AND campaign.id = {campaign_id}" if campaign_id else ""
    )
    gaql = f"""
        SELECT
          search_term_view.search_term,
          campaign.name,
          ad_group.name,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions
        FROM search_term_view
        WHERE segments.date DURING {date_range}
          AND metrics.impressions >= {min_impressions}
          {campaign_filter}
        ORDER BY metrics.cost_micros DESC
    """
    rows = _query(client, customer_id, gaql)

    terms = []
    suggested_negatives = []

    for row in rows:
        cost = round(row.metrics.cost_micros / 1_000_000, 2)
        convs = round(row.metrics.conversions, 2)
        entry = {
            "search_term": row.search_term_view.search_term,
            "campaign": row.campaign.name,
            "ad_group": row.ad_group.name,
            "impressions": row.metrics.impressions,
            "clicks": row.metrics.clicks,
            "cost": cost,
            "conversions": convs,
        }
        terms.append(entry)
        # Flag: spent more than $5 with zero conversions
        if cost > 5.0 and convs == 0:
            suggested_negatives.append(row.search_term_view.search_term)

    return {"terms": terms, "suggested_negatives": suggested_negatives}


# ── Keyword performance ─────────────────────────────────────────────────────────

def get_keyword_performance(
    client: GoogleAdsClient,
    customer_id: str,
    date_range: str,
    campaign_id: str | None,
    min_quality_score: int | None,
) -> list[dict]:
    campaign_filter = (
        f"AND campaign.id = {campaign_id}" if campaign_id else ""
    )
    qs_filter = (
        f"AND ad_group_criterion.quality_info.quality_score < {min_quality_score}"
        if min_quality_score
        else ""
    )
    gaql = f"""
        SELECT
          ad_group_criterion.keyword.text,
          ad_group_criterion.keyword.match_type,
          ad_group_criterion.quality_info.quality_score,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.search_impression_share
        FROM keyword_view
        WHERE segments.date DURING {date_range}
          {campaign_filter}
          {qs_filter}
        ORDER BY metrics.cost_micros DESC
    """
    rows = _query(client, customer_id, gaql)
    results = []
    for row in rows:
        cost = round(row.metrics.cost_micros / 1_000_000, 2)
        convs = round(row.metrics.conversions, 2)
        results.append(
            {
                "keyword": row.ad_group_criterion.keyword.text,
                "match_type": row.ad_group_criterion.keyword.match_type.name,
                "quality_score": row.ad_group_criterion.quality_info.quality_score,
                "impressions": row.metrics.impressions,
                "clicks": row.metrics.clicks,
                "cost": cost,
                "conversions": convs,
                "impression_share": round(
                    row.metrics.search_impression_share * 100, 1
                ),
                "flag_low_qs": row.ad_group_criterion.quality_info.quality_score < 5,
                "flag_high_spend_low_conv": cost > 10.0 and convs == 0,
            }
        )
    return results


# ── Budget pacing ───────────────────────────────────────────────────────────────

def get_budget_pacing(
    client: GoogleAdsClient, customer_id: str
) -> list[dict]:
    today = date.today()
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    gaql = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign_budget.amount_micros,
          metrics.cost_micros
        FROM campaign
        WHERE campaign.status = 'ENABLED'
          AND segments.date DURING THIS_MONTH
        ORDER BY campaign.name
    """
    rows = _query(client, customer_id, gaql)

    # Aggregate cost per campaign (GAQL returns one row per day)
    campaigns: dict[str, dict] = {}
    for row in rows:
        cid = str(row.campaign.id)
        if cid not in campaigns:
            campaigns[cid] = {
                "campaign_id": cid,
                "campaign_name": row.campaign.name,
                "daily_budget": round(
                    row.campaign_budget.amount_micros / 1_000_000, 2
                ),
                "spend_mtd": 0.0,
            }
        campaigns[cid]["spend_mtd"] += row.metrics.cost_micros / 1_000_000

    results = []
    for c in campaigns.values():
        daily = c["daily_budget"]
        spend = round(c["spend_mtd"], 2)
        monthly_budget = daily * days_in_month
        projected = (spend / days_elapsed * days_in_month) if days_elapsed else 0

        pct = round(projected / monthly_budget * 100, 1) if monthly_budget else 0
        if pct < 85:
            status = "UNDERSPENDING"
        elif pct > 115:
            status = "OVERSPENDING"
        else:
            status = "ON_TRACK"

        results.append(
            {
                "campaign_id": c["campaign_id"],
                "campaign_name": c["campaign_name"],
                "daily_budget": daily,
                "monthly_budget": round(monthly_budget, 2),
                "spend_mtd": spend,
                "projected_spend": round(projected, 2),
                "pacing_pct": pct,
                "status": status,
            }
        )
    return results
