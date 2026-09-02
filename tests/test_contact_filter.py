"""
Tests for mandatory contact-availability filter.

A lead is rejected when it does NOT have a valid Email address OR
a direct WhatsApp number:
  - phone only (landline) → rejected
  - website only → rejected
  - email only → accepted
  - WhatsApp mobile number → accepted
  - email + WhatsApp → accepted
"""

import pytest
from app.agents.lead_verification import LeadVerificationAgent
from app.sources.base import RawProspect


class TestContactFilter:
    """Strict contact check: email OR WhatsApp number required."""

    def _make(self, **kwargs) -> RawProspect:
        defaults = dict(
            business_name="Test Clinic",
            business_category="dentist",
            city="Karachi",
            country="Pakistan",
        )
        defaults.update(kwargs)
        return RawProspect(**defaults)

    def test_reject_when_all_missing(self):
        """No phone, no email, no website → reject."""
        p = self._make(phone="", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_reject_when_na_values(self):
        """Phone/email/website all 'N/A' → reject."""
        p = self._make(phone="N/A", email="N/A", website="N/A")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_reject_whitespace_only(self):
        """Whitespace-only contact fields → reject."""
        p = self._make(phone="  ", email="  ", website="  ")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_reject_phone_only_mobile(self):
        """Valid mobile phone only (WhatsApp-capable) → proceed."""
        p = self._make(phone="+923001234567", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        # Mobile number is WhatsApp-capable → should be accepted
        assert result.metadata.get("skip_reason") != "No reachable contact channel (email or WhatsApp required)"

    def test_reject_landline_only(self):
        """Landline phone only → reject (not WhatsApp-capable)."""
        p = self._make(phone="+92421234567", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_accept_with_email_only(self):
        """Valid email only → proceed."""
        p = self._make(phone="", email="info@clinic.com", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No reachable contact channel (email or WhatsApp required)"

    def test_accept_with_website_only(self):
        """Website only → reject (no email or WhatsApp)."""
        p = self._make(phone="", email="", website="https://clinic.com")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_accept_with_all_three(self):
        """All three present → proceed."""
        p = self._make(
            phone="+923001234567",
            email="info@clinic.com",
            website="https://clinic.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No reachable contact channel (email or WhatsApp required)"

    def test_reject_before_automation_check(self):
        """Contact filter runs before automation check — no crash on empty metadata."""
        p = self._make(phone="", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        # Should NOT have automation_check since we returned early
        assert "automation_check" not in result.metadata

    def test_osm_source_still_requires_channel(self):
        """OSM source with no email/WhatsApp → still rejected."""
        p = self._make(
            source="openstreetmap",
            phone="+92421234567",  # landline
            email="",
            website="",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_google_maps_source_requires_channel(self):
        """Google Maps source with only landline → rejected."""
        p = self._make(
            source="google_maps",
            phone="+92421234567",  # landline
            email="",
            website="",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_whatsapp_mobile_accepted_from_osm(self):
        """OSM source with WhatsApp mobile number → accepted."""
        p = self._make(
            source="openstreetmap",
            phone="+923001234567",  # mobile
            email="",
            website="",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No reachable contact channel (email or WhatsApp required)"
