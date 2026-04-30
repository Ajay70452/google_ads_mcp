"""Agent 5 — Creative Performance Ranker (Facebook).

Schedule: weekly, Monday at 09:30 AM UTC (after the Google search-terms agent)
Channel:  Zoho Cliq #creative-performance
Output:   one message per account listing top 5 + bottom 3 ads ranked by CTR,
          with cost-per-result attached when available.

Skips accounts with no active ads. Skips accounts where every active ad has
zero spend in the trailing 7 days.
"""
from datetime import date

from dotenv import load_dotenv

from agents.base import BaseAgent
from backend.facebook.reporting import get_creative_performance, list_fb_ad_accounts
from backend.notifications.cliq import send_cliq_alert, CHANNEL_CREATIVE

load_dotenv()

CLIQ_MAX_CHARS = 4800
TOP_N = 5
BOTTOM_N = 3
MIN_IMPRESSIONS = 500  # skip ads with too little data to rank meaningfully


def _format_ad_row(ad: dict, rank: int) -> str:
    cpr = ad["cost_per_result"]
    cpr_str = f"${cpr:,.2f}" if cpr is not None else "—"
    name = ad["ad_name"][:50]
    return (
        f"   {rank}. {name}\n"
        f"      CTR {ad['ctr']:.2f}% | "
        f"Impr {ad['impressions']:,} | "
        f"Clicks {ad['clicks']:,} | "
        f"Spend ${ad['spend']:,.2f} | "
        f"CPR {cpr_str}"
    )


class CreativePerformanceRanker(BaseAgent):
    def run(self) -> None:
        accounts = list_fb_ad_accounts()
        today = date.today()
        sent_count = 0

        for account in accounts:
            ad_account_id = account["ad_account_id"]
            account_name = account["name"]

            try:
                ads = get_creative_performance(ad_account_id, days=7)
            except Exception as exc:
                self.logger.warning(
                    "Skipping %s — Graph API error: %s", account_name, exc
                )
                continue

            # Filter ads with enough impressions to rank
            ranked = [a for a in ads if a["impressions"] >= MIN_IMPRESSIONS]
            if not ranked:
                self.logger.info(
                    "%s — no ads meet min impressions (%d), skipping",
                    account_name, MIN_IMPRESSIONS,
                )
                continue

            # ads is already sorted by CTR desc from reporting layer
            top = ranked[:TOP_N]
            bottom = ranked[-BOTTOM_N:] if len(ranked) > TOP_N + BOTTOM_N else []

            lines = [
                f"*Creative Performance — {account_name}*",
                f"_Week ending {today.strftime('%b %d, %Y')} | {len(ranked)} ads ranked_",
                "",
                f"*Top {len(top)} by CTR:*",
            ]
            for i, ad in enumerate(top, 1):
                lines.append(_format_ad_row(ad, i))

            if bottom:
                lines.append("")
                lines.append(f"*Bottom {len(bottom)} by CTR (review or pause):*")
                for i, ad in enumerate(bottom, 1):
                    lines.append(_format_ad_row(ad, i))

            message = "\n".join(lines)
            if len(message) > CLIQ_MAX_CHARS:
                message = message[:CLIQ_MAX_CHARS - 30] + "\n\n_...truncated_"

            if not send_cliq_alert(message, CHANNEL_CREATIVE):
                self.logger.error("Failed to send Cliq message for %s", account_name)
                continue

            sent_count += 1
            self.logger.info(
                "%s — sent (%d ads ranked)", account_name, len(ranked)
            )

        self.logger.info("Done — %d account message(s) sent", sent_count)
