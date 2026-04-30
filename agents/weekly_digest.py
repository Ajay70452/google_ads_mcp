"""Agent 7 — Weekly Paid Traffic Digest (cross-platform).

Schedule: weekly, Monday at 09:45 AM UTC (after Agent 5 / Creative Ranker)
Channel:  Zoho Cliq #weekly-digest
Output:   one Cliq message per client with a plain-language summary covering
          last week vs the prior week, across BOTH Google Ads and Facebook.

Pipeline per client:
  1. Match the Google account to a Facebook ad account by name (best-effort fuzzy)
  2. Pull last-week + prior-week metrics from each platform
  3. Compute deltas (spend, clicks, CTR, conversions, CPL)
  4. Hand the structured numbers to GPT-4o-mini → 2-3 sentence plain-language summary
  5. Post one message per client to Cliq

Clients with NO activity on either platform last week are skipped silently.
"""
import json
import os
import re
from datetime import date, timedelta

from dotenv import load_dotenv
from openai import OpenAI

from agents.base import BaseAgent
from backend.facebook.reporting import get_fb_account_summary, list_fb_ad_accounts
from backend.google_ads.auth import get_google_ads_client
from backend.google_ads.reporting import get_account_summary_custom, list_child_accounts
from backend.notifications.cliq import send_cliq_alert, CHANNEL_DIGEST

load_dotenv()

CLIQ_MAX_CHARS = 4800
_MODEL = "gpt-4o-mini"


# ── Account name matching ────────────────────────────────────────────────────

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def _normalize(name: str) -> str:
    """Lowercase + strip everything except alphanumerics. Used for fuzzy match."""
    return _NORMALIZE_RE.sub("", name.lower())


def _match_fb_account(google_name: str, fb_accounts: list[dict]) -> dict | None:
    """Find the Facebook account whose name best matches a Google account name.

    Strategy: normalize both, then match on equality, prefix, or substring.
    Returns the matched FB account dict, or None if no good match.
    """
    g_norm = _normalize(google_name)
    if not g_norm:
        return None

    # Pass 1: exact normalized match
    for fb in fb_accounts:
        if _normalize(fb["name"]) == g_norm:
            return fb

    # Pass 2: one is a prefix/substring of the other (≥6 chars to avoid false positives)
    if len(g_norm) >= 6:
        for fb in fb_accounts:
            f_norm = _normalize(fb["name"])
            if len(f_norm) < 6:
                continue
            if g_norm.startswith(f_norm) or f_norm.startswith(g_norm):
                return fb
            if g_norm in f_norm or f_norm in g_norm:
                return fb

    return None


# ── Date helpers ─────────────────────────────────────────────────────────────

def _last_complete_week() -> tuple[str, str]:
    """Return (Monday, Sunday) ISO strings for the most recent COMPLETED week."""
    today = date.today()
    last_sunday = today - timedelta(days=today.weekday() + 1)
    last_monday = last_sunday - timedelta(days=6)
    return last_monday.isoformat(), last_sunday.isoformat()


def _prior_week_of(start_iso: str) -> tuple[str, str]:
    """Given a Monday ISO date, return (prior Monday, prior Sunday)."""
    monday = date.fromisoformat(start_iso)
    prior_monday = monday - timedelta(days=7)
    prior_sunday = prior_monday + timedelta(days=6)
    return prior_monday.isoformat(), prior_sunday.isoformat()


# ── Delta calculation ────────────────────────────────────────────────────────

def _pct_change(current: float, prior: float) -> float | None:
    if prior == 0:
        return None
    return (current - prior) / prior * 100.0


def _build_platform_block(
    label: str, this_week: dict, prior_week: dict
) -> dict:
    """Compute week-over-week metrics block for one platform (Google or Facebook)."""
    spend = this_week.get("spend") or this_week.get("cost") or 0
    prior_spend = prior_week.get("spend") or prior_week.get("cost") or 0
    return {
        "platform": label,
        "spend": round(float(spend), 2),
        "spend_delta_pct": _round(_pct_change(float(spend), float(prior_spend))),
        "clicks": int(this_week.get("clicks", 0) or 0),
        "clicks_delta_pct": _round(
            _pct_change(this_week.get("clicks", 0) or 0, prior_week.get("clicks", 0) or 0)
        ),
        "conversions": round(float(this_week.get("conversions", 0) or 0), 2),
        "conversions_delta_pct": _round(_pct_change(
            float(this_week.get("conversions", 0) or 0),
            float(prior_week.get("conversions", 0) or 0),
        )),
        "ctr": round(float(this_week.get("ctr", 0) or 0), 2),
    }


def _round(value: float | None) -> float | None:
    return round(value, 1) if value is not None else None


# ── OpenAI summarization ─────────────────────────────────────────────────────

def _generate_summary(client_name: str, week_label: str, platforms: list[dict]) -> str:
    """Ask GPT for a 2-3 sentence plain-language digest covering all platforms."""
    payload = {"client": client_name, "week": week_label, "platforms": platforms}
    prompt = f"""You are summarizing a dental clinic's paid traffic performance for the MethodPro internal team.

Data for {client_name} (week of {week_label}):
{json.dumps(payload, indent=2)}

Write a 2-3 sentence summary in plain English covering:
- One-line overall status (healthy / concerning / mixed)
- The 1-2 most material week-over-week changes across platforms
- Anything needing attention this week (skip if nothing notable)

Keep it tight, specific, and grounded in the numbers. Do not list every metric.
Use platform names "Google Ads" and "Facebook" where relevant.
Format: plain text, no markdown headers, no bullet points."""

    api = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    response = api.chat.completions.create(
        model=_MODEL,
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


# ── Per-client message formatting ────────────────────────────────────────────

def _format_client_message(
    client_name: str,
    week_label: str,
    summary: str,
    platforms: list[dict],
) -> str:
    lines = [
        f"*{client_name} — Weekly Digest*",
        f"_Week of {week_label}_",
        "",
        summary,
        "",
    ]
    for p in platforms:
        delta_str = _format_delta(p["spend_delta_pct"])
        conv_delta = _format_delta(p["conversions_delta_pct"])
        lines.append(
            f"   • {p['platform']}: ${p['spend']:,.2f} spend ({delta_str}) | "
            f"{p['clicks']:,} clicks | "
            f"{p['conversions']:.1f} conv ({conv_delta}) | "
            f"CTR {p['ctr']:.2f}%"
        )
    return "\n".join(lines)


def _format_delta(pct: float | None) -> str:
    if pct is None:
        return "n/a"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}% WoW"


# ── Main agent ───────────────────────────────────────────────────────────────

class WeeklyDigest(BaseAgent):
    def run(self) -> None:
        ga_client = get_google_ads_client()
        google_accounts = list_child_accounts(ga_client)
        fb_accounts = list_fb_ad_accounts()

        this_start, this_end = _last_complete_week()
        prior_start, prior_end = _prior_week_of(this_start)
        week_label = f"{this_start} → {this_end}"

        sent_count = 0
        skipped = 0
        unmatched = 0

        for ga_account in google_accounts:
            cid = ga_account["customer_id"]
            name = ga_account["name"]

            # Pull Google week data
            try:
                google_this = get_account_summary_custom(ga_client, cid, this_start, this_end)
                google_prior = get_account_summary_custom(ga_client, cid, prior_start, prior_end)
            except Exception as exc:
                self.logger.warning("Skipping %s — Google fetch failed: %s", name, exc)
                continue

            google_block = _build_platform_block("Google Ads", google_this, google_prior)

            # Match + pull Facebook week data (optional; some clients are Google-only)
            fb_match = _match_fb_account(name, fb_accounts)
            fb_block = None
            if fb_match:
                try:
                    fb_this = get_fb_account_summary(
                        fb_match["ad_account_id"], this_start, this_end
                    )
                    fb_prior = get_fb_account_summary(
                        fb_match["ad_account_id"], prior_start, prior_end
                    )
                    fb_block = _build_platform_block("Facebook", fb_this, fb_prior)
                except Exception as exc:
                    self.logger.warning(
                        "FB fetch failed for %s (%s): %s",
                        name, fb_match["ad_account_id"], exc,
                    )
            else:
                unmatched += 1

            # Skip clients with zero activity on every platform
            platforms = [google_block] + ([fb_block] if fb_block else [])
            total_spend = sum(p["spend"] for p in platforms)
            if total_spend == 0:
                self.logger.info("%s — no spend last week, skipping", name)
                skipped += 1
                continue

            # Generate summary + post
            try:
                summary = _generate_summary(name, week_label, platforms)
            except Exception as exc:
                self.logger.warning("Summary failed for %s: %s", name, exc)
                summary = "(AI summary unavailable — see metrics below.)"

            message = _format_client_message(name, week_label, summary, platforms)
            if len(message) > CLIQ_MAX_CHARS:
                message = message[:CLIQ_MAX_CHARS - 30] + "\n\n_...truncated_"

            if not send_cliq_alert(message, CHANNEL_DIGEST):
                self.logger.error("Failed to send Cliq message for %s", name)
                continue

            sent_count += 1
            self.logger.info(
                "%s — sent (%s)",
                name, "Google + FB" if fb_block else "Google only",
            )

        self.logger.info(
            "Done — %d digests sent, %d skipped (no spend), %d unmatched on FB",
            sent_count, skipped, unmatched,
        )
