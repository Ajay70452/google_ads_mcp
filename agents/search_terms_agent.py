"""Agent 3 — Search Terms Flagging Agent.

Schedule: weekly, Monday at 9:00 AM (after Agent 2)
Channel:  Zoho Cliq #search-terms-review
Output:   one Cliq message per account with AI-identified irrelevant terms to add as negatives
"""
from dotenv import load_dotenv

from agents.base import BaseAgent
from backend.google_ads.auth import get_google_ads_client
from backend.google_ads.reporting import get_search_term_report, list_child_accounts
from backend.google_ads.search_term_classifier import classify_search_terms
from backend.notifications.cliq import send_cliq_alert, CHANNEL_SEARCH_TERMS

load_dotenv()

MIN_IMPRESSIONS = 5  # lower than MCP tool default to catch more terms in weekly runs
CLIQ_MAX_CHARS = 4800


class SearchTermsAgent(BaseAgent):
    def run(self) -> None:
        client = get_google_ads_client()
        accounts = list_child_accounts(client)

        sent_count = 0

        for account in accounts:
            cid = account["customer_id"]
            name = account["name"]

            # Fetch last 7 days of search terms
            try:
                data = get_search_term_report(
                    client, cid, "LAST_7_DAYS", None, MIN_IMPRESSIONS
                )
            except Exception as exc:
                self.logger.warning("Skipping %s — query failed: %s", name, exc)
                continue

            terms = data.get("terms", [])
            if not terms:
                self.logger.info("%s — no terms this week, skipping", name)
                continue

            # AI classification via Claude
            try:
                ai_flagged = classify_search_terms(terms, name)
            except Exception as exc:
                self.logger.warning("Claude classifier failed for %s: %s", name, exc)
                ai_flagged = []

            # Rule-based suggestions from reporting.py (spend > $5, 0 conversions)
            rule_based = data.get("suggested_negatives", [])

            if not ai_flagged and not rule_based:
                self.logger.info("%s — nothing to flag, skipping", name)
                continue

            # Build per-account message
            lines = [
                f"*Search Terms Review — {name}*",
                f"_{len(terms)} terms reviewed | LAST_7_DAYS_",
            ]

            if ai_flagged:
                high = [f for f in ai_flagged if f["priority"] == "HIGH"]
                med = [f for f in ai_flagged if f["priority"] == "MEDIUM"]
                low = [f for f in ai_flagged if f["priority"] == "LOW"]

                lines.append(f"\n*AI-Identified Negatives ({len(ai_flagged)} terms):*")
                for group, emoji in [(high, "🔴"), (med, "🟡"), (low, "🟢")]:
                    for item in group:
                        lines.append(f'   {emoji} "{item["term"]}" — {item["reason"]}')

            if rule_based:
                lines.append(
                    f"\n*High-Spend / Zero-Conversion ({len(rule_based)} terms):*"
                )
                for term in rule_based[:15]:  # cap to keep message readable
                    lines.append(f'   • "{term}"')
                if len(rule_based) > 15:
                    lines.append(f"   ... and {len(rule_based) - 15} more")

            message = "\n".join(lines)

            # Truncate if over Cliq limit (single-account messages should rarely hit this)
            if len(message) > CLIQ_MAX_CHARS:
                message = message[:CLIQ_MAX_CHARS - 30] + "\n\n_...truncated_"

            if not send_cliq_alert(message, CHANNEL_SEARCH_TERMS):
                self.logger.error("Failed to send Cliq message for %s", name)

            sent_count += 1
            self.logger.info(
                "%s — sent (%d AI-flagged, %d rule-based)", name, len(ai_flagged), len(rule_based)
            )

        self.logger.info("Done — %d account message(s) sent", sent_count)
