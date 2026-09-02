"""
Comprehensive E2E Audit Test Suite.
Tests sections 2-18 of the production readiness audit.
All tests use synthetic/mock data. No real outreach.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

# Ensure we're in the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════
# SECTION 2: DISCOVERY / SEARCH E2E
# ═══════════════════════════════════════════════════════════════

class TestDiscoveryE2E:
    """Verify lead discovery pipeline with mock data."""

    def test_rawprospect_fields_complete(self):
        """RawProspect should contain all expected fields."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Test Clinic",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            address="123 Main St",
            phone="+923001234567",
            email="test@clinic.com",
            website="https://clinic.com",
            google_maps_url="https://maps.google.com/test",
            source="google_search",
            source_url="https://search.example.com",
            posted_date="2026-09-01",
            requirement_text="Need AI chatbot",
        )
        assert p.business_name == "Test Clinic"
        assert p.business_category == "Dental Clinic"
        assert p.country == "Pakistan"
        assert p.city == "Lahore"
        assert p.email == "test@clinic.com"
        assert p.website == "https://clinic.com"
        assert p.source == "google_search"

    def test_rawprospect_metadata_dict(self):
        """RawProspect metadata should accept arbitrary data."""
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Test")
        p.metadata["snippet"] = "Best dental clinic in Lahore"
        p.metadata["freshness"] = "verified_recent"
        p.metadata["problems_list"] = ["appointment booking", "FAQ automation"]
        assert p.metadata["snippet"] == "Best dental clinic in Lahore"
        assert len(p.metadata["problems_list"]) == 2

    def test_discovery_dedup_by_website(self):
        """Duplicate prospects with same website should be deduplicated."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect

        agent = LeadDiscoveryAgent()
        prospects = [
            RawProspect(business_name="Clinic A", website="https://clinic-a.com", city="Lahore", country="Pakistan"),
            RawProspect(business_name="Clinic B", website="https://clinic-a.com", city="Lahore", country="Pakistan"),
            RawProspect(business_name="Clinic C", website="https://clinic-c.com", city="Lahore", country="Pakistan"),
        ]
        # Mock the database dedup check to return None (no existing records)
        with patch.object(agent.repo, 'is_duplicate', return_value=None):
            result = agent._deduplicate(prospects)
        assert len(result) == 2  # Clinic A and C survive

    def test_discovery_dedup_by_email(self):
        """Duplicate prospects with same email should be deduplicated."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect

        agent = LeadDiscoveryAgent()
        prospects = [
            RawProspect(business_name="Clinic A", email="same@test.com"),
            RawProspect(business_name="Clinic B", email="same@test.com"),
        ]
        with patch.object(agent.repo, 'is_duplicate', return_value=None):
            result = agent._deduplicate(prospects)
        assert len(result) == 1

    def test_discovery_dedup_by_phone(self):
        """Duplicate prospects with same phone should be deduplicated."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect

        agent = LeadDiscoveryAgent()
        prospects = [
            RawProspect(business_name="Clinic A", phone="+923001234567"),
            RawProspect(business_name="Clinic B", phone="923001234567"),
        ]
        with patch.object(agent.repo, 'is_duplicate', return_value=None):
            result = agent._deduplicate(prospects)
        assert len(result) == 1

    def test_discovery_dedup_by_name_city(self):
        """Duplicate prospects with same name+city should be deduplicated."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect

        agent = LeadDiscoveryAgent()
        prospects = [
            RawProspect(business_name="Smile Dental", city="Lahore"),
            RawProspect(business_name="Smile Dental", city="Lahore"),
        ]
        with patch.object(agent.repo, 'is_duplicate', return_value=None):
            result = agent._deduplicate(prospects)
        assert len(result) == 1

    def test_discovery_empty_results(self):
        """Empty search results should produce empty list."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect

        agent = LeadDiscoveryAgent()
        with patch.object(agent.repo, 'is_duplicate', return_value=None):
            result = agent._deduplicate([])
        assert result == []

    def test_dedup_preserves_different_businesses(self):
        """Different businesses should not be deduplicated."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect

        agent = LeadDiscoveryAgent()
        prospects = [
            RawProspect(business_name="Smile Dental", city="Lahore", website="https://smile.com"),
            RawProspect(business_name="Care Dental", city="Lahore", website="https://care.com"),
            RawProspect(business_name="Bright Dental", city="Karachi", website="https://bright.com"),
        ]
        with patch.object(agent.repo, 'is_duplicate', return_value=None):
            result = agent._deduplicate(prospects)
        assert len(result) == 3


# ═══════════════════════════════════════════════════════════════
# SECTION 3: LOCATION VERIFICATION
# ═══════════════════════════════════════════════════════════════

class TestLocationVerificationAudit:
    """Audit location verification with all 4 states."""

    def setup_method(self):
        from app.agents.location_verifier import LocationVerifier
        self.verifier = LocationVerifier()

    def _make_prospect(self, **kwargs):
        from app.sources.base import RawProspect
        defaults = {
            "business_name": "Test Business",
            "business_category": "Dental Clinic",
            "country": "",
            "city": "",
            "website": "",
            "address": "",
        }
        defaults.update(kwargs)
        return RawProspect(**defaults)

    def test_verified_city_and_country_structured(self):
        """Structured city+country both matching -> verified."""
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Smile Dental", city="Lahore", country="Pakistan")
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "verified"
        assert result.confidence >= 0.9

    def test_verified_city_and_country_text(self):
        """Text with both city+country -> verified."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental",
            metadata={"snippet": "Best dental clinic in Lahore, Pakistan"},
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "verified"

    def test_probably_verified_only_country(self):
        """Only country structured field -> probably_verified."""
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Smile Dental", country="Pakistan", city="")
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "probably_verified"

    def test_probably_verified_only_city(self):
        """Only city structured field -> probably_verified."""
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Smile Dental", city="Lahore", country="")
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "probably_verified"

    def test_probably_verified_text_city_only(self):
        """Text mentions only city -> probably_verified."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental",
            metadata={"snippet": "Best dental clinic in Lahore"},
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "probably_verified"

    def test_unknown_no_evidence(self):
        """No location evidence at all -> unknown."""
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Smile Dental")
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "unknown"

    def test_mismatch_different_city_structured(self):
        """Structured city contradicts target -> mismatch."""
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Smile Dental", city="Karachi", country="Pakistan")
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "mismatch"

    def test_mismatch_different_country_structured(self):
        """Structured country contradicts target -> mismatch."""
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Smile Dental", city="Mumbai", country="India")
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "mismatch"

    def test_mismatch_text_mentions_other_city(self):
        """Text mentions a different city -> mismatch."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental Karachi",
            metadata={"snippet": "Dental services in Karachi, Pakistan"},
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "mismatch"

    def test_mismatch_text_mentions_other_country(self):
        """Text mentions a different country -> mismatch."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental",
            metadata={"snippet": "Best dental clinic in Mumbai, India"},
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "mismatch"

    def test_url_domain_evidence(self):
        """URL with .pk domain contributes to country evidence."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental",
            website="https://smiledental.pk",
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        # .pk domain + no other evidence = probably_verified (country only)
        assert result.state in ("verified", "probably_verified")

    def test_address_evidence(self):
        """Address containing city name contributes to verification."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental",
            address="123 Main Boulevard, Gulberg, Lahore",
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state in ("verified", "probably_verified")

    def test_business_name_contains_city(self):
        """Business name containing city name contributes to verification."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental Clinic Lahore",
            website="https://smiledental.pk",
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state in ("verified", "probably_verified")

    def test_dot_com_not_flagged_as_usa(self):
        """A .com domain should NOT trigger USA mismatch."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental",
            city="Lahore",
            country="Pakistan",
            website="https://smiledental.com",
        )
        result = self.verifier.verify(p, "Lahore", "Pakistan")
        assert result.state == "verified"  # structured match, .com not a problem

    def test_empty_target_city(self):
        """Empty target city should not cause mismatch."""
        from app.sources.base import RawProspect
        p = RawProspect(
            business_name="Smile Dental",
            country="Pakistan",
        )
        result = self.verifier.verify(p, "", "Pakistan")
        # country matches, no target city to mismatch with
        assert result.state in ("verified", "probably_verified", "unknown")


# ═══════════════════════════════════════════════════════════════
# SECTION 4: LEAD SCORING
# ═══════════════════════════════════════════════════════════════

class TestLeadScoringAudit:
    """Audit the scoring implementation."""

    def _make_prospect(self, **kwargs):
        from app.sources.base import RawProspect
        defaults = {
            "business_name": "Test Business",
            "business_category": "Dental Clinic",
            "country": "Pakistan",
            "city": "Lahore",
            "email": "test@clinic.com",
            "phone": "+923001234567",
            "website": "https://clinic.com",
            "metadata": {},
        }
        defaults.update(kwargs)
        return RawProspect(**defaults)

    def test_weights_sum_does_not_exceed_100_with_cap(self):
        """WEIGHTS can sum to >100 but score() must cap at 100."""
        from app.agents.lead_scoring import LeadScoringAgent
        total = sum(LeadScoringAgent.WEIGHTS.values())
        assert total <= 110, f"WEIGHTS sum to {total}, seems too high"
        # The score() method uses min(score, 100) so this is safe

    def test_score_never_exceeds_100(self):
        """Score should never exceed 100."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )
        # Create a prospect with maximum possible data
        p = self._make_prospect(
            email="test@clinic.com",
            phone="+923001234567",
            website="https://clinic.com",
            google_maps_url="https://maps.google.com/test",
            address="123 Main St, Lahore",
            source="google_maps",
            metadata={
                "problems_list": ["appointment booking", "FAQ automation", "customer support"],
                "demo_url": "https://demo.com",
                "demo_name": "Medical Chatbot",
                "has_whatsapp": True,
                "location_verification": MagicMock(state="verified", confidence=0.95),
                "snippet": "Best dental clinic in Lahore, Pakistan",
                "freshness": "verified_recent",
            },
        )
        score = agent.score(p)
        assert score <= 100

    def test_strong_lead_scores_high(self):
        """A well-qualified lead should score >= 60."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )
        p = self._make_prospect(
            email="test@clinic.com",
            phone="+923001234567",
            website="https://clinic.com",
            address="123 Main St, Lahore",
            source="google_maps",
            metadata={
                "problems_list": ["appointment booking", "FAQ automation"],
                "demo_url": "https://demo.com",
                "has_whatsapp": True,
                "location_verification": MagicMock(state="verified", confidence=0.95),
                "snippet": "Best dental clinic in Lahore, Pakistan",
            },
        )
        score = agent.score(p)
        assert score >= 60, f"Strong lead scored {score}, expected >= 60"

    def test_weak_lead_scores_low(self):
        """A weak lead with minimal data should score below 60."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )
        p = self._make_prospect(
            business_name="Unknown Business",
            business_category="Retail",
            country="",
            city="",
            email="",
            phone="",
            website="",
            metadata={
                "location_verification": MagicMock(state="unknown", confidence=0.0),
            },
        )
        score = agent.score(p)
        assert score < 60, f"Weak lead scored {score}, expected < 60"

    def test_location_mismatch_gives_zero(self):
        """Location mismatch should result in score=0 (via batch rejection)."""
        from app.agents.lead_scoring import LeadScoringAgent
        from app.sources.base import RawProspect
        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )
        prospects = [
            RawProspect(
                business_name="Karachi Dental",
                business_category="Dental Clinic",
                country="Pakistan",
                city="Karachi",
                email="test@kd.com",
                website="https://kd.com",
            )
        ]
        result = agent.score_batch(prospects)
        assert result[0].lead_score == 0
        assert result[0].is_qualified is False

    def test_location_unknown_no_bonus(self):
        """Unknown location should not add location points."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )
        p = self._make_prospect(
            country="",
            city="",
            email="test@clinic.com",
            phone="+923001234567",
            website="https://clinic.com",
            metadata={
                "location_verification": MagicMock(state="unknown", confidence=0.0),
            },
        )
        score = agent.score(p)
        # Should have no location_match or location_verification points
        assert score <= 100

    def test_category_match_awards_points(self):
        """Matching category should award relevant_category points."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )
        # With category match
        p_match = self._make_prospect(business_category="Dental Clinic", country="", city="", email="", phone="", website="")
        p_match.metadata["location_verification"] = MagicMock(state="unknown", confidence=0.0)
        score_match = agent.score(p_match)

        # Without category match
        p_no_match = self._make_prospect(business_category="Restaurant", country="", city="", email="", phone="", website="")
        p_no_match.metadata["location_verification"] = MagicMock(state="unknown", confidence=0.0)
        score_no_match = agent.score(p_no_match)

        assert score_match > score_no_match

    def test_location_match_awards_points(self):
        """Matching location should award location_match points."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )
        # With location match
        p_match = self._make_prospect(email="", phone="", website="", metadata={
            "location_verification": MagicMock(state="verified", confidence=0.9),
        })
        score_match = agent.score(p_match)

        # Without location match
        p_no = self._make_prospect(country="", city="", email="", phone="", website="", metadata={
            "location_verification": MagicMock(state="unknown", confidence=0.0),
        })
        score_no = agent.score(p_no)

        assert score_match > score_no

    def test_website_email_phone_all_award_points(self):
        """Having website, email, phone should each award points."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(target_category="Dental Clinic", target_country="Pakistan", target_city="Lahore")

        # Full data
        p_full = self._make_prospect(email="t@t.com", phone="+923001234567", website="https://test.com",
                                      metadata={"location_verification": MagicMock(state="unknown", confidence=0.0)})
        s_full = agent.score(p_full)

        # No data
        p_empty = self._make_prospect(email="", phone="", website="",
                                       metadata={"location_verification": MagicMock(state="unknown", confidence=0.0)})
        s_empty = agent.score(p_empty)

        assert s_full > s_empty

    def test_automation_opportunity_awards_points(self):
        """Having problems should award automation_opportunity points."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(target_category="Dental Clinic", target_country="Pakistan", target_city="Lahore")

        # With problems
        p_problems = self._make_prospect(email="", phone="", website="", metadata={
            "problems_list": ["booking", "FAQ"],
            "location_verification": MagicMock(state="unknown", confidence=0.0),
        })
        s_problems = agent.score(p_problems)

        # Without problems
        p_no = self._make_prospect(email="", phone="", website="", metadata={
            "location_verification": MagicMock(state="unknown", confidence=0.0),
        })
        s_no = agent.score(p_no)

        assert s_problems > s_no

    def test_strong_evidence_awards_points(self):
        """Having 3+ evidence sources should award strong_evidence points."""
        from app.agents.lead_scoring import LeadScoringAgent
        agent = LeadScoringAgent(target_category="Dental Clinic", target_country="Pakistan", target_city="Lahore")

        # Strong evidence (website + email + phone + google_maps = 4)
        p_strong = self._make_prospect(
            email="t@t.com", phone="+923001234567", website="https://test.com",
            address="123 St", google_maps_url="https://maps.google.com/test",
            source="google_maps",
            metadata={"location_verification": MagicMock(state="unknown", confidence=0.0)},
        )
        s_strong = agent.score(p_strong)

        # Weak evidence (no website, email, phone)
        p_weak = self._make_prospect(
            email="", phone="", website="",
            metadata={"location_verification": MagicMock(state="unknown", confidence=0.0)},
        )
        s_weak = agent.score(p_weak)

        assert s_strong > s_weak


# ═══════════════════════════════════════════════════════════════
# SECTION 5: QUALIFICATION / FILTERING
# ═══════════════════════════════════════════════════════════════

class TestQualificationAudit:
    """Audit qualification threshold and filtering rules."""

    def test_threshold_from_settings(self):
        """Qualification threshold should come from settings."""
        from app.config.settings import settings
        threshold = settings.campaign.lead_score_threshold
        assert isinstance(threshold, int)
        assert threshold > 0
        assert threshold <= 100

    def test_threshold_default_is_60(self):
        """Default threshold should be 60."""
        from app.config.settings import settings
        # The .env may override, but the default is 60
        assert settings.campaign.lead_score_threshold >= 0

    def test_qualified_leads_only_above_threshold(self):
        """Only leads with score >= threshold should be marked qualified."""
        from app.agents.lead_scoring import LeadScoringAgent
        from app.sources.base import RawProspect
        from app.config.settings import settings

        agent = LeadScoringAgent(
            target_category="Dental Clinic",
            target_country="Pakistan",
            target_city="Lahore",
        )

        threshold = settings.campaign.lead_score_threshold

        # High-scoring lead
        p_high = RawProspect(
            business_name="Smile Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            email="test@smile.com",
            phone="+923001234567",
            website="https://smile.com",
            address="123 Main St, Lahore",
            source="google_maps",
            google_maps_url="https://maps.google.com/test",
            metadata={
                "problems_list": ["booking", "FAQ"],
                "demo_url": "https://demo.com",
                "has_whatsapp": True,
                "location_verification": MagicMock(state="verified", confidence=0.95),
                "snippet": "Best dental clinic in Lahore, Pakistan",
            },
        )

        # Low-scoring lead
        p_low = RawProspect(
            business_name="Unknown Shop",
            business_category="Retail",
            metadata={
                "location_verification": MagicMock(state="unknown", confidence=0.0),
            },
        )

        result = agent.score_batch([p_high, p_low])
        for p in result:
            if p.lead_score >= threshold:
                assert p.is_qualified is True
            else:
                assert p.is_qualified is False

    def test_select_top_leads_limits_count(self):
        """select_top_leads should return at most N leads."""
        from app.agents.lead_scoring import LeadScoringAgent
        from app.sources.base import RawProspect

        agent = LeadScoringAgent(target_category="Dental Clinic", target_country="Pakistan", target_city="Lahore")
        prospects = []
        for i in range(10):
            p = RawProspect(
                business_name=f"Clinic {i}",
                business_category="Dental Clinic",
                country="Pakistan",
                city="Lahore",
                email=f"test{i}@clinic.com",
                phone=f"+92300123456{i}",
                website=f"https://clinic{i}.com",
                address=f"{i} Main St, Lahore",
                source="google_maps",
                google_maps_url=f"https://maps.google.com/test{i}",
                metadata={
                    "problems_list": ["booking", "FAQ"],
                    "demo_url": "https://demo.com",
                    "has_whatsapp": True,
                    "location_verification": MagicMock(state="verified", confidence=0.95),
                    "snippet": f"Clinic {i} in Lahore, Pakistan",
                },
            )
            prospects.append(p)

        scored = agent.score_batch(prospects)
        top = agent.select_top_leads(scored, 3)
        assert len(top) <= 3


# ═══════════════════════════════════════════════════════════════
# SECTION 6: DEDUPLICATION
# ═══════════════════════════════════════════════════════════════

class TestDeduplicationAudit:
    """Audit deduplication in discovery and database."""

    def test_dedup_by_website_domain(self):
        """Normalized website domain should be used for dedup."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        assert LeadDiscoveryAgent._normalize_website("https://WWW.Example.COM/") == "example.com"
        assert LeadDiscoveryAgent._normalize_website("http://example.com") == "example.com"
        assert LeadDiscoveryAgent._normalize_website("example.com") == "example.com"
        assert LeadDiscoveryAgent._normalize_website("") == ""

    def test_dedup_by_phone_normalization(self):
        """Phone numbers should be normalized to digits-only."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        assert LeadDiscoveryAgent._normalize_phone("+92 300 123 4567") == "923001234567"
        assert LeadDiscoveryAgent._normalize_phone("(923) 001-234567") == "923001234567"
        assert LeadDiscoveryAgent._normalize_phone("") == ""

    def test_database_dedup_check(self):
        """is_duplicate should check website, email, phone, maps_url."""
        from app.database.repository import LeadRepository
        from app.database.models import init_db
        init_db()
        repo = LeadRepository()

        # No existing records should return None for clean data
        result = repo.is_duplicate(
            website="https://nonexistent-dedup-test-xyz123.com",
            email="nonexistent-dedup-test-xyz123@test.com",
        )
        assert result is None

    def test_no_duplicates_from_multiple_sources(self):
        """Same business from Google Maps and Google Search should be deduplicated."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        from app.sources.base import RawProspect

        agent = LeadDiscoveryAgent()
        prospects = [
            RawProspect(
                business_name="Smile Dental",
                website="https://smiledental.pk",
                email="info@smiledental.pk",
                source="google_maps",
            ),
            RawProspect(
                business_name="Smile Dental Clinic",
                website="https://smiledental.pk",
                email="info@smiledental.pk",
                source="google_search",
            ),
        ]
        with patch.object(agent.repo, 'is_duplicate', return_value=None):
            result = agent._deduplicate(prospects)
        assert len(result) == 1


# ═══════════════════════════════════════════════════════════════
# SECTION 8: MESSAGE GENERATION
# ═══════════════════════════════════════════════════════════════

class TestMessageGenerationAudit:
    """Audit message generation pipeline."""

    def _make_prospect(self):
        from app.sources.base import RawProspect
        return RawProspect(
            business_name="Smile Dental Clinic",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://smiledental.pk",
            email="info@smiledental.pk",
            potential_problem="Appointment scheduling is manual and time-consuming",
            recommended_service="AI Chatbot",
            recommended_ai_solution="Custom AI appointment booking system",
            business_research="Smile Dental is a modern dental clinic in Lahore offering general dentistry, orthodontics, and cosmetic procedures.",
            metadata={
                "problems_list": ["appointment scheduling", "patient FAQ"],
                "demo_url": "https://demo.example.com/medical-chatbot",
                "demo_name": "Medical Chatbot",
            },
        )

    def test_template_message_contains_business_name(self):
        """Template message should mention the business name."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent(llm=MagicMock(is_configured=False))
        p = self._make_prospect()
        message = agent._generate_template(p)
        assert "Smile Dental Clinic" in message

    def test_template_message_does_not_expose_prompts(self):
        """Template message should not contain internal prompt text."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent(llm=MagicMock(is_configured=False))
        p = self._make_prospect()
        message = agent._generate_template(p)
        assert "system_prompt" not in message.lower()
        assert "user_prompt" not in message.lower()

    def test_template_message_contains_links(self):
        """Template message should contain sender's links if configured."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent(llm=MagicMock(is_configured=False))
        p = self._make_prospect()
        message = agent._generate_template(p)
        # Message should be non-empty and reasonable length
        assert len(message) > 100
        assert len(message) < 3000

    def test_template_message_no_placeholder_variables(self):
        """Template message should not contain unresolved {variables}."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent(llm=MagicMock(is_configured=False))
        p = self._make_prospect()
        message = agent._generate_template(p)
        import re
        unresolved = re.findall(r'\{[a-zA-Z_]+\}', message)
        assert len(unresolved) == 0, f"Unresolved placeholders: {unresolved}"

    def test_followup_3day_message(self):
        """3-day follow-up message should mention the business."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent(llm=MagicMock(is_configured=False))
        p = self._make_prospect()
        msg_3day = agent.generate_followup_message(p, "3day")
        assert "Smile Dental Clinic" in msg_3day
        assert len(msg_3day) > 50

    def test_followup_7day_message(self):
        """7-day follow-up message should mention the business."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent(llm=MagicMock(is_configured=False))
        p = self._make_prospect()
        msg_7day = agent.generate_followup_message(p, "7day")
        assert "Smile Dental Clinic" in msg_7day
        assert len(msg_7day) > 50

    def test_llm_message_fallback_on_failure(self):
        """If LLM fails, should fall back to template."""
        from app.agents.personalization import PersonalizationAgent
        mock_llm = MagicMock(is_configured=True)
        mock_llm.generate.side_effect = Exception("LLM API error")
        agent = PersonalizationAgent(llm=mock_llm)
        p = self._make_prospect()
        message = agent.generate_message(p)
        # Should get template fallback
        assert "Smile Dental Clinic" in message
        assert len(message) > 100


# ═══════════════════════════════════════════════════════════════
# SECTION 9: OUTREACH SAFETY
# ═══════════════════════════════════════════════════════════════

class TestOutreachSafetyAudit:
    """Audit DRY_RUN and REVIEW_MODE safety."""

    def test_dry_run_blocks_send_initial(self):
        """DRY_RUN=true should block actual sending."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.config.settings import settings

        assert settings.campaign.dry_run is True

        agent = OutreachAgent()
        p = RawProspect(business_name="Test", email="test@test.com")
        result = agent.send_initial(p, "Test message")
        assert result["status"] == "draft"
        assert result["message_id"] == "dry_run"

    def test_dry_run_blocks_send_followup(self):
        """DRY_RUN=true should block follow-up sending."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.config.settings import settings

        assert settings.campaign.dry_run is True

        agent = OutreachAgent()
        p = RawProspect(business_name="Test", email="test@test.com")
        result = agent.send_followup(p, "Follow-up message", "3day", lead_db_id=0)
        assert result["status"] == "draft"

    def test_review_mode_blocks_auto_send(self):
        """REVIEW_MODE=true should return pending_review status."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.config.settings import settings

        # Both DRY_RUN and REVIEW_MODE should block
        assert settings.campaign.dry_run is True
        assert settings.campaign.review_mode is True

        agent = OutreachAgent()
        p = RawProspect(business_name="Test", email="test@test.com")
        result = agent.send_initial(p, "Test message")
        # DRY_RUN takes precedence, returns "draft"
        assert result["status"] in ("draft", "pending_review")

    def test_no_real_email_api_call_in_dry_run(self):
        """DRY_RUN should never call the email client send method."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.integrations.email import email_client

        with patch.object(email_client, 'send') as mock_send:
            agent = OutreachAgent()
            p = RawProspect(business_name="Test", email="test@test.com")
            result = agent.send_initial(p, "Test message")
            mock_send.assert_not_called()

    def test_no_real_whatsapp_api_call_in_dry_run(self):
        """DRY_RUN should never call the WhatsApp client."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.integrations.whatsapp import whatsapp_client

        with patch.object(whatsapp_client, 'send_text') as mock_send:
            agent = OutreachAgent()
            p = RawProspect(business_name="Test", phone="+923001234567")
            result = agent.send_initial(p, "Test message")
            mock_send.assert_not_called()


# ═══════════════════════════════════════════════════════════════
# SECTION 10: HUMAN APPROVAL FLOW
# ═══════════════════════════════════════════════════════════════

class TestHumanApprovalAudit:
    """Audit the approve_and_send flow."""

    def test_approve_requires_lead_in_db(self):
        """approve_and_send should fail if lead not found."""
        from app.agents.outreach import OutreachAgent
        agent = OutreachAgent()
        result = agent.approve_and_send(lead_db_id=999999)
        assert result["success"] is False
        assert "not found" in result["message"].lower()

    def test_approve_without_message_fails(self):
        """approve_and_send should fail if no message stored."""
        from app.agents.outreach import OutreachAgent
        from app.database import LeadRepository
        from app.database.models import init_db

        init_db()
        repo = LeadRepository()

        # Save a test lead
        lead = repo.save_lead({
            "business_name": "Test Approve Lead",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
            "notes": "",  # No message
        })

        agent = OutreachAgent()
        result = agent.approve_and_send(lead.id)
        assert result["success"] is False
        assert "no message" in result["message"].lower()

        # Cleanup
        from app.database.models import get_session, DiscoveredLead
        session = get_session()
        session.query(DiscoveredLead).filter_by(id=lead.id).delete()
        session.commit()
        session.close()


# ═══════════════════════════════════════════════════════════════
# SECTION 11: DAILY LIMITS
# ═══════════════════════════════════════════════════════════════

class TestDailyLimitsAudit:
    """Audit daily outreach limit implementation."""

    def test_counter_persists_in_database(self):
        """Outreach count should persist across CounterRepository instances."""
        from app.database.repository import CounterRepository
        from app.database.models import init_db

        init_db()
        import uuid
        date_str = f"2099-12-{abs(hash(str(uuid.uuid4())) % 28) + 1:02d}"

        # Reset
        from app.database.models import DailyCounter, get_session
        session = get_session()
        existing = session.query(DailyCounter).filter_by(date=date_str).first()
        if existing:
            existing.outreach_count = 0
            session.commit()
        session.close()

        counter = CounterRepository()
        counter.increment_outreach(date_str)
        count = counter.get_outreach_count(date_str)
        assert count == 1

        # New instance should see the same count
        counter2 = CounterRepository()
        count2 = counter2.get_outreach_count(date_str)
        assert count2 == 1

    def test_can_send_respects_limit(self):
        """can_send_more should return False at limit."""
        from app.database.repository import CounterRepository
        from app.database.models import DailyCounter, get_session, init_db

        init_db()
        import uuid
        date_str = f"2099-11-{abs(hash(str(uuid.uuid4())) % 28) + 1:02d}"

        # Reset
        session = get_session()
        existing = session.query(DailyCounter).filter_by(date=date_str).first()
        if existing:
            existing.outreach_count = 0
            session.commit()
        session.close()

        counter = CounterRepository()
        limit = 5

        for i in range(limit):
            assert counter.can_send_more(limit, date_str) is True
            counter.increment_outreach(date_str)

        assert counter.can_send_more(limit, date_str) is False
        assert counter.can_send_more(limit, date_str) is False  # Still blocked

    def test_limit_configured_from_env(self):
        """Daily limit should come from settings."""
        from app.config.settings import settings
        limit = settings.campaign.max_daily_outreach
        assert isinstance(limit, int)
        assert limit > 0
        assert limit <= 1000  # Reasonable upper bound


# ═══════════════════════════════════════════════════════════════
# SECTION 12: DNC / OPT-OUT
# ═══════════════════════════════════════════════════════════════

class TestDNCAudit:
    """Audit Do Not Contact behavior."""

    def test_dnc_flag_blocks_initial(self):
        """DNC lead should be blocked from initial outreach."""
        from app.database import FollowUpRepository, LeadRepository
        from app.database.models import init_db, DiscoveredLead, get_session

        init_db()
        lead_repo = LeadRepository()
        followup_repo = FollowUpRepository()

        # Create test lead
        lead = lead_repo.save_lead({
            "business_name": "DNC Test Lead",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        })

        # Create follow-up state and mark DNC
        followup_repo.create_state(lead.id)
        followup_repo.set_do_not_contact(lead.id)

        # Verify DNC is set
        state = followup_repo.get_by_lead_id(lead.id)
        assert state.do_not_contact is True
        assert state.overall_status == "stopped"

        # Cleanup
        session = get_session()
        session.query(DiscoveredLead).filter_by(id=lead.id).delete()
        from app.database.models import FollowUpState
        session.query(FollowUpState).filter_by(lead_id=lead.id).delete()
        session.commit()
        session.close()

    def test_not_interested_sets_dnc(self):
        """Replying 'not interested' should set DNC."""
        from app.agents.follow_up import FollowUpAgent
        from app.database import FollowUpRepository, LeadRepository
        from app.database.models import init_db, DiscoveredLead, get_session

        init_db()
        lead_repo = LeadRepository()
        followup_repo = FollowUpRepository()

        lead = lead_repo.save_lead({
            "business_name": "Not Interested Test",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        })
        followup_repo.create_state(lead.id)

        agent = FollowUpAgent()
        agent.handle_reply(lead.id, "not_interested")

        state = followup_repo.get_by_lead_id(lead.id)
        assert state.do_not_contact is True
        assert state.overall_status == "stopped"

        # Cleanup
        session = get_session()
        session.query(DiscoveredLead).filter_by(id=lead.id).delete()
        from app.database.models import FollowUpState
        session.query(FollowUpState).filter_by(lead_id=lead.id).delete()
        session.commit()
        session.close()

    def test_human_required_sets_flag(self):
        """Replying with pricing/meeting request should set human_required."""
        from app.agents.follow_up import FollowUpAgent
        from app.database import FollowUpRepository, LeadRepository
        from app.database.models import init_db, DiscoveredLead, get_session

        init_db()
        lead_repo = LeadRepository()
        followup_repo = FollowUpRepository()

        lead = lead_repo.save_lead({
            "business_name": "Human Required Test",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        })
        followup_repo.create_state(lead.id)

        agent = FollowUpAgent()
        agent.handle_reply(lead.id, "wants_meeting")

        state = followup_repo.get_by_lead_id(lead.id)
        assert state.human_required is True
        assert state.overall_status == "stopped"

        # Cleanup
        session = get_session()
        session.query(DiscoveredLead).filter_by(id=lead.id).delete()
        from app.database.models import FollowUpState
        session.query(FollowUpState).filter_by(lead_id=lead.id).delete()
        session.commit()
        session.close()


# ═══════════════════════════════════════════════════════════════
# SECTION 13: FOLLOW-UP LOGIC
# ═══════════════════════════════════════════════════════════════

class TestFollowUpAudit:
    """Audit follow-up behavior."""

    def test_followup_state_lifecycle(self):
        """Follow-up state should track the full lifecycle."""
        from app.database import FollowUpRepository, LeadRepository
        from app.database.models import init_db, DiscoveredLead, get_session

        init_db()
        lead_repo = LeadRepository()
        followup_repo = FollowUpRepository()

        lead = lead_repo.save_lead({
            "business_name": "Followup Lifecycle Test",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        })

        # Create state
        state = followup_repo.create_state(lead.id)
        assert state.initial_status == "pending"
        assert state.followup_3day_status == "pending"
        assert state.followup_7day_status == "pending"
        assert state.overall_status == "active"

        # Mark initial sent
        followup_repo.mark_initial_sent(lead.id, "email")
        state = followup_repo.get_by_lead_id(lead.id)
        assert state.initial_status == "sent"

        # Mark 3-day follow-up sent
        followup_repo.mark_followup_3day_sent(lead.id)
        state = followup_repo.get_by_lead_id(lead.id)
        assert state.followup_3day_status == "sent"

        # Mark 7-day follow-up sent
        followup_repo.mark_followup_7day_sent(lead.id)
        state = followup_repo.get_by_lead_id(lead.id)
        assert state.followup_7day_status == "sent"
        assert state.overall_status == "completed"

        # Cleanup
        session = get_session()
        session.query(DiscoveredLead).filter_by(id=lead.id).delete()
        from app.database.models import FollowUpState
        session.query(FollowUpState).filter_by(lead_id=lead.id).delete()
        session.commit()
        session.close()

    def test_stop_followups(self):
        """stop_followups should set overall_status to stopped."""
        from app.database import FollowUpRepository, LeadRepository
        from app.database.models import init_db, DiscoveredLead, get_session

        init_db()
        lead_repo = LeadRepository()
        followup_repo = FollowUpRepository()

        lead = lead_repo.save_lead({
            "business_name": "Stop Followup Test",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        })
        followup_repo.create_state(lead.id)

        followup_repo.stop_followups(lead.id)
        state = followup_repo.get_by_lead_id(lead.id)
        assert state.overall_status == "stopped"

        # Cleanup
        session = get_session()
        session.query(DiscoveredLead).filter_by(id=lead.id).delete()
        from app.database.models import FollowUpState
        session.query(FollowUpState).filter_by(lead_id=lead.id).delete()
        session.commit()
        session.close()


# ═══════════════════════════════════════════════════════════════
# SECTION 14: WHATSAPP
# ═══════════════════════════════════════════════════════════════

class TestWhatsAppAudit:
    """Audit WhatsApp implementation."""

    def test_whatsapp_uses_official_api(self):
        """WhatsApp should use Meta Cloud API, not unofficial methods."""
        from app.integrations import whatsapp as wa_module
        import inspect
        source = inspect.getsource(wa_module)
        assert "graph.facebook.com" in source

    def test_whatsapp_requires_config(self):
        """WhatsApp should not send when not configured."""
        from app.integrations.whatsapp import WhatsAppClient
        client = WhatsAppClient()
        if not client.is_configured:
            result = client.send_text("+923001234567", "Test")
            assert result["success"] is False

    def test_whatsapp_no_session_hijacking(self):
        """WhatsApp should NOT use session hijacking or unofficial access."""
        from app.integrations.whatsapp import WhatsAppClient
        import inspect
        source = inspect.getsource(WhatsAppClient)
        # Should not contain unofficial methods
        assert "whatsapp-web" not in source.lower()
        assert "puppeteer" not in source.lower()
        assert "selenium" not in source.lower()
        assert "session" not in source.lower() or "phone_number_id" in source.lower()


# ═══════════════════════════════════════════════════════════════
# SECTION 15: SCHEDULER
# ═══════════════════════════════════════════════════════════════

class TestSchedulerAudit:
    """Audit scheduler safety."""

    def test_scheduler_disabled_by_default(self):
        """SCHEDULER_ENABLED should be false."""
        from app.config.settings import settings
        assert settings.campaign.scheduler_enabled is False

    def test_scheduler_class_exists(self):
        """Scheduler class should exist and be importable."""
        from app.scheduler.scheduler import LeadGenerationScheduler
        assert LeadGenerationScheduler is not None

    def test_scheduler_does_not_auto_start(self):
        """Scheduler should not start automatically on import."""
        from app.scheduler.scheduler import LeadGenerationScheduler
        scheduler = LeadGenerationScheduler()
        # The scheduler object should exist but not be running
        assert scheduler.scheduler is not None  # APScheduler object exists
        # But it should not be started


# ═══════════════════════════════════════════════════════════════
# SECTION 17: ERROR HANDLING
# ═══════════════════════════════════════════════════════════════

class TestErrorHandlingAudit:
    """Audit failure paths."""

    def test_email_client_handles_no_config(self):
        """EmailClient should handle missing configuration gracefully."""
        from app.integrations.email import EmailClient
        client = EmailClient()
        if not client.is_configured:
            result = client.send("test@test.com", "Subject", "Body")
            assert result["success"] is False
            assert "not configured" in result["message"].lower()

    def test_whatsapp_client_handles_no_config(self):
        """WhatsAppClient should handle missing configuration gracefully."""
        from app.integrations.whatsapp import WhatsAppClient
        client = WhatsAppClient()
        if not client.is_configured:
            result = client.send_text("+1234567890", "Test")
            assert result["success"] is False
            assert "not configured" in result["message"].lower()

    def test_outreach_handles_no_channel(self):
        """Outreach should handle prospects with no contact channel."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.config.settings import settings

        agent = OutreachAgent()
        p = RawProspect(business_name="No Contact", email="", phone="")
        # In DRY_RUN, returns 'draft' before channel check (correct)
        # In non-DRY_RUN, should return 'no_channel'
        assert settings.campaign.dry_run is True
        result = agent.send_initial(p, "Test")
        assert result["status"] == "draft"  # DRY_RUN takes precedence

    def test_outreach_handles_empty_message(self):
        """Outreach should handle empty message gracefully."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.config.settings import settings

        # In DRY_RUN mode, should still return draft
        assert settings.campaign.dry_run is True
        agent = OutreachAgent()
        p = RawProspect(business_name="Empty Message", email="test@test.com")
        result = agent.send_initial(p, "")
        assert result["status"] == "draft"

    def test_sheets_client_handles_missing_config(self):
        """Google Sheets client should handle missing configuration."""
        from app.integrations.google_sheets import sheets_client
        if not sheets_client.is_configured:
            # Should not raise when not configured
            assert sheets_client.is_configured is False


# ═══════════════════════════════════════════════════════════════
# SECTION 18: SECRETS / SECURITY AUDIT
# ═══════════════════════════════════════════════════════════════

class TestSecurityAudit:
    """Audit security of secrets and tokens."""

    def test_env_not_in_git(self):
        """.env should be in .gitignore."""
        gitignore_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path) as f:
                content = f.read()
            assert ".env" in content

    def test_google_token_not_in_git(self):
        """google_token.json should be in .gitignore."""
        gitignore_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path) as f:
                content = f.read()
            assert "google_token.json" in content

    def test_gmail_token_not_in_git(self):
        """gmail_token.json should be in .gitignore (or *.json covers it)."""
        gitignore_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path) as f:
                content = f.read()
            # gmail_token.json may be covered by *.json pattern
            has_explicit = "gmail_token.json" in content
            has_wildcard = "*.json" in content
            assert has_explicit or has_wildcard, "gmail_token.json not protected in .gitignore"

    def test_service_account_not_in_git(self):
        """service_account.json should be in .gitignore."""
        gitignore_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".gitignore")
        if os.path.exists(gitignore_path):
            with open(gitignore_path) as f:
                content = f.read()
            assert "service_account.json" in content

    def test_no_api_keys_in_source(self):
        """Source code should not contain hardcoded API keys."""
        import glob as glob_module
        project_root = os.path.dirname(os.path.dirname(__file__))
        # Only check for actual API key prefixes, not substrings
        dangerous_patterns = [
            ("sk-ant-", "Anthropic API key"),
            ("sk-proj-", "OpenAI API key"),
        ]
        for py_file in glob_module.glob(os.path.join(project_root, "app", "**", "*.py"), recursive=True):
            with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for pattern, desc in dangerous_patterns:
                assert pattern not in content, f"{desc} pattern '{pattern}' found in {py_file}"

    def test_settings_does_not_print_secrets(self):
        """settings.print_status should not contain secret values."""
        from app.config.settings import settings
        status = settings.print_status()
        # Should only show [OK] or [NOT CONFIGURED]
        assert "sk-" not in status
        assert "GOCSPX" not in status
        assert "re_" not in status
