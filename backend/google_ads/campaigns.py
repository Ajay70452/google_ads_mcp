"""Campaign and budget write operations."""
import uuid
from datetime import datetime, timezone
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.protobuf.field_mask_pb2 import FieldMask


# ── Budget update ───────────────────────────────────────────────────────────────

def get_campaign_budget_id(
    client: GoogleAdsClient, customer_id: str, campaign_id: str
) -> tuple[str, float]:
    """Return (budget_resource_name, current_daily_budget_in_currency)."""
    ga_service = client.get_service("GoogleAdsService")
    gaql = f"""
        SELECT
          campaign.id,
          campaign.name,
          campaign_budget.resource_name,
          campaign_budget.amount_micros
        FROM campaign
        WHERE campaign.id = {campaign_id}
    """
    response = ga_service.search(customer_id=customer_id, query=gaql)
    rows = list(response)
    if not rows:
        raise ValueError(f"Campaign {campaign_id} not found in account {customer_id}")
    row = rows[0]
    budget_rn = row.campaign_budget.resource_name
    current = round(row.campaign_budget.amount_micros / 1_000_000, 2)
    return budget_rn, current, row.campaign.name


def preview_budget_update(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    new_daily_budget: float,
) -> dict:
    budget_rn, current, campaign_name = get_campaign_budget_id(
        client, customer_id, campaign_id
    )
    change_pct = round((new_daily_budget - current) / current * 100, 1) if current else 0
    return {
        "preview": True,
        "action": "update_campaign_budget",
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "current_daily_budget": current,
        "new_daily_budget": new_daily_budget,
        "change_pct": change_pct,
        "message": (
            f"Campaign '{campaign_name}': "
            f"${current:,.2f}/day → ${new_daily_budget:,.2f}/day "
            f"({'+' if change_pct >= 0 else ''}{change_pct}%)"
        ),
    }


def update_campaign_budget(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_id: str,
    new_daily_budget: float,
) -> dict:
    budget_rn, current, campaign_name = get_campaign_budget_id(
        client, customer_id, campaign_id
    )

    # Safety: reject > 3× increase in one call
    if current > 0 and new_daily_budget / current > 3:
        raise ValueError(
            f"Budget increase of {round(new_daily_budget/current*100)}% exceeds "
            "the 300% single-call safety limit. Make the change in smaller steps."
        )

    service = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    budget = op.update
    budget.resource_name = budget_rn
    budget.amount_micros = int(new_daily_budget * 1_000_000)

    op.update_mask.CopyFrom(FieldMask(paths=["amount_micros"]))

    response = service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[op]
    )

    return {
        "success": True,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "previous_daily_budget": current,
        "new_daily_budget": new_daily_budget,
        "resource_name": response.results[0].resource_name,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Campaign creation ───────────────────────────────────────────────────────────

def preview_create_campaign(
    campaign_name: str,
    daily_budget: float,
    ad_group_name: str,
    keywords: list[str],
    match_type: str,
) -> dict:
    return {
        "preview": True,
        "action": "create_campaign",
        "campaign_name": campaign_name,
        "daily_budget": daily_budget,
        "ad_group_name": ad_group_name,
        "keyword_count": len(keywords),
        "match_type": match_type.upper(),
        "keywords": keywords,
        "message": (
            f"Will create campaign '{campaign_name}' "
            f"(${daily_budget:,.2f}/day) with ad group '{ad_group_name}' "
            f"and {len(keywords)} {match_type.upper()} match keywords."
        ),
    }


def _mutate_keywords_with_exemptions(client, kw_service, customer_id, kw_ops):
    """Add keywords, auto-exempting any exemptible policy violations (e.g. HEALTH_IN_PERSONALIZED_ADS)."""
    try:
        return kw_service.mutate_ad_group_criteria(
            customer_id=customer_id, operations=kw_ops
        )
    except GoogleAdsException as ex:
        exemptions: dict[int, list] = {}
        for error in ex.failure.errors:
            pvd = error.details.policy_violation_details
            # policy_name is empty string when this detail type is not set
            if not pvd.key.policy_name:
                raise  # non-policy error — re-raise
            if not pvd.is_exemptible:
                raise  # non-exemptible — re-raise
            idx = error.location.field_path_elements[0].index
            exemptions.setdefault(idx, []).append(pvd.key)

    # Retry with exemption keys attached to each violating operation
    for idx, keys in exemptions.items():
        for key in keys:
            exempt_key = client.get_type("PolicyViolationKey")
            exempt_key.policy_name = key.policy_name
            exempt_key.violating_text = key.violating_text
            kw_ops[idx].exempt_policy_violation_keys.append(exempt_key)

    return kw_service.mutate_ad_group_criteria(
        customer_id=customer_id, operations=kw_ops
    )


def create_campaign(
    client: GoogleAdsClient,
    customer_id: str,
    campaign_name: str,
    daily_budget: float,
    ad_group_name: str,
    keywords: list[str],
    match_type: str,
    target_locations: list[str] | None,
) -> dict:
    # 1. Create budget
    budget_service = client.get_service("CampaignBudgetService")
    budget_op = client.get_type("CampaignBudgetOperation")
    budget = budget_op.create
    budget.name = f"Budget for {campaign_name} [{uuid.uuid4().hex[:8]}]"
    budget.amount_micros = int(daily_budget * 1_000_000)
    budget.delivery_method = (
        client.enums.BudgetDeliveryMethodEnum.STANDARD
    )
    budget_response = budget_service.mutate_campaign_budgets(
        customer_id=customer_id, operations=[budget_op]
    )
    budget_rn = budget_response.results[0].resource_name

    # 2. Create campaign
    campaign_service = client.get_service("CampaignService")
    campaign_op = client.get_type("CampaignOperation")
    campaign = campaign_op.create
    campaign.name = campaign_name
    campaign.status = client.enums.CampaignStatusEnum.PAUSED  # Start paused for safety
    campaign.advertising_channel_type = (
        client.enums.AdvertisingChannelTypeEnum.SEARCH
    )
    campaign.campaign_budget = budget_rn
    campaign.manual_cpc.enhanced_cpc_enabled = False  # required bidding strategy
    campaign.contains_eu_political_advertising = (
        client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    )
    campaign.network_settings.target_google_search = True
    campaign.network_settings.target_search_network = False
    campaign.network_settings.target_content_network = False

    campaign_response = campaign_service.mutate_campaigns(
        customer_id=customer_id, operations=[campaign_op]
    )
    campaign_rn = campaign_response.results[0].resource_name
    campaign_id = campaign_rn.split("/")[-1]

    # 3. Create ad group
    ag_service = client.get_service("AdGroupService")
    ag_op = client.get_type("AdGroupOperation")
    ag = ag_op.create
    ag.name = ad_group_name
    ag.campaign = campaign_rn
    ag.status = client.enums.AdGroupStatusEnum.ENABLED

    ag_response = ag_service.mutate_ad_groups(
        customer_id=customer_id, operations=[ag_op]
    )
    ag_rn = ag_response.results[0].resource_name

    # 4. Add keywords
    kw_service = client.get_service("AdGroupCriterionService")
    match_enum = {
        "EXACT": client.enums.KeywordMatchTypeEnum.EXACT,
        "PHRASE": client.enums.KeywordMatchTypeEnum.PHRASE,
        "BROAD": client.enums.KeywordMatchTypeEnum.BROAD,
    }.get(match_type.upper(), client.enums.KeywordMatchTypeEnum.PHRASE)

    kw_ops = []
    for kw in keywords:
        kw_op = client.get_type("AdGroupCriterionOperation")
        criterion = kw_op.create
        criterion.ad_group = ag_rn
        criterion.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        criterion.keyword.text = kw
        criterion.keyword.match_type = match_enum
        kw_ops.append(kw_op)

    kw_response = _mutate_keywords_with_exemptions(
        client, kw_service, customer_id, kw_ops
    )
    keywords_added = len(kw_response.results)

    return {
        "success": True,
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "campaign_resource_name": campaign_rn,
        "ad_group_resource_name": ag_rn,
        "daily_budget": daily_budget,
        "keywords_added": keywords_added,
        "note": "Campaign created in PAUSED status — enable it in Google Ads UI when ready.",
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
