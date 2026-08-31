"""Tests for Google Sheets CRM integration."""

import pytest
from unittest.mock import patch, MagicMock


class TestGoogleSheetsColumnOrder:
    """SHEET_COLUMNS must match the specification."""

    def test_all_columns_present(self):
        from app.integrations.google_sheets import SHEET_COLUMNS
        required = [
            "Lead ID", "Date Found", "Business Name", "Business Category",
            "Country", "City", "Address", "Phone", "Email", "Website",
            "Google Maps URL", "Source", "Source URL", "Posted Date",
            "Requirement", "Business Research", "Potential Problem",
            "Recommended Service", "Recommended AI Solution", "Lead Score",
            "Contact Channel", "Initial Message", "Initial Contact Date",
            "Initial Contact Status", "Follow-up 3 Day", "Follow-up 7 Day",
            "Response", "Response Category", "Follow-up Status",
            "Do Not Contact", "Human Required", "Notes",
        ]
        for col in required:
            assert col in SHEET_COLUMNS, f"Missing column: {col}"

    def test_no_duplicates(self):
        from app.integrations.google_sheets import SHEET_COLUMNS
        assert len(SHEET_COLUMNS) == len(set(SHEET_COLUMNS))


class TestGoogleSheetsClient:
    """Test client initialization and helper methods."""

    def test_unconfigured_client(self):
        from app.integrations.google_sheets import GoogleSheetsClient
        client = GoogleSheetsClient()
        # Should not crash when unconfigured
        assert isinstance(client.is_configured, bool)

    def test_col_index_to_letter(self):
        from app.integrations.google_sheets import GoogleSheetsClient
        assert GoogleSheetsClient._col_index_to_letter(0) == "A"
        assert GoogleSheetsClient._col_index_to_letter(25) == "Z"
        assert GoogleSheetsClient._col_index_to_letter(26) == "AA"

    def test_lead_data_to_sheet_row(self):
        from app.integrations.google_sheets import GoogleSheetsClient
        client = GoogleSheetsClient()

        lead = {
            "lead_id": 42,
            "date_found": "2026-08-31",
            "business_name": "Smile Dental",
            "business_category": "Dental Clinic",
            "country": "Pakistan",
            "city": "Lahore",
            "address": "123 Main St",
            "phone": "+923001234567",
            "email": "info@smile.pk",
            "website": "https://smile.pk",
            "google_maps_url": "https://maps.google.com/abc",
            "source": "google_maps",
            "source_url": "https://google.com/maps/abc",
            "posted_date": "",
            "requirement": "",
            "business_research": "Dental clinic in Lahore",
            "potential_problem": "- Appointment booking",
            "recommended_service": "AI Chatbot",
            "recommended_ai_solution": "AI Dental Receptionist",
            "lead_score": 75,
            "contact_channel": "email",
            "initial_message": "Hi there...",
            "initial_contact_date": "2026-08-31",
            "initial_contact_status": "Sent",
            "followup_3day": "",
            "followup_7day": "",
            "response": "",
            "response_category": "",
            "followup_status": "Active",
            "do_not_contact": "No",
            "human_required": "No",
            "notes": "",
        }

        row = client.lead_data_to_sheet_row(lead)
        assert row["Lead ID"] == "42"
        assert row["Business Name"] == "Smile Dental"
        assert row["Lead Score"] == "75"
        assert row["Do Not Contact"] == "No"

    def test_read_all_rows_returns_list(self):
        """When not configured, should return empty list gracefully."""
        from app.integrations.google_sheets import GoogleSheetsClient
        client = GoogleSheetsClient()
        if not client.is_configured:
            # Should not crash
            result = client.read_all_rows()
            assert isinstance(result, list)


class TestGoogleSheetsSingleton:
    """Module-level singleton should be accessible."""

    def test_singleton_exists(self):
        from app.integrations.google_sheets import sheets_client
        assert sheets_client is not None

    def test_singleton_has_methods(self):
        from app.integrations.google_sheets import sheets_client
        assert hasattr(sheets_client, "read_all_rows")
        assert hasattr(sheets_client, "append_lead")
        assert hasattr(sheets_client, "update_cell")
        assert hasattr(sheets_client, "lead_data_to_sheet_row")
