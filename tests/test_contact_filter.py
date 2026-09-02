"""
Tests for mandatory contact-availability filter.

A lead is rejected when ALL THREE contact fields are missing:
  - phone (empty or N/A)
  - email (empty or N/A)
  - website (empty or N/A)
"""

import pytest
from app.agents.lead_verification import LeadVerificationAgent
from app.sources.base import RawProspect


class TestContactFilter:
    """Mandatory contact check: at least one of phone/email/website required."""

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
        assert result.metadata["skip_reason"] == "No contact information available"

    def test_reject_when_na_values(self):
        """Phone/email/website all 'N/A' → reject."""
        p = self._make(phone="N/A", email="N/A", website="N/A")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert result.metadata["skip_reason"] == "No contact information available"

    def test_reject_whitespace_only(self):
        """Whitespace-only contact fields → reject."""
        p = self._make(phone="  ", email="  ", website="  ")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert result.metadata["skip_reason"] == "No contact information available"

    def test_accept_with_phone_only(self):
        """Valid phone only → proceed."""
        p = self._make(phone="+923001234567", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No contact information available"

    def test_accept_with_email_only(self):
        """Valid email only → proceed."""
        p = self._make(phone="", email="info@clinic.com", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No contact information available"

    def test_accept_with_website_only(self):
        """Valid website only → proceed."""
        p = self._make(phone="", email="", website="https://clinic.com")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No contact information available"

    def test_accept_with_all_three(self):
        """All three present → proceed."""
        p = self._make(
            phone="+923001234567",
            email="info@clinic.com",
            website="https://clinic.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No contact information available"

    def test_reject_before_automation_check(self):
        """Contact filter runs before automation check — no crash on empty metadata."""
        p = self._make(phone="", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        # Should NOT have automation_check since we returned early
        assert "automation_check" not in result.metadata

    def test_osm_source_still_requires_contact(self):
        """OSM source with no contact → still rejected (bounded source is not a bypass)."""
        p = self._make(
            source="openstreetmap",
            phone="",
            email="",
            website="",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert result.metadata["skip_reason"] == "No contact information available"

    def test_google_maps_source_requires_contact(self):
        """Google Maps source with no contact → still rejected."""
        p = self._make(
            source="google_maps",
            phone="",
            email="",
            website="",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert result.metadata["skip_reason"] == "No contact information available"
