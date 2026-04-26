"""
Generate a new Google Ads OAuth refresh token.

Run this script whenever the refresh token in .env expires (every 7 days for
OAuth apps in Testing mode; indefinitely for Published apps).

Usage:
    python scripts/generate_refresh_token.py

It will open a browser window, ask you to log in with the Google account that
has access to the MCC, and then print the new refresh token to paste into .env.
"""

import os
import webbrowser
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/adwords"]

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]

# Force Brave instead of the system default browser
brave_path = (
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    if os.path.exists(r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe")
    else r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe"
)
webbrowser.register("brave", None, webbrowser.BackgroundBrowser(brave_path))

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

print("\nOpening Brave for Google OAuth login...")
print("Log in with the Google account that has access to your MCC.\n")

credentials = flow.run_local_server(
    port=8080,
    prompt="consent",
    access_type="offline",
    browser="brave",
)

print("\n" + "=" * 60)
print("SUCCESS — copy this into your .env file:")
print("=" * 60)
print(f"\nREFRESH_TOKEN={credentials.refresh_token}\n")
print("=" * 60)
print("\nThen restart the backend server (save any file to trigger reload).")
