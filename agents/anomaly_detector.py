"""Agent 2 — Performance Anomaly Detector.

Schedule: weekly, Monday at 8:00 AM
Channel:  Zoho Cliq #performance-alerts
Trigger:  CPC, CTR, or conversion rate more than 20% outside the trailing 4-week average
"""
import os
from datetime import date, timedelta

from dotenv import load_dotenv

from agents.base import BaseAgent
from backend.google_ads.auth import get_google_ads_client
from backend.google_ads.reporting import get_account_summary_custom, list_child_accounts
from backend.notifications.cliq import send_cliq_alert, CHANNEL_PERFORMANCE

load_dotenv()

ANOMALY_THRESHOLD = 0.20  # 20% deviation triggers an alert
CLIQ_MAX_CHARS = 4800


def _week_bounds(weeks_ago: int) -> tuple[str, str]:
    """Return (Monday, Sunday) strings for N weeks ago (0 = current week)."""
    today = date.today()
    last_monday = today - timedelta(days=today.weekday())
    week_start = last_monday - timedelta(weeks=weeks_ago)
    week_end = week_start + timedelta(days=6)
    return week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d")


def _safe_avg(values: list[float]) -> float:
    non_zero = [v for v in values if v > 0]
    return sum(non_zero) / len(non_zero) if non_zero else 0.0


def _check_deviation(
    current: float,
    average: float,
    label: str,
    unit: str = "",
) -> str | None:
    """Return a formatted flag string if deviation exceeds threshold, else None."""
    if average == 0 or current == 0:
        return None
    deviation = (current - average) / average
    if abs(deviation) <= ANOMALY_THRESHOLD:
        return None
    direction = "up" if deviation > 0 else "down"
    emoji = "🔴" if abs(deviation) > 0.40 else "🟡"
    return (
        f"   {emoji} {label}: {unit}{current:.2f} vs {unit}{average:.2f} avg "
        f"({'+' if deviation > 0 else ''}{deviation * 100:.0f}% {direction})"
    )


def _chunk_blocks(header: str, blocks: list[str], max_chars: int) -> list[str]:
    """Split alert blocks into multiple messages that fit within Cliq's char limit."""
    chunks = []
    current = header
    for block in blocks:
        piece = block + "\n\n"
        if len(current) + len(piece) > max_chars:
            chunks.append(current.rstrip())
            current = "*...continued*\n\n" + piece
        else:
            current += piece
    if current.strip():
        chunks.append(current.rstrip())
    return chunks


class AnomalyDetector(BaseAgent):
    def run(self) -> None:
        client = get_google_ads_client()
        accounts = list_child_accounts(client)
        today = date.today()

        alert_blocks: list[tuple[str, int]] = []  # (message_block, severity_count)

        for account in accounts:
            cid = account["customer_id"]
            name = account["name"]

            # Fetch the trailing 4 completed weeks (weeks 1–4 ago, oldest first)
            history = []
            for w in range(4, 0, -1):
                start, end = _week_bounds(w)
                metrics = get_account_summary_custom(client, cid, start, end)
                history.append(metrics)

            this_start, this_end = _week_bounds(0)
            this_week = get_account_summary_custom(client, cid, this_start, this_end)

            # Skip accounts with no activity at all
            if this_week["clicks"] == 0 and all(w["clicks"] == 0 for w in history):
                self.logger.info("%s — no activity, skipping", name)
                continue

            avg_cpc = _safe_avg([w["cpc"] for w in history])
            avg_ctr = _safe_avg([w["ctr"] for w in history])
            avg_conv_rate = _safe_avg([w["conv_rate"] for w in history])

            flags = []
            for result in [
                _check_deviation(this_week["cpc"], avg_cpc, "CPC", "$"),
                _check_deviation(this_week["ctr"], avg_ctr, "CTR"),
                _check_deviation(this_week["conv_rate"], avg_conv_rate, "Conv Rate"),
            ]:
                if result:
                    flags.append(result)

            if not flags:
                continue

            block = (
                f"*{name}* (week of {this_start})\n"
                + "\n".join(flags)
            )
            alert_blocks.append((block, len(flags)))

        if not alert_blocks:
            self.logger.info("No anomalies detected — no alert sent")
            return

        # Sort by severity (most flags first)
        alert_blocks.sort(key=lambda x: x[1], reverse=True)

        header = (
            f"*Performance Anomaly Report — {today.strftime('%B %d, %Y')}*\n"
            f"{len(alert_blocks)} account(s) with metrics >20% from 4-week average:\n\n"
        )
        block_texts = [block for block, _ in alert_blocks]
        chunks = _chunk_blocks(header, block_texts, CLIQ_MAX_CHARS)
        success = all(send_cliq_alert(chunk, CHANNEL_PERFORMANCE) for chunk in chunks)

        if success:
            self.logger.info(
                "Alert sent — %d account(s) flagged across %d message(s)",
                len(alert_blocks), len(chunks),
            )
        else:
            raise RuntimeError("One or more Cliq messages failed to send")
