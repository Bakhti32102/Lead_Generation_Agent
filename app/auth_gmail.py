"""
Gmail OAuth Authentication.

Opens the browser for Google authorization and stores the Gmail send token locally.

Usage:
    python -m app.auth_gmail

Prerequisites:
    GOOGLE_AUTH_MODE=oauth
    GOOGLE_CLIENT_ID=<your-client-id>
    GOOGLE_CLIENT_SECRET=<your-client-secret>
    EMAIL_FROM=<your-gmail-address>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app.config.settings import settings, PROJECT_ROOT

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def authenticate() -> bool:
    """Run the OAuth flow: open browser → authorize → store token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    gs_cfg = settings.google_sheets
    email_cfg = settings.email

    if not gs_cfg.client_id or not gs_cfg.client_secret:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")
        return False

    if not email_cfg.from_address:
        print("ERROR: EMAIL_FROM must be set in .env (your Gmail address)")
        return False

    # Gmail token file — separate from Google Sheets token (different scopes)
    gmail_token_path = Path(gs_cfg.token_path).parent / "gmail_token.json"

    print("=" * 60)
    print("Gmail OAuth Authentication")
    print("=" * 60)
    print()
    print(f"Email: {email_cfg.from_address}")
    print(f"Scopes: {', '.join(SCOPES)}")
    print()

    # Build the client config for the OAuth flow
    client_config = {
        "installed": {
            "client_id": gs_cfg.client_id,
            "client_secret": gs_cfg.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    print("Opening browser for Google authorization...")
    print("If the browser doesn't open, copy the URL below and open it manually.")
    print()

    try:
        creds = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
        )
    except Exception:
        print("Local server failed. Trying console flow...")
        creds = flow.run_console()

    # Save the token
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }

    with open(gmail_token_path, "w") as f:
        json.dump(token_data, f, indent=2)

    print()
    print(f"Token saved to: {gmail_token_path}")

    # Verify: try to build Gmail service
    print()
    print("Verifying Gmail API connection...")
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        print(f"Gmail account: {profile.get('emailAddress', 'unknown')}")
        print()
        print("AUTHENTICATION SUCCESSFUL")
        return True
    except Exception as e:
        print(f"WARNING: Token saved but Gmail API verification failed: {e}")
        print("This may be normal — verify the Gmail API is enabled in Google Cloud Console.")
        print("AUTHENTICATION COMPLETE (verify API enablement separately)")
        return True


def main():
    success = authenticate()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
