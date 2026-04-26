import asyncio
import json
import os
from calendar import month_name
from contextlib import asynccontextmanager
from datetime import date

import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import engine, get_db
from backend.resolver import resolve_customer_id, list_all_accounts
from backend.google_ads.auth import get_google_ads_client
from backend.google_ads.campaigns import (
    create_campaign,
    preview_budget_update,
    preview_create_campaign,
    update_campaign_budget,
)
from backend.google_ads.keywords import add_negative_keywords, preview_negative_keywords
from backend.google_ads.ad_copy import generate_ad_copy
from backend.google_ads.reporting import (
    cache_key,
    get_account_summary,
    get_budget_pacing,
    get_campaign_report,
    get_keyword_performance,
    get_monthly_metrics,
    get_search_term_report,
    list_child_accounts,
)

load_dotenv()

# ── TTLs ────────────────────────────────────────────────────────────────────────
TTL_CURRENT_MONTH = 60 * 60          # 1 hour
TTL_PAST_MONTH = 60 * 60 * 24        # 24 hours
TTL_DEFAULT = 60 * 60 * 3            # 3 hours

redis_client: aioredis.Redis | None = None


# ── Lifespan ─────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client

    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    print("Database connection OK")

    redis_client = aioredis.from_url(
        os.environ["REDIS_URL"], decode_responses=True
    )
    await redis_client.ping()
    print("Redis connection OK")

    yield

    await redis_client.aclose()
    await engine.dispose()


app = FastAPI(title="Google Ads MCP Backend", lifespan=lifespan)


# ── Cache helper ─────────────────────────────────────────────────────────────────

async def _cached(key: str, ttl: int, refresh: bool, fn):
    if not refresh:
        cached = await redis_client.get(key)
        if cached:
            return json.loads(cached)

    result = fn()
    await redis_client.setex(key, ttl, json.dumps(result, default=str))

    # Track API calls
    today = date.today().isoformat()
    await redis_client.incr(f"api_calls:{today}")
    await redis_client.expire(f"api_calls:{today}", 86400)

    return result


# ── Infra routes ─────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rate-limit-status")
async def rate_limit_status():
    today = date.today().isoformat()
    count = int(await redis_client.get(f"api_calls:{today}") or 0)
    limit = 15000
    return {
        "date": today,
        "calls_today": count,
        "limit": limit,
        "percent_used": round(count / limit * 100, 1),
        "warning": count / limit >= 0.8,
    }


# ── Account routes ───────────────────────────────────────────────────────────────

@app.get("/accounts")
async def list_accounts(db: AsyncSession = Depends(get_db)):
    """List all accounts from DB registry (fast, no API call)."""
    return await list_all_accounts(db)


@app.get("/accounts/resolve")
async def resolve_account(q: str, db: AsyncSession = Depends(get_db)):
    """
    Resolve a clinic name or customer_id to a canonical customer_id.
    e.g. ?q=Apex+Dental  →  {customer_id: '8785895348', name: 'Apex Dental Group'}
    """
    try:
        customer_id, name = await resolve_customer_id(q, db)
        return {"customer_id": customer_id, "name": name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/accounts/summary")
async def account_summary(
    customer_id: str,
    date_range: str = "LAST_30_DAYS",
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    customer_id, _ = await resolve_customer_id(customer_id, db)
    client = get_google_ads_client()
    key = cache_key(customer_id, "account_summary", {"date_range": date_range})
    return await _cached(
        key, TTL_DEFAULT, refresh,
        lambda: get_account_summary(client, customer_id, date_range),
    )


@app.get("/accounts/summary/all")
async def all_accounts_summary(
    date_range: str = "LAST_30_DAYS",
    refresh: bool = False,
):
    client = get_google_ads_client()
    accounts = list_child_accounts(client)
    results = []
    for account in accounts:
        cid = account["customer_id"]
        key = cache_key(cid, "account_summary", {"date_range": date_range})
        summary = await _cached(
            key, TTL_DEFAULT, refresh,
            lambda c=cid: get_account_summary(client, c, date_range),
        )
        results.append(summary)
    return results


# ── YTD report ────────────────────────────────────────────────────────────────────

@app.get("/reports/ytd")
async def ytd_report(year: int = Query(default=None), refresh: bool = False):
    if year is None:
        year = date.today().year

    client = get_google_ads_client()
    accounts = list_child_accounts(client)

    today = date.today()
    months_to_fetch = list(range(1, today.month + 1)) if year == today.year else list(range(1, 13))
    current_month = today.month if year == today.year else None

    async def fetch_account(account: dict) -> dict:
        cid = account["customer_id"]
        monthly_rows = []

        for month in months_to_fetch:
            is_current = (month == current_month)
            ttl = TTL_CURRENT_MONTH if is_current else TTL_PAST_MONTH
            key = f"ytd:{cid}:{year}-{month:02d}"

            metrics = await _cached(
                key, ttl, refresh,
                lambda c=cid, m=month: get_monthly_metrics(client, c, year, m),
            )
            monthly_rows.append({
                "month": f"{month_name[month]} {year}",
                "is_current": is_current,
                **metrics,
            })

        return {
            "account_name": account["name"],
            "customer_id": cid,
            "months": monthly_rows,
        }

    # Fetch all accounts concurrently in batches of 10
    results = []
    for i in range(0, len(accounts), 10):
        batch = accounts[i:i + 10]
        batch_results = await asyncio.gather(*[fetch_account(a) for a in batch])
        results.extend(batch_results)

    results.sort(key=lambda x: x["account_name"])
    return {"year": year, "accounts": results}


# ── Campaign routes ───────────────────────────────────────────────────────────────

@app.get("/accounts/{customer_id}/campaigns")
async def campaign_report(
    customer_id: str,
    date_range: str = "LAST_30_DAYS",
    campaign_status: str = "ENABLED",
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    customer_id, _ = await resolve_customer_id(customer_id, db)
    client = get_google_ads_client()
    key = cache_key(
        customer_id, "campaign_report",
        {"date_range": date_range, "status": campaign_status},
    )
    return await _cached(
        key, TTL_DEFAULT, refresh,
        lambda: get_campaign_report(client, customer_id, date_range, campaign_status),
    )


# ── Search terms ──────────────────────────────────────────────────────────────────

@app.get("/accounts/{customer_id}/search-terms")
async def search_term_report(
    customer_id: str,
    date_range: str = "LAST_30_DAYS",
    campaign_id: str = None,
    min_impressions: int = 10,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    customer_id, _ = await resolve_customer_id(customer_id, db)
    client = get_google_ads_client()
    key = cache_key(
        customer_id, "search_terms",
        {"date_range": date_range, "campaign_id": campaign_id, "min_imp": min_impressions},
    )
    return await _cached(
        key, TTL_DEFAULT, refresh,
        lambda: get_search_term_report(
            client, customer_id, date_range, campaign_id, min_impressions
        ),
    )


# ── Keywords ──────────────────────────────────────────────────────────────────────

@app.get("/accounts/{customer_id}/keywords")
async def keyword_performance(
    customer_id: str,
    date_range: str = "LAST_30_DAYS",
    campaign_id: str = None,
    min_quality_score: int = None,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    customer_id, _ = await resolve_customer_id(customer_id, db)
    client = get_google_ads_client()
    key = cache_key(
        customer_id, "keywords",
        {"date_range": date_range, "campaign_id": campaign_id, "min_qs": min_quality_score},
    )
    return await _cached(
        key, TTL_DEFAULT, refresh,
        lambda: get_keyword_performance(
            client, customer_id, date_range, campaign_id, min_quality_score
        ),
    )


# ── Budget pacing ─────────────────────────────────────────────────────────────────

@app.get("/accounts/{customer_id}/budget-pacing")
async def budget_pacing(
    customer_id: str,
    refresh: bool = False,
    db: AsyncSession = Depends(get_db),
):
    customer_id, _ = await resolve_customer_id(customer_id, db)
    client = get_google_ads_client()
    key = cache_key(customer_id, "budget_pacing", {})
    return await _cached(
        key, TTL_DEFAULT, refresh,
        lambda: get_budget_pacing(client, customer_id),
    )


@app.get("/budget-pacing/all")
async def budget_pacing_all(refresh: bool = False):
    client = get_google_ads_client()
    accounts = list_child_accounts(client)
    results = []
    for account in accounts:
        cid = account["customer_id"]
        key = cache_key(cid, "budget_pacing", {})
        pacing = await _cached(
            key, TTL_DEFAULT, refresh,
            lambda c=cid: get_budget_pacing(client, c),
        )
        results.append({"account_name": account["name"], "customer_id": cid, "campaigns": pacing})
    return results


# ── Write: negative keywords ──────────────────────────────────────────────────────

class NegativeKeywordsRequest(BaseModel):
    keywords: list[str]
    match_type: str = "PHRASE"
    campaign_id: str | None = None
    confirm: bool = False


@app.post("/accounts/{customer_id}/negative-keywords")
async def negative_keywords(
    customer_id: str,
    body: NegativeKeywordsRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.keywords:
        raise HTTPException(status_code=400, detail="keywords list is empty")
    customer_id, _ = await resolve_customer_id(customer_id, db)

    if not body.confirm:
        return preview_negative_keywords(body.keywords, body.match_type, body.campaign_id)

    client = get_google_ads_client()
    return add_negative_keywords(
        client, customer_id, body.keywords, body.match_type, body.campaign_id
    )


# ── Write: budget update ──────────────────────────────────────────────────────────

class BudgetUpdateRequest(BaseModel):
    new_daily_budget: float
    confirm: bool = False


@app.post("/accounts/{customer_id}/campaigns/{campaign_id}/budget")
async def update_budget(
    customer_id: str,
    campaign_id: str,
    body: BudgetUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    if body.new_daily_budget <= 0:
        raise HTTPException(status_code=400, detail="new_daily_budget must be positive")
    customer_id, _ = await resolve_customer_id(customer_id, db)
    client = get_google_ads_client()

    if not body.confirm:
        return preview_budget_update(client, customer_id, campaign_id, body.new_daily_budget)

    return update_campaign_budget(client, customer_id, campaign_id, body.new_daily_budget)


# ── Write: create campaign ────────────────────────────────────────────────────────

class CreateCampaignRequest(BaseModel):
    campaign_name: str
    daily_budget: float
    ad_group_name: str
    keywords: list[str]
    match_type: str = "PHRASE"
    target_locations: list[str] | None = None
    confirm: bool = False


@app.post("/accounts/{customer_id}/campaigns")
async def create_new_campaign(
    customer_id: str,
    body: CreateCampaignRequest,
    db: AsyncSession = Depends(get_db),
):
    if not body.keywords:
        raise HTTPException(status_code=400, detail="keywords list is empty")
    if body.daily_budget <= 0:
        raise HTTPException(status_code=400, detail="daily_budget must be positive")
    customer_id, _ = await resolve_customer_id(customer_id, db)

    if not body.confirm:
        return preview_create_campaign(
            body.campaign_name,
            body.daily_budget,
            body.ad_group_name,
            body.keywords,
            body.match_type,
        )

    client = get_google_ads_client()
    return create_campaign(
        client,
        customer_id,
        body.campaign_name,
        body.daily_budget,
        body.ad_group_name,
        body.keywords,
        body.match_type,
        body.target_locations,
    )


# ── Ad copy generation ────────────────────────────────────────────────────────────

class AdCopyRequest(BaseModel):
    service: str
    location: str
    campaign_id: str | None = None
    unique_selling_points: list[str] | None = None


@app.post("/accounts/{customer_id}/ad-copy")
async def generate_ad_copy_route(
    customer_id: str,
    body: AdCopyRequest,
    db: AsyncSession = Depends(get_db),
):
    customer_id, account_name = await resolve_customer_id(customer_id, db)

    result = generate_ad_copy(
        service=body.service,
        location=body.location,
        unique_selling_points=body.unique_selling_points,
    )

    # Persist to generated_ad_copy table
    await db.execute(
        text("""
            INSERT INTO generated_ad_copy
              (customer_id, campaign_id, service, location, headlines, descriptions, created_at)
            VALUES
              (:customer_id, :campaign_id, :service, :location, :headlines::jsonb, :descriptions::jsonb, :created_at)
        """),
        {
            "customer_id": customer_id,
            "campaign_id": body.campaign_id,
            "service": body.service,
            "location": body.location,
            "headlines": json.dumps(result["headlines"]),
            "descriptions": json.dumps(result["descriptions"]),
            "created_at": result["generated_at"],
        },
    )
    await db.commit()

    result["account_name"] = account_name
    return result


@app.get("/accounts/{customer_id}/ad-copy/history")
async def ad_copy_history(
    customer_id: str,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    customer_id, _ = await resolve_customer_id(customer_id, db)
    rows = await db.execute(
        text("""
            SELECT service, location, headlines, descriptions, created_at
            FROM generated_ad_copy
            WHERE customer_id = :cid
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"cid": customer_id, "limit": limit},
    )
    return [
        {
            "service": r.service,
            "location": r.location,
            "headlines": r.headlines,
            "descriptions": r.descriptions,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows.fetchall()
    ]


# ── Change log ────────────────────────────────────────────────────────────────────

@app.get("/accounts/{customer_id}/changes")
async def change_log(customer_id: str, limit: int = 20):
    return {"customer_id": customer_id, "changes": [], "note": "Change log DB integration pending"}
