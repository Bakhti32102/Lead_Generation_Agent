"""
Google Sheets OAuth Authentication.

Opens the browser for Google authorization and stores the refresh token locally.

Usage:
    python -m app.auth_sheets

Prerequisites:
    GOOGLE_AUTH_MODE=oauth
    GOOGLE_CLIENT_ID=<your-client-id>
    GOOGLE_CLIENT_SECRET=<your-client-secret>
    GOOGLE_SHEET_ID=<your-spreadsheet-id>
"""

from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

from app.config.settings import settings, PROJECT_ROOT

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def authenticate() -> bool:
    """Run the OAuth flow: open browser → authorize → store token."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    cfg = settings.google_sheets

    if not cfg.client_id or not cfg.client_secret:
        print("ERROR: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env")
        return False

    if not cfg.sheet_id:
        print("ERROR: GOOGLE_SHEET_ID must be set in .env")
        return False

    # Build the client config for the OAuth flow
    client_config = {
        "installed": {
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print("=" * 60)
    print("Google Sheets OAuth Authentication")
    print("=" * 60)
    print()
    print(f"Sheet ID:  {cfg.sheet_id}")
    print(f"Worksheet: {cfg.worksheet_name}")
    print()

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)

    print("Opening browser for Google authorization...")
    print("If the browser doesn't open, copy the URL below and open it manually.")
    print()

    # Use run_console for headless/manual auth, or run_local_server for automatic
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
    token_path = cfg.token_path
    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes or SCOPES),
    }

    with open(token_path, "w") as f:
        json.dump(token_data, f, indent=2)

    print()
    print(f"Token saved to: {token_path}")
    print()
    print("Verifying connection...")

    # Test: read the sheet
    try:
        from googleapiclient.discovery import build

        service = build("sheets", "v4", credentials=creds)
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=cfg.sheet_id, range=f"{cfg.worksheet_name}!A1:Z1")
            .execute()
        )
        headers = result.get("values", [[]])[0]
        if headers:
            print(f"Sheet verified. Headers found: {len(headers)} columns")
            print(f"First 5 headers: {headers[:5]}")
        else:
            print("Sheet is empty (no headers found). This is OK — headers will be created on first write.")
        print()
        print("AUTHENTICATION SUCCESSFUL")
        return True
    except Exception as e:
        print(f"WARNING: Token saved but sheet read failed: {e}")
        print("This may be normal if the sheet doesn't exist yet or sharing isn't set up.")
        print("AUTHENTICATION COMPLETE (verify sheet sharing separately)")
        return True


def main():
    success = authenticate()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
