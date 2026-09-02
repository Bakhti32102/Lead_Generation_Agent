"""
Tests for strict contact channel enforcement.

A lead MUST have a valid Email address OR a direct WhatsApp number
to pass pre-qualification.  Phone-only leads (standard/landline numbers)
and website-only leads are rejected.
"""

import pytest
from app.agents.lead_verification import LeadVerificationAgent
from app.sources.base import RawProspect
from app.utils.phone import is_whatsapp_number, has_valid_email, has_reachable_channel


# ── Unit tests for phone utility ──


class TestWhatsAppDetection:
    """WhatsApp number detection heuristics."""

    def test_pakistani_mobile_is_whatsapp(self):
        """Pakistan mobile numbers (03XX) are WhatsApp-capable."""
        assert is_whatsapp_number("+923001234567") is True
        assert is_whatsapp_number("+923211234567") is True
        assert is_whatsapp_number("+923331234567") is True

    def test_pakistani_landline_is_not_whatsapp(self):
        """Pakistan landline numbers (042, 021) are NOT WhatsApp-capable."""
        assert is_whatsapp_number("+92421234567") is False
        assert is_whatsapp_number("+92211234567") is False

    def test_uae_mobile_is_whatsapp(self):
        """UAE mobile numbers (05X) are WhatsApp-capable."""
        assert is_whatsapp_number("+971501234567") is True
        assert is_whatsapp_number("+971551234567") is True

    def test_uae_landline_is_not_whatsapp(self):
        """UAE landline numbers (04X, 06X) are NOT WhatsApp-capable."""
        assert is_whatsapp_number("+97141234567") is False
        assert is_whatsapp_number("+97161234567") is False

    def test_uk_mobile_is_whatsapp(self):
        """UK mobile numbers (07XXX) are WhatsApp-capable."""
        assert is_whatsapp_number("+447911123456") is True

    def test_uk_landline_is_not_whatsapp(self):
        """UK landline numbers (01XXX, 02XXXX) are NOT WhatsApp-capable."""
        assert is_whatsapp_number("+442012345678") is False
        assert is_whatsapp_number("+441211234567") is False

    def test_india_mobile_is_whatsapp(self):
        """India mobile numbers (9XX, 8XX, 7XX) are WhatsApp-capable."""
        assert is_whatsapp_number("+919876543210") is True
        assert is_whatsapp_number("+918765432109") is True

    def test_empty_phone_is_not_whatsapp(self):
        """Empty or whitespace phone is not WhatsApp."""
        assert is_whatsapp_number("") is False
        assert is_whatsapp_number("  ") is False

    def test_short_phone_is_not_whatsapp(self):
        """Very short phone numbers are not WhatsApp."""
        assert is_whatsapp_number("12345") is False
        assert is_whatsapp_number("+1234") is False

    def test_local_format_pakistani_mobile(self):
        """Local format Pakistani mobile (03XX) should be detected."""
        assert is_whatsapp_number("03001234567") is True

    def test_formatted_phone_is_detected(self):
        """Phone with spaces/dashes should still be detected."""
        assert is_whatsapp_number("+92 300 123 4567") is True
        assert is_whatsapp_number("+971-50-123-4567") is True


class TestEmailValidation:
    """Email format validation."""

    def test_valid_email(self):
        assert has_valid_email("info@clinic.com") is True
        assert has_valid_email("user.name@domain.co.uk") is True

    def test_invalid_email(self):
        assert has_valid_email("not-an-email") is False
        assert has_valid_email("@domain.com") is False
        assert has_valid_email("user@") is False

    def test_empty_email(self):
        assert has_valid_email("") is False
        assert has_valid_email("  ") is False


class TestReachableChannel:
    """Combined email + WhatsApp check."""

    def test_email_only_is_reachable(self):
        assert has_reachable_channel("", "info@clinic.com") is True

    def test_whatsapp_only_is_reachable(self):
        assert has_reachable_channel("+923001234567", "") is True

    def test_both_present_is_reachable(self):
        assert has_reachable_channel("+923001234567", "info@clinic.com") is True

    def test_landline_only_is_not_reachable(self):
        assert has_reachable_channel("+92421234567", "") is False

    def test_website_only_is_not_reachable(self):
        """Website is NOT a reachable outreach channel."""
        assert has_reachable_channel("", "") is False


# ── Integration tests for LeadVerificationAgent ──


class TestStrictContactFilter:
    """Strict contact channel enforcement in verification."""

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
        """No email, no WhatsApp → reject."""
        p = self._make(phone="", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_reject_landline_only(self):
        """Landline phone only → reject (not WhatsApp-capable)."""
        p = self._make(phone="+92421234567", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_reject_website_only(self):
        """Website only → reject (no email or WhatsApp)."""
        p = self._make(phone="", email="", website="https://clinic.com")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_reject_na_values(self):
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

    def test_accept_with_email_only(self):
        """Valid email only → proceed."""
        p = self._make(phone="", email="info@clinic.com", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No reachable contact channel (email or WhatsApp required)"

    def test_accept_with_whatsapp_only(self):
        """WhatsApp-capable mobile number only → proceed."""
        p = self._make(phone="+923001234567", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "No reachable contact channel (email or WhatsApp required)"

    def test_accept_with_both(self):
        """Email + WhatsApp → proceed."""
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

    def test_pakistani_landline_rejected(self):
        """Pakistani landline (042) → rejected."""
        p = self._make(phone="+92423456789", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False

    def test_uae_landline_rejected(self):
        """UAE landline (04) → rejected."""
        p = self._make(phone="+97143456789", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False

    def test_uk_landline_rejected(self):
        """UK landline (020) → rejected."""
        p = self._make(phone="+442012345678", email="", website="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
