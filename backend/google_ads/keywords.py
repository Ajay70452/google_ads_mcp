"""Negative keyword management."""
from datetime import datetime, timezone
from google.ads.googleads.client import GoogleAdsClient


def add_negative_keywords(
    client: GoogleAdsClient,
    customer_id: str,
    keywords: list[str],
    match_type: str,
    campaign_id: str | None,
) -> dict:
    """
    Add negative keywords at campaign level (if campaign_id given)
    or account level (customer negative criteria).

    Returns a summary of what was added.
    """
    match_type_enum = {
        "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
        "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
        "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
    }.get(match_type.upper(), client.enums.KeywordMatchTypeEnum.PHRASE)

    added = []

    if campaign_id:
        # Campaign-level negative keywords
        service = client.get_service("CampaignCriterionService")
        operations = []
        for kw in keywords:
            op = client.get_type("CampaignCriterionOperation")
            criterion = op.create
            criterion.campaign = client.get_service(
                "CampaignService"
            ).campaign_path(customer_id, campaign_id)
            criterion.negative = True
            criterion.keyword.text = kw
            criterion.keyword.match_type = match_type_enum
            operations.append(op)

        response = service.mutate_campaign_criteria(
            customer_id=customer_id, operations=operations
        )
        added = [r.resource_name for r in response.results]
    else:
        # Account-level negative keywords
        service = client.get_service("CustomerNegativeCriterionService")
        operations = []
        for kw in keywords:
            op = client.get_type("CustomerNegativeCriterionOperation")
            criterion = op.create
            criterion.keyword.text = kw
            criterion.keyword.match_type = match_type_enum
            operations.append(op)

        response = service.mutate_customer_negative_criteria(
            customer_id=customer_id, operations=operations
        )
        added = [r.resource_name for r in response.results]

    return {
        "added_count": len(added),
        "level": "campaign" if campaign_id else "account",
        "campaign_id": campaign_id,
        "match_type": match_type.upper(),
        "keywords": keywords,
        "resource_names": added,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


def preview_negative_keywords(
    keywords: list[str],
    match_type: str,
    campaign_id: str | None,
) -> dict:
    """Dry-run preview — no API call, just describe the change."""
    return {
        "preview": True,
        "action": "add_negative_keywords",
        "level": "campaign" if campaign_id else "account",
        "campaign_id": campaign_id,
        "match_type": match_type.upper(),
        "keywords": keywords,
        "count": len(keywords),
        "message": (
            f"Will add {len(keywords)} negative keyword(s) "
            f"({match_type.upper()} match) "
            + (f"to campaign {campaign_id}." if campaign_id else "at account level.")
        ),
    }
