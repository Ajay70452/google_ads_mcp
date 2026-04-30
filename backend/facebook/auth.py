"""Facebook Graph API auth — token + base URL."""
import os

from dotenv import load_dotenv

load_dotenv()


def graph_base() -> str:
    version = os.environ.get("META_API_VERSION", "v21.0")
    return f"https://graph.facebook.com/{version}"


def access_token() -> str:
    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN not set in environment")
    return token


def business_id() -> str:
    bid = os.environ.get("META_BUSINESS_ID")
    if not bid:
        raise RuntimeError("META_BUSINESS_ID not set in environment")
    return bid
