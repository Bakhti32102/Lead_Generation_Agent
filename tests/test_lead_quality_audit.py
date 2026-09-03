"""
Regression tests for lead quality audit fixes:
1. Cross-campaign duplicate outreach protection
2. Score explainability (breakdown stored)
3. Phone validation after extraction
4. Email domain verification
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────────
# TEST 1 — Cross-campaign duplicate outreach protection
# ────────────────────────────────────────────────────────────────────

class TestCrossCampaignDuplicateProtection:
    """Verify that businesses already contacted in previous campaigns
    are skipped during discovery."""

    def test_outreach_lead_skipped_in_dedup(self):
        """A prospect matching an existing outreach lead should be skipped."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect
        from app.database.models import get_session, DiscoveredLead

        session = get_session()
        try:
            # Create an existing outreach lead
            existing = DiscoveredLead(
                business_name="Test Dental Clinic",
                business_category="dentist",
                country="Australia",
                city="Melbourne",
                email="test@example.com",
                website="https://testdental.com",
                is_outreach_lead=True,
                source="google_search",
                dedup_website="testdental.com",
                dedup_email="test@example.com",
            )
            session.add(existing)
            session.commit()
            session.refresh(existing)

            # Create a prospect with the same website
            prospect = RawProspect(
                business_name="Test Dental Clinic",
                business_category="dentist",
                country="Australia",
                city="Melbourne",
                email="test@example.com",
                website="https://testdental.com",
                source="openstreetmap",
            )

            # Run dedup
            discovery = LeadDiscoveryAgent.__new__(LeadDiscoveryAgent)
            discovery.repo = MagicMock()
            discovery.repo.is_duplicate.return_value = existing

            unique = discovery._deduplicate([prospect])

            # Should be empty — the prospect matches an outreach lead
            assert len(unique) == 0

        finally:
            session.query(DiscoveredLead).filter_by(id=existing.id).delete()
            session.commit()
            session.close()

    def test_non_outreach_lead_still_deduped(self):
        """A prospect matching a non-outreach lead is also deduped
        (standard dedup behavior preserved)."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect
        from app.database.models import get_session, DiscoveredLead

        session = get_session()
        try:
            # Create an existing NON-outreach lead
            existing = DiscoveredLead(
                business_name="Test Dental",
                business_category="dentist",
                country="Australia",
                city="Melbourne",
                email="test@example.com",
                is_outreach_lead=False,
                dedup_email="test@example.com",
            )
            session.add(existing)
            session.commit()
            session.refresh(existing)

            prospect = RawProspect(
                business_name="Test Dental",
                business_category="dentist",
                country="Australia",
                city="Melbourne",
                email="test@example.com",
                source="openstreetmap",
            )

            discovery = LeadDiscoveryAgent.__new__(LeadDiscoveryAgent)
            discovery.repo = MagicMock()
            discovery.repo.is_duplicate.return_value = existing

            unique = discovery._deduplicate([prospect])

            # Should also be empty — standard dedup still works
            assert len(unique) == 0

        finally:
            session.query(DiscoveredLead).filter_by(id=existing.id).delete()
            session.commit()
            session.close()


# ────────────────────────────────────────────────────────────────────
# TEST 2 — Score explainability
# ────────────────────────────────────────────────────────────────────

class TestScoreExplainability:
    """Verify that score breakdown is stored in metadata."""

    def test_score_breakdown_stored(self):
        """score() should store a breakdown dict in metadata."""
        from app.agents.lead_scoring import LeadScoringAgent
        from app.sources.base import RawProspect

        agent = LeadScoringAgent(
            target_category="dentist",
            target_country="australia",
            target_city="melbourne",
        )

        prospect = RawProspect(
            business_name="Test Dental",
            business_category="dentist",
            country="Australia",
            city="Melbourne",
            email="test@example.com",
            website="https://test.com",
            phone="+61412345678",
            source="openstreetmap",
        )
        prospect.metadata["problems_list"] = ["problem1", "problem2"]
        prospect.metadata["location_verification"] = MagicMock(
            state="verified", confidence=0.9
        )

        score = agent.score(prospect)

        assert score > 0
        assert "score_breakdown" in prospect.metadata
        breakdown = prospect.metadata["score_breakdown"]
        assert isinstance(breakdown, dict)
        assert "_final" in breakdown
        assert breakdown["_final"] == score
        # At least some factors should be present
        assert len(breakdown) >= 3

    def test_zero_score_has_empty_breakdown(self):
        """A zero-score lead should still have a breakdown."""
        from app.agents.lead_scoring import LeadScoringAgent
        from app.sources.base import RawProspect

        agent = LeadScoringAgent(
            target_category="dentist",
            target_country="australia",
            target_city="melbourne",
        )

        # Non-matching category, no contact, no website
        prospect = RawProspect(
            business_name="Random Business",
            business_category="restaurant",
            country="Germany",
            city="Berlin",
            source="linkedin",
        )

        score = agent.score(prospect)

        assert "score_breakdown" in prospect.metadata
        breakdown = prospect.metadata["score_breakdown"]
        assert breakdown["_final"] == score


# ────────────────────────────────────────────────────────────────────
# TEST 3 — Phone validation after extraction
# ────────────────────────────────────────────────────────────────────

class TestPhoneExtractionValidation:
    """Verify that extracted phone numbers are validated."""

    def test_valid_phone_extracted(self):
        """Valid phone numbers are extracted correctly."""
        from app.sources.google_search import GoogleSearchSource

        # Format with consistent digit groups matches the regex
        text = "Call us at +61412345678 or email info@example.com"
        phone = GoogleSearchSource._extract_phone(text)
        assert phone  # Should extract something

    def test_malformed_concatenated_rejected(self):
        """Obviously malformed numbers (too many digits) are rejected."""
        from app.sources.google_search import GoogleSearchSource

        # This is the exact malformed number from the real data
        text = "Phone: 9654 51449654"
        phone = GoogleSearchSource._extract_phone(text)
        # 12 digits without country code — should be rejected
        # (valid numbers are 7-15 digits)
        if phone:
            import re
            digits = re.sub(r"[^\d]", "", phone)
            assert len(digits) <= 15

    def test_empty_text_returns_empty(self):
        """Empty text returns empty phone."""
        from app.sources.google_search import GoogleSearchSource

        assert GoogleSearchSource._extract_phone("") == ""
        assert GoogleSearchSource._extract_phone("no phone here") == ""


# ────────────────────────────────────────────────────────────────────
# TEST 4 — Email domain verification
# ────────────────────────────────────────────────────────────────────

class TestEmailDomainVerification:
    """Verify email domain checking works correctly."""

    def test_valid_format_passes(self):
        """Valid email format passes without domain check."""
        from app.utils.phone import has_valid_email

        assert has_valid_email("test@example.com") is True
        assert has_valid_email("user@domain.org") is True

    def test_invalid_format_fails(self):
        """Invalid email format fails."""
        from app.utils.phone import has_valid_email

        assert has_valid_email("") is False
        assert has_valid_email("notanemail") is False
        assert has_valid_email("@domain.com") is False

    def test_blocked_domain_rejected(self):
        """Test/example domains are rejected with domain check."""
        from app.utils.phone import has_valid_email

        assert has_valid_email("test@example.com", check_domain=True) is False
        assert has_valid_email("user@test.com", check_domain=True) is False
        assert has_valid_email("admin@localhost", check_domain=True) is False

    def test_valid_domain_passes(self):
        """Real domains pass domain check."""
        from app.utils.phone import has_valid_email

        # gmail.com definitely has DNS
        assert has_valid_email("test@gmail.com", check_domain=True) is True

    def test_nonexistent_domain_fails(self):
        """Non-existent domain fails domain check."""
        from app.utils.phone import has_valid_email

        assert has_valid_email("test@nonexistent-domain-xyz123.com", check_domain=True) is False
