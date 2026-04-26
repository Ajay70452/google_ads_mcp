import os
from functools import lru_cache
from google.ads.googleads.client import GoogleAdsClient
from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_google_ads_client() -> GoogleAdsClient:
    credentials = {
        "developer_token": os.environ["DEVELOPER_TOKEN"],
        "client_id": os.environ["CLIENT_ID"],
        "client_secret": os.environ["CLIENT_SECRET"],
        "refresh_token": os.environ["REFRESH_TOKEN"],
        "login_customer_id": os.environ["MCC_CUSTOMER_ID"],
        "use_proto_plus": True,
    }
    return GoogleAdsClient.load_from_dict(credentials)


def list_accessible_customers() -> list[str]:
    """Validate MCC access by listing all child account customer IDs."""
    client = get_google_ads_client()
    customer_service = client.get_service("CustomerService")
    response = customer_service.list_accessible_customers()
    return list(response.resource_names)
