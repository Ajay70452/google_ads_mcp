"""Zoho Cliq notifier using webhook token (zapikey)."""
import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_COMPANY_ID = os.environ.get("CLIQ_COMPANY_ID", "746931876")
_BASE = f"https://cliq.zoho.com/company/{_COMPANY_ID}/api/v2/channelsbyname"

CHANNEL_PACING = "pacingalerts"
CHANNEL_PERFORMANCE = "performancealerts"
CHANNEL_SEARCH_TERMS = "searchtermsreview"


def send_cliq_alert(message: str, channel: str) -> bool:
    """POST a message to a Cliq channel using the zapikey webhook token.

    Returns True on success, False on failure (never raises so agents keep running).
    """
    zapikey = os.environ.get("CLIQ_ZAPIKEY", "")
    if not zapikey:
        logger.error("CLIQ_ZAPIKEY not set in environment")
        return False

    try:
        response = httpx.post(
            f"{_BASE}/{channel}/message",
            params={"zapikey": zapikey},
            json={"text": message},
            timeout=15,
        )
        response.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        logger.error("Cliq returned %s: %s", e.response.status_code, e.response.text)
        return False
    except httpx.HTTPError as e:
        logger.error("Cliq request failed: %s", e)
        return False
