"""Agent 1 — Budget Pacing Monitor.

Schedule: daily at 8:00 AM
Channel:  Zoho Cliq #pacing-alerts
Trigger:  any campaign 15%+ off expected pace (pacing_pct < 85 or > 115)
"""
import os
from calendar import monthrange
from datetime import date

import httpx
from dotenv import load_dotenv

from agents.base import BaseAgent
from backend.notifications.cliq import send_cliq_alert, CHANNEL_PACING

load_dotenv()

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8001")
CLIQ_MAX_CHARS = 4800


def _format_campaign_alert(account_name: str, campaign: dict, days_elapsed: int, days_in_month: int) -> str:
    pct = campaign["pacing_pct"]
    deviation = pct - 100
    direction = "over" if deviation > 0 else "under"
    emoji = "🚨" if abs(deviation) >= 30 else "⚠️"
    return (
        f"{emoji} *{account_name}* — {campaign['campaign_name']}\n"
        f"   Day {days_elapsed}/{days_in_month} | "
        f"${campaign['daily_budget']:,.0f}/day budget | "
        f"MTD: ${campaign['spend_mtd']:,.2f} | "
        f"Projected: ${campaign['projected_spend']:,.2f} | "
        f"{abs(deviation):.0f}% {direction} pace"
    )


def _chunk_alerts(header: str, alerts: list[str], max_chars: int) -> list[str]:
    """Split alerts into multiple messages that fit within Cliq's char limit."""
    chunks = []
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


class BudgetPacingMonitor(BaseAgent):
    def run(self) -> None:
        today = date.today()
        days_elapsed = today.day
        days_in_month = monthrange(today.year, today.month)[1]

        response = httpx.get(
            f"{BACKEND_URL}/budget-pacing/all",
            params={"refresh": "true"},
            timeout=120,
        )
        response.raise_for_status()
        accounts = response.json()

        alerts = []
        for account in accounts:
            account_name = account["account_name"]
            for campaign in account.get("campaigns", []):
                if campaign["status"] == "ON_TRACK":
                    continue
                alerts.append(
                    _format_campaign_alert(account_name, campaign, days_elapsed, days_in_month)
                )

        if not alerts:
            self.logger.info("All campaigns on track — no alert sent")
            return

        header = (
            f"*Budget Pacing Alert — {today.strftime('%A, %B %d, %Y')}*\n"
            f"{len(alerts)} campaign(s) off pace:\n\n"
        )

        chunks = _chunk_alerts(header, alerts, CLIQ_MAX_CHARS)
        success = all(send_cliq_alert(chunk, CHANNEL_PACING) for chunk in chunks)

        if success:
            self.logger.info(
                "Alert sent — %d campaign(s) flagged across %d message(s)",
                len(alerts), len(chunks),
            )
        else:
            raise RuntimeError("One or more Cliq messages failed to send")
