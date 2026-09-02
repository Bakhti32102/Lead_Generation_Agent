"""
Google Sheets integration.
Uses the official Google Sheets API via service account or OAuth.
Acts as the primary human-readable CRM.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config.settings import settings, PROJECT_ROOT

logger = logging.getLogger(__name__)

# Column order — matches the specification
SHEET_COLUMNS = [
    "Lead ID",
    "Date Found",
    "Business Name",
    "Business Category",
    "Country",
    "City",
    "Address",
    "Phone",
    "Email",
    "Website",
    "Google Maps URL",
    "Source",
    "Source URL",
    "Posted Date",
    "Requirement",
    "Business Research",
    "Potential Problem",
    "Recommended Service",
    "Recommended AI Solution",
    "Lead Score",
    "Contact Channel",
    "Initial Message",
    "Initial Contact Date",
    "Initial Contact Status",
    "Follow-up 3 Day",
    "Follow-up 7 Day",
    "Response",
    "Response Category",
    "Follow-up Status",
    "Do Not Contact",
    "Human Required",
    "Notes",
]


class GoogleSheetsClient:
    """Wrapper around the Google Sheets API."""

    def __init__(self):
        self._service = None
        self._sheet_id = settings.google_sheets.sheet_id
        self._worksheet = settings.google_sheets.worksheet_name
        self._credentials_path = settings.google_sheets.credentials_path

    @property
    def is_configured(self) -> bool:
        return settings.google_sheets.is_configured

    def _get_service(self):
        """Lazy-init the Sheets API service."""
        if self._service is not None:
            return self._service

        if not self.is_configured:
            raise RuntimeError(
                "Google Sheets API is not configured. "
                "Set GOOGLE_SHEET_ID and configure auth (OAuth or service account)."
            )

        from googleapiclient.discovery import build

        creds = self._get_credentials()
        self._service = build("sheets", "v4", credentials=creds)
        return self._service

    def _get_credentials(self):
        """Get credentials based on auth mode (OAuth or service account)."""
        auth_mode = settings.google_sheets.auth_mode.lower()

        if auth_mode == "oauth":
            return self._get_oauth_credentials()
        else:
            return self._get_service_account_credentials()

    def _get_oauth_credentials(self):
        """Get OAuth2 credentials. Refreshes token if expired."""
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        token_path = settings.google_sheets.token_path

        if not token_path.exists():
            raise FileNotFoundError(
                f"OAuth token file not found: {token_path}\n"
                f"Run: python -m app.auth_sheets"
            )

        creds = Credentials.from_authorized_user_file(
            str(token_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )

        # Refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(token_path, "w") as f:
                json.dump({
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": list(creds.scopes or []),
                }, f)
            logger.info("OAuth token refreshed.")

        return creds

    def _get_service_account_credentials(self):
        """Get service account credentials."""
        from google.oauth2.service_account import Credentials

        return Credentials.from_service_account_file(
            str(self._credentials_path),
            scopes=["https://www.googleapis.com/auth/spreadsheets"],
        )

    def _get_range(self, range_str: str) -> str:
        """Return the A1 notation with worksheet name."""
        return f"{self._worksheet}!{range_str}"

    # ---- Read ----

    def read_all_rows(self) -> List[Dict[str, str]]:
        """Read all rows from the worksheet. Returns list of dicts keyed by column."""
        if not self.is_configured:
            return []
        service = self._get_service()
        try:
            result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._sheet_id,
                    range=self._get_range("A:AG"),
                )
                .execute()
            )
            values = result.get("values", [])
            if len(values) < 2:
                return []

            headers = values[0]
            rows = []
            for row in values[1:]:
                # Pad row to match header length
                padded = row + [""] * (len(headers) - len(row))
                row_dict = dict(zip(headers, padded[: len(headers)]))
                rows.append(row_dict)
            return rows
        except Exception as e:
            logger.error(f"Failed to read Google Sheet: {e}")
            return []

    def find_row_by_lead_id(self, lead_id: str) -> Optional[int]:
        """Find the row number (1-indexed, including header) for a given Lead ID."""
        rows = self.read_all_rows()
        for i, row in enumerate(rows, start=2):  # row 1 is header
            if row.get("Lead ID") == lead_id:
                return i
        return None

    def find_row_by_business_name(self, business_name: str) -> Optional[int]:
        """Find row number by business name (case-insensitive partial match)."""
        rows = self.read_all_rows()
        for i, row in enumerate(rows, start=2):
            name = row.get("Business Name", "")
            if name.lower() == business_name.lower():
                return i
        return None

    # ---- Write ----

    def _ensure_headers(self) -> None:
        """Make sure the header row exists and matches expected columns."""
        service = self._get_service()
        try:
            result = (
                service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=self._sheet_id,
                    range=self._get_range("A1:AG1"),
                )
                .execute()
            )
            existing = result.get("values", [[]])[0]
            if not existing or existing != SHEET_COLUMNS:
                service.spreadsheets().values().update(
                    spreadsheetId=self._sheet_id,
                    range=self._get_range("A1"),
                    valueInputOption="RAW",
                    body={"values": [SHEET_COLUMNS]},
                ).execute()
                logger.info("Google Sheets headers updated.")
        except Exception as e:
            logger.warning(f"Could not verify/update headers: {e}")

    def append_lead(self, lead_data: Dict[str, str]) -> int:
        """
        Append a single lead row. Returns the row number.
        lead_data keys should match SHEET_COLUMNS names.
        """
        service = self._get_service()
        self._ensure_headers()

        row_values = [lead_data.get(col, "") for col in SHEET_COLUMNS]
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=self._sheet_id,
                range=self._get_range("A1"),
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": [row_values]},
            )
            .execute()
        )
        updated_range = result.get("updates", {}).get("updatedRange", "")
        # Parse the row number from updated range like "Sheet1!A17:AG17"
        row_num = 0
        if "!" in updated_range:
            part = updated_range.split("!")[-1]
            row_start = part.split(":")[0]
            row_num = int("".join(c for c in row_start if c.isdigit()))
        logger.info(f"Appended lead at row {row_num}")
        return row_num

    def update_cell(self, row_number: int, column: str, value: str) -> None:
        """Update a single cell by row number and column name."""
        service = self._get_service()
        col_idx = SHEET_COLUMNS.index(column) if column in SHEET_COLUMNS else -1
        if col_idx < 0:
            logger.warning(f"Unknown column: {column}")
            return

        col_letter = self._col_index_to_letter(col_idx)
        cell_range = f"{self._get_range(f'{col_letter}{row_number}')}"
        service.spreadsheets().values().update(
            spreadsheetId=self._sheet_id,
            range=cell_range,
            valueInputOption="RAW",
            body={"values": [[value]]},
        ).execute()

    def update_lead_row(self, row_number: int, updates: Dict[str, str]) -> None:
        """Update multiple cells in a row by column names."""
        for column, value in updates.items():
            self.update_cell(row_number, column, value)

    def update_lead_by_id(
        self, lead_id: str, updates: Dict[str, str]
    ) -> bool:
        """Find lead by ID and update. Returns True if found."""
        row_num = self.find_row_by_lead_id(lead_id)
        if row_num:
            self.update_lead_row(row_num, updates)
            return True
        return False

    # ---- Helpers ----

    @staticmethod
    def _col_index_to_letter(index: int) -> str:
        """Convert 0-based column index to Excel-style letter(s)."""
        result = ""
        while True:
            result = chr(65 + (index % 26)) + result
            index = index // 26 - 1
            if index < 0:
                break
        return result

    def lead_data_to_sheet_row(self, lead: dict) -> Dict[str, str]:
        """Convert a lead dictionary to the format expected by Google Sheets."""
        return {
            "Lead ID": str(lead.get("lead_id", "")),
            "Date Found": str(lead.get("date_found", "")),
            "Business Name": lead.get("business_name", ""),
            "Business Category": lead.get("business_category", ""),
            "Country": lead.get("country", ""),
            "City": lead.get("city", ""),
            "Address": lead.get("address", ""),
            "Phone": lead.get("phone", ""),
            "Email": lead.get("email", ""),
            "Website": lead.get("website", ""),
            "Google Maps URL": lead.get("google_maps_url", ""),
            "Source": lead.get("source", ""),
            "Source URL": lead.get("source_url", ""),
            "Posted Date": lead.get("posted_date", ""),
            "Requirement": lead.get("requirement", ""),
            "Business Research": lead.get("business_research", ""),
            "Potential Problem": lead.get("potential_problem", ""),
            "Recommended Service": lead.get("recommended_service", ""),
            "Recommended AI Solution": lead.get("recommended_ai_solution", ""),
            "Lead Score": str(lead.get("lead_score", "")),
            "Contact Channel": lead.get("contact_channel", ""),
            "Initial Message": lead.get("initial_message", ""),
            "Initial Contact Date": lead.get("initial_contact_date", ""),
            "Initial Contact Status": lead.get("initial_contact_status", ""),
            "Follow-up 3 Day": lead.get("followup_3day", ""),
            "Follow-up 7 Day": lead.get("followup_7day", ""),
            "Response": lead.get("response", ""),
            "Response Category": lead.get("response_category", ""),
            "Follow-up Status": lead.get("followup_status", ""),
            "Do Not Contact": lead.get("do_not_contact", "No"),
            "Human Required": lead.get("human_required", "No"),
            "Notes": lead.get("notes", ""),
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
sheets_client = GoogleSheetsClient()
