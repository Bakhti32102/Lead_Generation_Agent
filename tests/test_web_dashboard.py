"""
Tests for Web Dashboard.
Validates Flask routes and templates load correctly.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestWebDashboard:
    """Tests for Flask web dashboard."""

    def test_web_dashboard_importable(self):
        """Web dashboard module should be importable."""
        from app.dashboard.web import app
        assert app is not None

    def test_web_dashboard_has_routes(self):
        """Web dashboard should have all required routes."""
        from app.dashboard.web import app

        rules = [rule.rule for rule in app.url_map.iter_rules()]
        assert "/" in rules
        assert "/leads" in rules
        assert "/leads/<int:lead_id>" in rules
        assert "/campaign" in rules
        assert "/followups" in rules
        assert "/config" in rules

    def test_web_dashboard_client(self):
        """Flask test client should work."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/")
            assert response.status_code == 200
            assert b"AI Lead Generation Agent" in response.data

    def test_leads_page(self):
        """Leads page should load successfully."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/leads")
            assert response.status_code == 200
            assert b"Leads" in response.data

    def test_config_page(self):
        """Config page should load successfully."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/config")
            assert response.status_code == 200
            assert b"Configuration" in response.data

    def test_campaign_page(self):
        """Campaign page should load successfully."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/campaign")
            assert response.status_code == 200
            assert b"Campaign" in response.data

    def test_followups_page(self):
        """Follow-ups page should load successfully."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/followups")
            assert response.status_code == 200
            assert b"Follow-up" in response.data

    def test_lead_detail_page(self):
        """Lead detail page should handle missing leads."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/leads/99999")
            assert response.status_code == 404

    def test_dashboard_shows_stats(self):
        """Dashboard should show campaign statistics."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/")
            assert response.status_code == 200
            assert b"Target Leads" in response.data or b"Dashboard" in response.data

    def test_web_dashboard_has_navigation(self):
        """Dashboard should have navigation links."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/")
            assert b"Dashboard" in response.data
            assert b"Leads" in response.data
            assert b"Campaign" in response.data
            assert b"Follow-ups" in response.data
            assert b"Config" in response.data

    def test_config_shows_api_status(self):
        """Config page should show API configuration status."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/config")
            assert response.status_code == 200
            assert b"LLM API" in response.data
            assert b"Search API" in response.data
            assert b"Google Maps" in response.data

    def test_leads_page_empty(self):
        """Leads page should handle empty state gracefully."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/leads")
            assert response.status_code == 200
            assert b"All Qualified Leads" in response.data

    def test_followups_page_empty(self):
        """Follow-ups page should handle empty state gracefully."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/followups")
            assert response.status_code == 200
            assert b"Follow-up Management" in response.data

    def test_config_campaign_settings(self):
        """Config page should show campaign settings."""
        from app.dashboard.web import app

        with app.test_client() as client:
            response = client.get("/config")
            assert response.status_code == 200
            assert b"Campaign Settings" in response.data
            assert b"Business Information" in response.data
