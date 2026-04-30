"""Agent 4 — Ad Fatigue Monitor (Facebook).

Schedule: every 3 days at 8:00 AM UTC
Channel:  Zoho Cliq #fatigue-alerts
Trigger:  any active ad set with frequency above the threshold for its objective
          - awareness/reach/video_views   → frequency > 7.0
          - conversions/lead/purchase     → frequency > 3.5
          - everything else (default)     → frequency > 5.0

Posts a single message listing all flagged ad sets across all accounts, sorted
by severity. Skips silently when nothing is over threshold.
"""
from datetime import date

from dotenv import load_dotenv

from agents.base import BaseAgent
from backend.facebook.reporting import get_adset_frequency, list_fb_ad_accounts
from backend.notifications.cliq import send_cliq_alert, CHANNEL_FATIGUE

load_dotenv()

CLIQ_MAX_CHARS = 4800

# Frequency thresholds per Facebook campaign objective.
# Awareness-type objectives tolerate higher frequency; conversion campaigns do not.
AWARENESS_OBJECTIVES = {
    "OUTCOME_AWARENESS",
    "BRAND_AWARENESS",
    "REACH",
    "VIDEO_VIEWS",
    "OUTCOME_ENGAGEMENT",
    "POST_ENGAGEMENT",
    "PAGE_LIKES",
}
CONVERSION_OBJECTIVES = {
    "OUTCOME_LEADS",
    "OUTCOME_SALES",
    "CONVERSIONS",
    "LEAD_GENERATION",
    "PRODUCT_CATALOG_SALES",
    "MESSAGES",
    "APP_INSTALLS",
}

THRESHOLD_AWARENESS = 7.0
THRESHOLD_CONVERSION = 3.5
THRESHOLD_DEFAULT = 5.0


def _threshold_for_objective(objective: str) -> float:
    if objective in AWARENESS_OBJECTIVES:
        return THRESHOLD_AWARENESS
    if objective in CONVERSION_OBJECTIVES:
        return THRESHOLD_CONVERSION
    return THRESHOLD_DEFAULT


def _format_alert(account_name: str, adset: dict, threshold: float) -> str:
    freq = adset["frequency"]
    over_by = freq - threshold
    severe = freq > threshold * 1.5
    emoji = "🚨" if severe else "⚠️"
    return (
        f"{emoji} *{account_name}* — {adset['adset_name']}\n"
        f"   Frequency: {freq:.2f} (threshold {threshold:.1f}, +{over_by:.2f}) | "
        f"Objective: {adset['campaign_objective']} | "
        f"Impr: {adset['impressions']:,} | "
        f"Reach: {adset['reach']:,} | "
        f"Spend: ${adset['spend']:,.2f}"
    )


def _chunk(header: str, alerts: list[str], max_chars: int) -> list[str]:
    chunks: list[str] = []
    current = header
    for alert in alerts:
        block = alert + "\n\n"
        if len(current) + len(block) > max_chars:
            chunks.append(current.rstrip())
            current = "*...continued*\n\n" + block
        else:
            current += block
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


class AdFatigueMonitor(BaseAgent):
    def run(self) -> None:
        accounts = list_fb_ad_accounts()
        today = date.today()

        flagged: list[tuple[str, float]] = []  # (formatted_alert, severity_score)

        for account in accounts:
            ad_account_id = account["ad_account_id"]
            account_name = account["name"]

            try:
                adsets = get_adset_frequency(ad_account_id, days=3)
            except Exception as exc:
                self.logger.warning(
                    "Skipping %s — Graph API error: %s", account_name, exc
                )
                continue

            for adset in adsets:
                threshold = _threshold_for_objective(adset["campaign_objective"])
                if adset["frequency"] <= threshold:
                    continue
                severity = adset["frequency"] - threshold
                flagged.append(
                    (_format_alert(account_name, adset, threshold), severity)
                )

        if not flagged:
            self.logger.info("No ad sets over fatigue threshold — no alert sent")
            return

        # Sort by severity (most over threshold first)
        flagged.sort(key=lambda x: x[1], reverse=True)
        alerts = [a for a, _ in flagged]

        header = (
            f"*Facebook Ad Fatigue Report — {today.strftime('%A, %B %d, %Y')}*\n"
            f"{len(alerts)} ad set(s) over fatigue threshold:\n\n"
        )

        chunks = _chunk(header, alerts, CLIQ_MAX_CHARS)
        success = all(send_cliq_alert(c, CHANNEL_FATIGUE) for c in chunks)

        if success:
            self.logger.info(
                "Alert sent — %d ad set(s) flagged across %d message(s)",
                len(alerts), len(chunks),
            )
        else:
            raise RuntimeError("One or more Cliq messages failed to send")
