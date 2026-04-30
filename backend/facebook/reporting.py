"""Facebook Graph API reporting — read-only data fetchers.

Mirrors the shape of backend/google_ads/reporting.py:
  - list_fb_ad_accounts() enumerates all ad accounts under the Business Manager
  - get_adset_frequency() / get_creative_performance() pull per-account metrics

All functions raise on Graph API errors so the agent retry/log layer can decide.
"""
import logging
from typing import Any

import httpx

from backend.facebook.auth import access_token, business_id, graph_base

logger = logging.getLogger(__name__)

_TIMEOUT = 60


def _get(path: str, params: dict | None = None) -> dict:
    """GET /<path> with token attached. Returns parsed JSON, raises on HTTP error."""
    p = {"access_token": access_token(), **(params or {})}
    response = httpx.get(f"{graph_base()}/{path.lstrip('/')}", params=p, timeout=_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _paginate(path: str, params: dict | None = None) -> list[dict]:
    """GET with pagination — follows `paging.next` cursors until exhausted."""
    out: list[dict] = []
    p = {"access_token": access_token(), **(params or {})}
    url = f"{graph_base()}/{path.lstrip('/')}"
    while url:
        response = httpx.get(url, params=p, timeout=_TIMEOUT)
        response.raise_for_status()
        body = response.json()
        out.extend(body.get("data", []))
        url = body.get("paging", {}).get("next")
        p = None  # next URL is fully-formed
    return out


# ── Account discovery ────────────────────────────────────────────────────────

def list_fb_ad_accounts() -> list[dict]:
    """Return all active ad accounts the Business Manager can act on.

    Queries BOTH `owned_ad_accounts` (BM directly owns) AND `client_ad_accounts`
    (BM has agency access to a client's account). Agencies like MethodPro mostly
    have client accounts, not owned ones.

    Mirrors list_child_accounts() from google_ads/reporting.py. Filters out
    disabled / closed accounts so agents don't waste cycles on them.
    """
    bid = business_id()
    # account_status: 1=ACTIVE, 2=DISABLED, 3=UNSETTLED, 7=PENDING_RISK_REVIEW,
    # 8=PENDING_SETTLEMENT, 9=IN_GRACE_PERIOD, 100=PENDING_CLOSURE, 101=CLOSED.
    # Treat 1 and 9 as usable (active or in grace period).
    USABLE = {1, 9}

    rows: list[dict] = []
    for endpoint in ("owned_ad_accounts", "client_ad_accounts"):
        try:
            rows.extend(_paginate(
                f"{bid}/{endpoint}",
                {"fields": "id,name,account_status", "limit": "100"},
            ))
        except httpx.HTTPStatusError as exc:
            # If the BM has no client accounts at all, FB may 400 — keep going.
            logger.warning("Could not list %s: %s", endpoint, exc)

    # De-duplicate by ad_account_id (an account could appear in both endpoints
    # if the BM both owns AND has client access — rare but possible).
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        aid = r["id"]
        if aid in seen:
            continue
        if r.get("account_status") not in USABLE:
            continue
        seen.add(aid)
        out.append({"ad_account_id": aid, "name": r.get("name", aid)})
    return out


# ── Account summary (Agent 7 — Weekly Digest) ────────────────────────────────

def get_fb_account_summary(ad_account_id: str, start_date: str, end_date: str) -> dict:
    """Account-level metrics for a date range. Mirrors get_account_summary_custom().

    `start_date` / `end_date` are YYYY-MM-DD strings.
    Returns aggregated totals; empty/zero dict if no activity.
    """
    body = _get(
        f"{ad_account_id}/insights",
        {
            "fields": "impressions,clicks,spend,actions,ctr,cpm",
            "time_range": f'{{"since":"{start_date}","until":"{end_date}"}}',
            "level": "account",
        },
    )
    rows = body.get("data", [])
    if not rows:
        return {
            "ad_account_id": ad_account_id,
            "impressions": 0, "clicks": 0, "spend": 0.0,
            "conversions": 0.0, "ctr": 0.0, "cpm": 0.0,
        }
    r = rows[0]
    return {
        "ad_account_id": ad_account_id,
        "impressions": int(r.get("impressions", 0) or 0),
        "clicks": int(r.get("clicks", 0) or 0),
        "spend": float(r.get("spend", 0) or 0),
        "conversions": _extract_total_results(r.get("actions") or []),
        "ctr": float(r.get("ctr", 0) or 0),
        "cpm": float(r.get("cpm", 0) or 0),
    }


# ── Ad set frequency (Agent 4 — Ad Fatigue) ──────────────────────────────────

def get_adset_frequency(ad_account_id: str, days: int = 3) -> list[dict]:
    """Return ad sets with frequency, spend, impressions, and parent campaign objective.

    `days` controls the trailing window for insights (default 3 days, matching the
    fatigue monitor cadence). Ad sets with zero impressions in the window are
    excluded since frequency is undefined.
    """
    date_preset = _date_preset_for_days(days)
    fields = (
        "id,name,status,"
        "campaign{objective},"
        f"insights.date_preset({date_preset}){{frequency,impressions,spend,reach}}"
    )
    rows = _paginate(
        f"{ad_account_id}/adsets",
        {"fields": fields, "effective_status": '["ACTIVE"]', "limit": "100"},
    )

    out = []
    for r in rows:
        insights = (r.get("insights") or {}).get("data", [])
        if not insights:
            continue
        i = insights[0]
        impressions = int(i.get("impressions", 0) or 0)
        if impressions == 0:
            continue
        out.append({
            "adset_id": r["id"],
            "adset_name": r.get("name", r["id"]),
            "campaign_objective": (r.get("campaign") or {}).get("objective", "UNKNOWN"),
            "frequency": float(i.get("frequency", 0) or 0),
            "impressions": impressions,
            "reach": int(i.get("reach", 0) or 0),
            "spend": float(i.get("spend", 0) or 0),
        })
    return out


# ── Creative performance (Agent 5 — Creative Ranker) ─────────────────────────

def get_creative_performance(ad_account_id: str, days: int = 7) -> list[dict]:
    """Return ads ranked by CTR with spend, impressions, clicks, conversions, CPR.

    Used by the weekly Creative Performance Ranker. Excludes ads with no spend.
    """
    date_preset = _date_preset_for_days(days)
    fields = (
        "id,name,status,"
        "creative{id,name,thumbnail_url},"
        f"insights.date_preset({date_preset})"
        "{ctr,cpm,impressions,clicks,spend,actions,cost_per_action_type}"
    )
    rows = _paginate(
        f"{ad_account_id}/ads",
        {"fields": fields, "effective_status": '["ACTIVE"]', "limit": "100"},
    )

    out = []
    for r in rows:
        insights = (r.get("insights") or {}).get("data", [])
        if not insights:
            continue
        i = insights[0]
        spend = float(i.get("spend", 0) or 0)
        if spend == 0:
            continue
        creative = r.get("creative") or {}
        out.append({
            "ad_id": r["id"],
            "ad_name": r.get("name", r["id"]),
            "creative_id": creative.get("id"),
            "creative_name": creative.get("name", ""),
            "ctr": float(i.get("ctr", 0) or 0),
            "cpm": float(i.get("cpm", 0) or 0),
            "impressions": int(i.get("impressions", 0) or 0),
            "clicks": int(i.get("clicks", 0) or 0),
            "spend": spend,
            "results": _extract_total_results(i.get("actions") or []),
            "cost_per_result": _extract_primary_cost_per_result(
                i.get("cost_per_action_type") or []
            ),
        })

    # Rank by CTR descending — caller can re-sort by cost_per_result if desired
    out.sort(key=lambda x: x["ctr"], reverse=True)
    return out


# ── Helpers ──────────────────────────────────────────────────────────────────

def _date_preset_for_days(days: int) -> str:
    """Map a window-in-days to the closest Graph API date_preset literal."""
    if days <= 1:
        return "yesterday"
    if days <= 3:
        return "last_3d"
    if days <= 7:
        return "last_7d"
    if days <= 14:
        return "last_14d"
    if days <= 28:
        return "last_28d"
    return "last_30d"


_RESULT_ACTION_TYPES = (
    "purchase",
    "lead",
    "complete_registration",
    "schedule",
    "submit_application",
    "onsite_conversion.lead_grouped",
    "offsite_conversion.fb_pixel_lead",
    "offsite_conversion.fb_pixel_purchase",
    "offsite_conversion.fb_pixel_complete_registration",
)


def _extract_total_results(actions: list[dict]) -> float:
    """Sum action values for the action types we treat as 'results'."""
    total = 0.0
    for a in actions:
        if a.get("action_type") in _RESULT_ACTION_TYPES:
            try:
                total += float(a.get("value", 0))
            except (TypeError, ValueError):
                pass
    return total


def _extract_primary_cost_per_result(costs: list[dict]) -> float | None:
    """Return cost-per-result for the first matching result action type, else None."""
    for c in costs:
        if c.get("action_type") in _RESULT_ACTION_TYPES:
            try:
                return float(c.get("value", 0))
            except (TypeError, ValueError):
                continue
    return None
