"""Tests for 24-hour freshness filtering on recent requirement sources."""

import pytest

from app.sources.base import RawProspect
from app.agents.lead_verification import LeadVerificationAgent


class TestFreshnessFiltering:
    """Recent requirements should be filtered by recency."""

    def test_verified_recent_passes(self):
        """'verified_recent' freshness should pass verification."""
        p = RawProspect(
            business_name="Tech Startup",
            source="linkedin",
            freshness="verified_recent",
            website="https://techstartup.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_probably_recent_passes(self):
        """'probably_recent' freshness should pass verification."""
        p = RawProspect(
            business_name="AI Company",
            source="linkedin",
            freshness="probably_recent",
            website="https://aicompany.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_unknown_freshness_passes(self):
        """'unknown' freshness should still pass (partial credit in scoring)."""
        p = RawProspect(
            business_name="Old Post",
            source="linkedin",
            freshness="unknown",
            website="https://oldpost.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_business_listings_skip_freshness(self):
        """Business listings (google_maps) should not need freshness check."""
        p = RawProspect(
            business_name="Dental Clinic",
            source="google_maps",
            freshness="unknown",
            website="https://clinic.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_freshness_affects_score(self):
        """Recent requirements should score higher than non-recent on freshness points.

        Both prospects have identical data except freshness, so the only
        scoring difference should come from the freshness/recent-requirement
        factor: verified_recent=+25 vs unknown=+5 = 20 point gap.
        """
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")

        base_kw = dict(
            business_name="Test",
            business_category="AI Services",
            country="UAE",
            city="Dubai",
            # Minimal contact — avoid contact-related scoring
            website="",
            email="",
            phone="",
            # No automation problems, no demo — avoid those scoring points
            metadata={"problems_list": [], "demo_url": ""},
        )

        recent = RawProspect(
            source="linkedin",
            freshness="verified_recent",
            **base_kw,
        )
        old = RawProspect(
            source="linkedin",
            freshness="unknown",
            **base_kw,
        )

        recent_score = scoring.score(recent)
        old_score = scoring.score(old)

        # Verified recent = +25, unknown = +5 → 20 point gap
        assert recent_score == old_score + 20, (
            f"Expected 20-point gap, got recent={recent_score} old={old_score}"
        )
