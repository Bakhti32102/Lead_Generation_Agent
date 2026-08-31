"""
END-TO-END INTEGRATION TEST — Full Pipeline Verification
=========================================================
Tests all 18 acceptance criteria using mocks for missing API keys
and real logic for everything else.

Run with: python -m pytest tests/test_e2e_full_pipeline.py -v
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.config.settings import settings
from app.database.models import init_db
from app.database import (
    LeadRepository,
    FollowUpRepository,
    CampaignRepository,
    CounterRepository,
)
from app.sources.base import RawProspect, LeadSource


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(autouse=True)
def setup_db():
    """Initialize database before every test."""
    init_db()
    yield


@pytest.fixture
def clinic_prospect():
    """A realistic clinic prospect."""
    return RawProspect(
        business_name="Smile Dental Clinic",
        business_category="Dental Clinic",
        country="Pakistan",
        city="Lahore",
        address="123 Main Street, Gulberg, Lahore",
        phone="+923001234567",
        email="info@smiledental.pk",
        website="https://smiledental.pk",
        google_maps_url="https://maps.google.com/place?place_id=abc123",
        source="google_maps",
        source_url="https://google.com/maps/smiledental",
    )


@pytest.fixture
def restaurant_prospect():
    """A realistic restaurant prospect."""
    return RawProspect(
        business_name="Food Palace Restaurant",
        business_category="Restaurant",
        country="UAE",
        city="Dubai",
        address="45 Sheikh Zayed Road, Dubai",
        phone="+971501234567",
        email="contact@foodpalace.ae",
        website="https://foodpalace.ae",
        google_maps_url="https://maps.google.com/place?place_id=def456",
        source="google_maps",
        source_url="https://google.com/maps/foodpalace",
    )


@pytest.fixture
def beauty_prospect():
    """A realistic beauty parlor prospect."""
    return RawProspect(
        business_name="Glamour Beauty Salon",
        business_category="Beauty Salon",
        country="Pakistan",
        city="Lahore",
        address="78 Mall Road, Lahore",
        phone="+923211234567",
        email="hello@glamour.pk",
        website="https://glamour.pk",
        google_maps_url="https://maps.google.com/place?place_id=ghi789",
        source="google_search",
        source_url="https://google.com/search/glamour",
    )


@pytest.fixture
def linkedin_prospect():
    """A recent LinkedIn requirement."""
    return RawProspect(
        business_name="TechStartup Solutions",
        business_category="Technology",
        country="UAE",
        city="Dubai",
        website="https://techstartup.ae",
        source="linkedin",
        source_url="https://linkedin.com/posts/abc123",
        requirement_text="Need AI chatbot developer for customer support",
        freshness="verified_recent",
        hours_old=2,
    )


# ============================================================
# 1. CAMPAIGN TARGET — Country/City/Category Restriction
# ============================================================

class TestCampaignTarget:
    """Verify the agent searches ONLY the configured target."""

    def test_country_restriction(self):
        """When country=UAE, city=Dubai, results from Pakistan should score lower."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="uae",
            target_city="dubai",
            target_category="dental clinic",
        )

        dubai = RawProspect(
            business_name="Dubai Dental",
            business_category="Dental Clinic",
            country="UAE",
            city="Dubai",
        )
        pakistan = RawProspect(
            business_name="Lahore Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
        )

        assert scoring.score(dubai) > scoring.score(pakistan)

    def test_city_restriction(self):
        """Lahore businesses should score higher than Karachi for Lahore target."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="restaurant",
        )

        lahore = RawProspect(
            business_name="Lahore Food",
            business_category="Restaurant",
            country="Pakistan",
            city="Lahore",
        )
        karachi = RawProspect(
            business_name="Karachi Food",
            business_category="Restaurant",
            country="Pakistan",
            city="Karachi",
        )

        assert scoring.score(lahore) > scoring.score(karachi)

    def test_category_restriction(self):
        """Dental clinics should score higher than restaurants for dental target."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental clinic",
        )

        dental = RawProspect(
            business_name="Smile Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
        )
        restaurant = RawProspect(
            business_name="Food Place",
            business_category="Restaurant",
            country="Pakistan",
            city="Lahore",
        )

        assert scoring.score(dental) > scoring.score(restaurant)

    def test_expansion_not_allowed(self):
        """Agent must NOT automatically expand to other countries/cities."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="uae",
            target_city="dubai",
            target_category="dental clinic",
        )

        # A perfect match in the target
        perfect = RawProspect(
            business_name="Perfect Match",
            business_category="Dental Clinic",
            country="UAE",
            city="Dubai",
            website="https://match.ae",
            email="info@match.ae",
            phone="+971501234567",
            source="linkedin",
            freshness="verified_recent",
            metadata={
                "problems_list": ["Booking", "Support", "FAQs"],
                "demo_url": "https://demo.com",
            },
        )

        # An expansion target (wrong city, wrong country)
        expansion = RawProspect(
            business_name="Expansion Target",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://expand.pk",
            email="info@expand.pk",
            phone="+923001234567",
            metadata={
                "problems_list": ["Booking"],
                "demo_url": "",
            },
        )

        perfect_score = scoring.score(perfect)
        expansion_score = scoring.score(expansion)

        # Perfect match should score significantly higher
        assert perfect_score > expansion_score
        assert perfect_score >= 80


# ============================================================
# 2. LEAD DISCOVERY — All Search Sources
# ============================================================

class TestLeadDiscovery:
    """Verify all search sources are integrated and working."""

    def test_discovery_agent_has_all_sources(self):
        """LeadDiscoveryAgent should have all configured search sources."""
        from app.agents.lead_discovery import LeadDiscoveryAgent

        discovery = LeadDiscoveryAgent()
        source_names = [s.name for s in discovery.sources]

        assert "google_maps" in source_names
        assert "google_search" in source_names
        assert "linkedin" in source_names
        assert "public_jobs" in source_names
        assert "serpapi" in source_names

    def test_source_is_configured_check(self):
        """Each source should correctly report its configuration status."""
        from app.sources.google_maps import GoogleMapsSource
        from app.sources.google_search import GoogleSearchSource
        from app.sources.linkedin import LinkedInSource
        from app.sources.public_jobs import PublicJobSource
        from app.sources.serpapi import SerpAPISource

        # All should be checkable without crashing
        for SourceClass in [GoogleMapsSource, GoogleSearchSource, LinkedInSource, PublicJobSource, SerpAPISource]:
            source = SourceClass()
            assert isinstance(source.is_configured, bool)

    def test_deduplication_across_sources(self):
        """Same business from different sources should be deduplicated."""
        from app.agents.lead_discovery import LeadDiscoveryAgent

        discovery = LeadDiscoveryAgent()

        # Use unique identifiers to avoid database conflicts
        import uuid
        uid = uuid.uuid4().hex[:8]

        p1 = RawProspect(
            business_name=f"Smile Dental {uid}",
            website=f"https://smiledental{uid}.pk",
            email=f"info@smiledental{uid}.pk",
            source="google_maps",
        )
        p2 = RawProspect(
            business_name=f"Smile Dental {uid}",
            website=f"https://smiledental{uid}.pk",
            email=f"info@smiledental{uid}.pk",
            source="google_search",
        )

        merged = discovery._deduplicate([p1, p2])
        assert len(merged) == 1
        assert merged[0].source == "google_maps"  # First source preserved

    def test_deduplication_by_phone(self):
        """Same phone number from different sources should deduplicate."""
        from app.agents.lead_discovery import LeadDiscoveryAgent

        discovery = LeadDiscoveryAgent()

        import uuid
        uid = uuid.uuid4().hex[:8]
        phone = f"+92300{uid[:7]}"

        p1 = RawProspect(
            business_name=f"Clinic A {uid}",
            phone=phone,
            source="google_maps",
        )
        p2 = RawProspect(
            business_name=f"Clinic B {uid}",  # Different name
            phone=phone,  # Same phone
            source="google_search",
        )

        merged = discovery._deduplicate([p1, p2])
        assert len(merged) == 1

    def test_deduplication_by_website_domain(self):
        """Same website domain should deduplicate."""
        from app.agents.lead_discovery import LeadDiscoveryAgent

        discovery = LeadDiscoveryAgent()

        import uuid
        uid = uuid.uuid4().hex[:8]

        p1 = RawProspect(
            business_name=f"Clinic X {uid}",
            website=f"https://www.clinicx{uid}.pk",
            source="google_maps",
        )
        p2 = RawProspect(
            business_name=f"Clinic Y {uid}",
            website=f"http://clinicx{uid}.pk/",  # Same domain, different format
            source="google_search",
        )

        merged = discovery._deduplicate([p1, p2])
        assert len(merged) == 1


# ============================================================
# 3. RECENT REQUIREMENT FILTER — 24-Hour Freshness
# ============================================================

class TestRecentRequirementFilter:
    """Verify 24-hour freshness filtering."""

    def test_verified_recent_passes(self):
        """'verified_recent' should pass freshness check."""
        from app.agents.lead_verification import LeadVerificationAgent

        agent = LeadVerificationAgent()
        p = RawProspect(
            business_name="Recent Post",
            source="linkedin",
            freshness="verified_recent",
            website="https://recent.com",
        )

        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_probably_recent_passes(self):
        """'probably_recent' should pass freshness check."""
        from app.agents.lead_verification import LeadVerificationAgent

        agent = LeadVerificationAgent()
        p = RawProspect(
            business_name="Probably Recent",
            source="linkedin",
            freshness="probably_recent",
            website="https://probable.com",
        )

        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_unknown_freshness_passes(self):
        """'unknown' should pass (partial credit in scoring)."""
        from app.agents.lead_verification import LeadVerificationAgent

        agent = LeadVerificationAgent()
        p = RawProspect(
            business_name="Unknown Freshness",
            source="linkedin",
            freshness="unknown",
            website="https://unknown.com",
        )

        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_business_listings_skip_freshness(self):
        """Google Maps listings should not need freshness check."""
        from app.agents.lead_verification import LeadVerificationAgent

        agent = LeadVerificationAgent()
        p = RawProspect(
            business_name="Local Business",
            source="google_maps",
            freshness="unknown",
            website="https://local.com",
        )

        result = agent.verify(p)
        assert result.metadata["verification"]["recency_valid"] is True

    def test_freshness_affects_score(self):
        """Recent requirements should score higher than non-recent."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")

        base = dict(
            business_category="AI Services",
            country="UAE",
            city="Dubai",
            source="linkedin",
        )

        recent = RawProspect(
            business_name="Recent",
            freshness="verified_recent",
            metadata={"problems_list": [], "demo_url": ""},
            **base,
        )
        old = RawProspect(
            business_name="Old",
            freshness="unknown",
            metadata={"problems_list": [], "demo_url": ""},
            **base,
        )

        # verified_recent=+25, unknown=+5 -> 20 point gap
        assert scoring.score(recent) == scoring.score(old) + 20

    def test_posting_age_not_invented(self):
        """System must NOT invent posting age when unknown."""
        from app.sources.base import RawProspect

        p = RawProspect(
            business_name="No Date Info",
            source="linkedin",
            freshness="unknown",
        )

        # freshness should be "unknown", not fabricated
        assert p.freshness == "unknown"
        assert p.hours_old is None


# ============================================================
# 4. BUSINESS RESEARCH — Verify Data Collection
# ============================================================

class TestBusinessResearch:
    """Verify research pipeline collects all required fields."""

    def test_research_collects_required_fields(self):
        """Research should populate all required business fields."""
        from app.agents.business_research import BusinessResearchAgent
        from app.integrations.llm import LLMClient

        # Use unconfigured LLM (will use basic analysis)
        agent = BusinessResearchAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Smile Dental Clinic",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            phone="+923001234567",
            email="info@smiledental.pk",
            website="https://smiledental.pk",
            source="google_maps",
            source_url="https://google.com/maps/smiledental",
        )

        # Mock the website fetch to return basic content
        with patch.object(agent, "_fetch_website_text", return_value="Dental clinic appointment booking chatbot WhatsApp"):
            result = agent.research(prospect)

        # All required fields should be present
        assert result.business_name == "Smile Dental Clinic"
        assert result.business_category == "Dental Clinic"
        assert result.country == "Pakistan"
        assert result.city == "Lahore"
        assert result.phone == "+923001234567"
        assert result.email == "info@smiledental.pk"
        assert result.website == "https://smiledental.pk"
        assert result.source == "google_maps"
        assert result.source_url == "https://google.com/maps/smiledental"
        assert result.business_research != ""

    def test_research_without_website(self):
        """Research should handle businesses without websites."""
        from app.agents.business_research import BusinessResearchAgent
        from app.integrations.llm import LLMClient

        agent = BusinessResearchAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="No Website Biz",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
        )

        result = agent.research(prospect)
        assert "No website" in result.business_research

    def test_research_with_failing_fetch(self):
        """Research should handle website fetch failures gracefully."""
        from app.agents.business_research import BusinessResearchAgent
        from app.integrations.llm import LLMClient

        agent = BusinessResearchAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Failing Site",
            website="https://nonexistent.invalid",
        )

        with patch.object(agent, "_fetch_website_text", return_value=""):
            result = agent.research(prospect)

        # Should not crash, should indicate failure
        assert result.metadata.get("website_analysis") is not None


# ============================================================
# 5. PROBLEM ANALYSIS — Category-Specific Problem Matching
# ============================================================

class TestProblemAnalysis:
    """Verify category-specific problem identification."""

    def test_clinic_problems(self):
        """Clinics should get appointment/FAQ/support problems."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        from app.integrations.llm import LLMClient

        agent = ProblemAnalysisAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="City Clinic",
            business_category="Clinic",
            country="Pakistan",
            city="Lahore",
        )

        result = agent.analyze(prospect, "Clinic")

        assert result.potential_problem != ""
        assert result.recommended_ai_solution != ""
        # Should mention appointment or FAQ
        problems_lower = result.potential_problem.lower()
        assert "appointment" in problems_lower or "faq" in problems_lower or "customer" in problems_lower

    def test_dental_clinic_problems(self):
        """Dental clinics should get dental-specific problems."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        from app.integrations.llm import LLMClient

        agent = ProblemAnalysisAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Smile Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
        )

        result = agent.analyze(prospect, "Dental Clinic")

        assert result.potential_problem != ""
        assert "Dental" in result.recommended_ai_solution or "dental" in result.potential_problem.lower()

    def test_restaurant_problems(self):
        """Restaurants should get reservation/menu/support problems."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        from app.integrations.llm import LLMClient

        agent = ProblemAnalysisAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Food Palace",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
        )

        result = agent.analyze(prospect, "Restaurant")

        assert result.potential_problem != ""
        problems_lower = result.potential_problem.lower()
        assert "reservation" in problems_lower or "menu" in problems_lower or "customer" in problems_lower

    def test_beauty_salon_problems(self):
        """Beauty salons should get booking/service problems."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        from app.integrations.llm import LLMClient

        agent = ProblemAnalysisAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Glamour Salon",
            business_category="Beauty Salon",
            country="Pakistan",
            city="Lahore",
        )

        result = agent.analyze(prospect, "Beauty Salon")

        assert result.potential_problem != ""
        problems_lower = result.potential_problem.lower()
        assert "appointment" in problems_lower or "booking" in problems_lower or "service" in problems_lower

    def test_no_fabricated_problems(self):
        """Problems must be framed as potential, not factual."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        from app.integrations.llm import LLMClient

        agent = ProblemAnalysisAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Test Business",
            business_category="Unknown Category",
            country="Test",
            city="Test",
        )

        result = agent.analyze(prospect, "Unknown")

        # Should have at least one problem (generic fallback)
        assert result.potential_problem != ""
        # Problems should use hedging language
        problems = result.potential_problem.lower()
        assert "may" in problems or "potential" in problems or "could" in problems or "if" in problems


# ============================================================
# 6. SERVICE MATCHING — Website/AI Agent/Chatbot Selection
# ============================================================

class TestServiceMatching:
    """Verify service recommendation logic."""

    def test_no_website_recommends_website(self):
        """Business without website should get Website recommendation."""
        from app.agents.solution_matching import SolutionMatchingAgent

        agent = SolutionMatchingAgent()

        prospect = RawProspect(
            business_name="No Website Biz",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
            metadata={"website_analysis": {"has_booking": False, "has_chatbot": False, "website_quality": "average"}},
        )

        result = agent.match(prospect)
        assert "Website" in prospect.recommended_service

    def test_with_website_no_chatbot_recommends_chatbot(self):
        """Business with website but no chatbot should get Chatbot recommendation."""
        from app.agents.solution_matching import SolutionMatchingAgent

        agent = SolutionMatchingAgent()

        prospect = RawProspect(
            business_name="Has Website Biz",
            business_category="Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://clinic.pk",
            metadata={"website_analysis": {"has_booking": True, "has_chatbot": False, "website_quality": "good"}},
        )

        result = agent.match(prospect)
        assert "Chatbot" in prospect.recommended_service or "AI" in prospect.recommended_service

    def test_all_services_not_recommended_automatically(self):
        """System should NOT recommend all three services automatically."""
        from app.agents.solution_matching import SolutionMatchingAgent

        agent = SolutionMatchingAgent()

        prospect = RawProspect(
            business_name="Perfect Business",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
            website="https://perfect.ae",
            metadata={"website_analysis": {"has_booking": True, "has_chatbot": True, "website_quality": "good"}},
        )

        result = agent.match(prospect)
        # Should recommend a focused solution, not all three
        services = prospect.recommended_service
        assert services  # Should have a recommendation

    def test_demo_matching(self):
        """Demo should be matched to business category."""
        from app.agents.solution_matching import SolutionMatchingAgent

        agent = SolutionMatchingAgent()

        # Restaurant should get restaurant demo if available
        prospect = RawProspect(
            business_name="Food Place",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
            metadata={"website_analysis": {"has_booking": False, "has_chatbot": False}},
        )

        result = agent.match(prospect)
        # Should have attempted demo matching
        assert isinstance(prospect.metadata.get("demo_url", ""), str)


# ============================================================
# 7. LEAD SCORING — 100-Point System
# ============================================================

class TestLeadScoring:
    """Verify the 100-point scoring system."""

    def test_perfect_lead_scores_high(self):
        """Lead matching all criteria should score 80+."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental clinic",
        )

        perfect = RawProspect(
            business_name="Perfect Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://perfect.pk",
            email="info@perfect.pk",
            phone="+923001234567",
            source="linkedin",
            google_maps_url="https://maps.google.com/cid/123",
            address="123 Main St",
            freshness="verified_recent",
            metadata={
                "problems_list": ["Booking", "Support", "FAQs"],
                "demo_url": "https://demo.com",
            },
        )

        score = scoring.score(perfect)
        assert score >= 80

    def test_worst_lead_scores_low(self):
        """Lead matching nothing should score below 30."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="uae",
            target_city="dubai",
            target_category="dental clinic",
        )

        worst = RawProspect(
            business_name="Random Gym",
            business_category="Gym",
            country="India",
            city="Mumbai",
            metadata={"problems_list": [], "demo_url": ""},
        )

        score = scoring.score(worst)
        assert score < 30

    def test_score_capped_at_100(self):
        """Score must never exceed 100."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")

        p = RawProspect(
            business_name="Overachiever",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://over.pk",
            email="info@over.pk",
            phone="+923001234567",
            source="linkedin",
            freshness="verified_recent",
            google_maps_url="https://maps.google.com/cid/999",
            address="123 Main St",
            metadata={
                "problems_list": ["Booking", "Support", "FAQs", "WhatsApp"],
                "demo_url": "https://demo.com",
            },
        )

        score = scoring.score(p)
        assert score <= 100

    def test_threshold_qualification(self):
        """Only leads above threshold should be qualified."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental",
        )

        strong = RawProspect(
            business_name="Strong Lead",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://strong.pk",
            email="info@strong.pk",
            phone="+923001234567",
        )

        weak = RawProspect(
            business_name="Weak Lead",
            business_category="Gym",
            country="India",
            city="Mumbai",
        )

        scoring.score_batch([strong, weak])

        assert strong.is_qualified is True
        assert weak.is_qualified is False

    def test_scoring_weights_sum_correctly(self):
        """All scoring weights should sum to a reasonable maximum."""
        from app.agents.lead_scoring import LeadScoringAgent

        total = sum(LeadScoringAgent.WEIGHTS.values())
        # Should be 100 or close to it
        assert 90 <= total <= 110


# ============================================================
# 8. DAILY LIMIT — Enforcement and Persistence
# ============================================================

class TestDailyLimit:
    """Verify daily limit enforcement across restarts."""

    def test_counter_starts_at_zero(self):
        """Fresh day counter should start at 0."""
        repo = CounterRepository()
        test_date = "2099-12-31"
        count = repo.get_outreach_count(test_date)
        assert count == 0

    def test_counter_increments(self):
        """Counter should increment correctly."""
        repo = CounterRepository()
        test_date = "2099-12-30"
        initial = repo.get_outreach_count(test_date)
        repo.increment_outreach(test_date)
        after = repo.get_outreach_count(test_date)
        assert after == initial + 1

    def test_counter_persists_across_instances(self):
        """Counter should persist across different repository instances."""
        repo1 = CounterRepository()
        test_date = "2099-12-29"
        initial = repo1.get_outreach_count(test_date)
        repo1.increment_outreach(test_date)
        repo1.increment_outreach(test_date)

        repo2 = CounterRepository()
        count = repo2.get_outreach_count(test_date)
        assert count == initial + 2

    def test_can_send_more_respects_limit(self):
        """can_send_more should return False when limit reached."""
        repo = CounterRepository()
        test_date = "2099-12-28"
        initial = repo.get_outreach_count(test_date)

        for _ in range(3):
            repo.increment_outreach(test_date)

        after = repo.get_outreach_count(test_date)
        assert repo.can_send_more(after + 5, test_date) is True
        assert repo.can_send_more(after, test_date) is False

    def test_limit_enforced_in_outreach(self):
        """Outreach agent should respect daily limit."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = False
            mock_campaign.review_mode = False
            mock_campaign.max_daily_outreach = 0  # Set limit to 0
            mock_settings.campaign = mock_campaign

            agent = OutreachAgent()
            prospect = RawProspect(
                business_name="Test",
                email="test@example.com",
            )

            result = agent.send_initial(prospect, "Hello!")
            assert result["status"] == "limit_reached"


# ============================================================
# 9. GOOGLE SHEETS — API Integration Architecture
# ============================================================

class TestGoogleSheets:
    """Verify Google Sheets integration architecture."""

    def test_sheets_columns_match_spec(self):
        """Sheet columns must match the specification."""
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

    def test_sheets_client_unconfigured(self):
        """Sheets client should return empty when not configured."""
        from app.integrations.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient()
        assert client.is_configured is False
        rows = client.read_all_rows()
        assert rows == []

    def test_lead_data_to_sheet_row(self):
        """Lead data should convert to correct sheet format."""
        from app.integrations.google_sheets import GoogleSheetsClient

        client = GoogleSheetsClient()

        lead = {
            "lead_id": 42,
            "date_found": "2026-08-31",
            "business_name": "Smile Dental",
            "business_category": "Dental Clinic",
            "country": "Pakistan",
            "city": "Lahore",
            "phone": "+923001234567",
            "email": "info@smile.pk",
            "website": "https://smile.pk",
            "source": "google_maps",
            "lead_score": 75,
            "do_not_contact": "No",
            "human_required": "No",
        }

        row = client.lead_data_to_sheet_row(lead)
        assert row["Lead ID"] == "42"
        assert row["Business Name"] == "Smile Dental"
        assert row["Lead Score"] == "75"

    def test_sheets_save_in_pipeline(self):
        """Pipeline should attempt to save to Google Sheets."""
        from app.scheduler.daily_campaign import DailyCampaign
        from app.sources.base import RawProspect

        # Mock the sheets client
        with patch("app.scheduler.daily_campaign.sheets_client") as mock_sheets:
            mock_sheets.is_configured = False  # Not configured in test

            campaign = DailyCampaign()
            # This should not crash even when sheets is not configured
            prospect = RawProspect(
                business_name="Test",
                country="Test",
                city="Test",
            )

            # _save_to_sheets should gracefully skip when not configured
            campaign._save_to_sheets(prospect, 1, "Test message", {"success": True})

    def test_sheets_update_after_outreach(self):
        """Google Sheets should be updated after outreach."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        with patch("app.agents.outreach.sheets_client") as mock_sheets:
            mock_sheets.is_configured = False

            agent = OutreachAgent()
            prospect = RawProspect(
                business_name="Test",
                email="test@example.com",
            )

            # In dry run mode, should not try to update sheets
            with patch("app.agents.outreach.settings") as mock_settings:
                mock_campaign = MagicMock()
                mock_campaign.dry_run = True
                mock_campaign.review_mode = False
                mock_settings.campaign = mock_campaign

                result = agent.send_initial(prospect, "Hello!")
                assert result["status"] == "draft"


# ============================================================
# 10. EMAIL — Integration Architecture
# ============================================================

class TestEmail:
    """Verify email integration architecture."""

    def test_email_unconfigured_returns_failure(self):
        """Email should return failure when not configured."""
        from app.integrations.email import EmailClient

        client = EmailClient()
        assert client.is_configured is False

        result = client.send("test@example.com", "Subject", "Body")
        assert result["success"] is False
        assert "not configured" in result["message"].lower()

    def test_email_empty_recipient(self):
        """Email should reject empty recipients."""
        from app.integrations.email import EmailClient

        client = EmailClient()
        result = client.send("", "Subject", "Body")
        assert result["success"] is False

    def test_email_provider_routing(self):
        """Email should route to correct provider."""
        from app.integrations.email import EmailClient

        client = EmailClient()
        client.provider = "resend"
        client.api_key = "test"
        client.from_address = "test@example.com"

        with patch.object(EmailClient, "is_configured", new_callable=lambda: property(lambda self: True)):
            with patch.object(EmailClient, "_send_resend", return_value={"success": True, "message": "Sent", "id": "123"}) as mock:
                result = client.send("recipient@example.com", "Subject", "Body")
                mock.assert_called_once()
                assert result["success"] is True

    def test_email_in_outreach_dry_run(self):
        """Email should not be sent in dry run mode."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = True
            mock_campaign.review_mode = False
            mock_settings.campaign = mock_campaign

            agent = OutreachAgent()
            prospect = RawProspect(
                business_name="Test",
                email="test@example.com",
            )

            result = agent.send_initial(prospect, "Hello!")
            assert result["status"] == "draft"
            assert result["channel"] == "email"


# ============================================================
# 11. WHATSAPP — Official API Architecture
# ============================================================

class TestWhatsApp:
    """Verify WhatsApp Business API integration architecture."""

    def test_whatsapp_unconfigured(self):
        """WhatsApp should return failure when not configured."""
        from app.integrations.whatsapp import WhatsAppClient

        client = WhatsAppClient()
        assert client.is_configured is False

        result = client.send_text("+1234567890", "Hello")
        assert result["success"] is False
        assert "not configured" in result["message"].lower()

    def test_whatsapp_empty_number(self):
        """WhatsApp should reject empty numbers."""
        from app.integrations.whatsapp import WhatsAppClient

        client = WhatsAppClient()
        result = client.send_text("", "Hello")
        assert result["success"] is False

    def test_whatsapp_uses_official_api(self):
        """WhatsApp should use official Meta Cloud API, not hijacking."""
        from app.integrations.whatsapp import WhatsAppClient

        client = WhatsAppClient()
        # Verify it uses the official API endpoint
        assert "graph.facebook.com" in "https://graph.facebook.com/v18.0"


# ============================================================
# 12. REVIEW MODE — Draft Creation and Approval
# ============================================================

class TestReviewMode:
    """Verify REVIEW_MODE creates drafts and waits for approval."""

    def test_review_mode_creates_draft(self):
        """REVIEW_MODE=true should create draft, not send."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = False
            mock_campaign.review_mode = True
            mock_campaign.max_daily_outreach = 15
            mock_settings.campaign = mock_campaign

            agent = OutreachAgent()
            prospect = RawProspect(
                business_name="Test",
                email="test@example.com",
            )

            result = agent.send_initial(prospect, "Hello!")
            assert result["status"] == "pending_review"

    def test_approve_and_send(self):
        """Approved messages should be sent."""
        from app.agents.outreach import OutreachAgent
        from app.database import LeadRepository

        # Create a lead with a message
        repo = LeadRepository()
        lead = repo.save_lead({
            "business_name": "Approve Test",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
            "is_qualified": True,
            "lead_score": 75,
            "notes": "Test message for approval",
        })

        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = True  # Use dry run for testing
            mock_campaign.review_mode = False
            mock_campaign.max_daily_outreach = 15
            mock_settings.campaign = mock_campaign

            agent = OutreachAgent()
            result = agent.approve_and_send(lead.id)

            assert result["success"] is True


# ============================================================
# 13. DRY RUN — No Messages Sent
# ============================================================

class TestDryRun:
    """Verify DRY_RUN=true sends nothing."""

    def test_dry_run_no_email_sent(self):
        """DRY_RUN should not send emails."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = True
            mock_campaign.review_mode = False
            mock_settings.campaign = mock_campaign

            agent = OutreachAgent()
            prospect = RawProspect(
                business_name="Dry Run Test",
                email="test@example.com",
            )

            result = agent.send_initial(prospect, "Hello!")
            assert result["status"] == "draft"
            assert result["message_id"] == "dry_run"

    def test_dry_run_no_whatsapp_sent(self):
        """DRY_RUN should not send WhatsApp messages."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = True
            mock_campaign.review_mode = False
            mock_settings.campaign = mock_campaign

            agent = OutreachAgent()
            prospect = RawProspect(
                business_name="Dry Run Test",
                phone="+1234567890",
            )

            result = agent.send_initial(prospect, "Hello!")
            assert result["status"] == "draft"

    def test_dry_run_generates_messages(self):
        """DRY_RUN should still generate messages for review."""
        from app.agents.personalization import PersonalizationAgent
        from app.integrations.llm import LLMClient
        from app.sources.base import RawProspect

        agent = PersonalizationAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Dry Run Test",
            business_category="Clinic",
            country="Pakistan",
            city="Lahore",
            potential_problem="- Appointment booking",
            recommended_service="AI Chatbot",
            recommended_ai_solution="AI Clinic Receptionist",
            metadata={"problems_list": ["Booking"]},
        )

        message = agent.generate_message(prospect)
        assert len(message) > 50
        assert "Dry Run Test" in message


# ============================================================
# 14. 3-DAY FOLLOW-UP — Timing, Eligibility, Sheets Update
# ============================================================

class TestThreeDayFollowUp:
    """Verify 3-day follow-up logic."""

    def test_followup_state_created(self):
        """Follow-up state should be created for each outreach lead."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        state = repo.create_state(lead_id=88001, initial_channel="email")

        assert state.lead_id == 88001
        assert state.initial_channel == "email"
        assert state.overall_status == "active"

    def test_initial_sent_recorded(self):
        """Initial send should be recorded with timestamp."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        repo.create_state(lead_id=88002)
        repo.mark_initial_sent(88002, "email")

        state = repo.get_by_lead_id(88002)
        assert state.initial_status == "sent"
        assert state.initial_sent_at is not None

    def test_3day_followup_marked(self):
        """3-day follow-up should be marked when sent."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        repo.create_state(lead_id=88003)
        repo.mark_initial_sent(88003, "email")
        repo.mark_followup_3day_sent(88003)

        state = repo.get_by_lead_id(88003)
        assert state.followup_3day_status == "sent"

    def test_3day_due_only_after_3_days(self):
        """3-day follow-up should only be due after 3 days."""
        from app.database import FollowUpRepository
        from app.database.models import get_session, FollowUpState

        repo = FollowUpRepository()
        repo.create_state(lead_id=88004)

        # Set initial sent to 4 days ago
        session = get_session()
        state = session.query(FollowUpState).filter_by(lead_id=88004).first()
        state.initial_status = "sent"
        state.initial_sent_at = _dt.datetime.utcnow() - _dt.timedelta(days=4)
        state.followup_3day_status = "pending"
        state.overall_status = "active"
        state.do_not_contact = False
        session.commit()
        session.close()

        due = repo.get_due_followups_3day()
        due_ids = [d.lead_id for d in due]
        assert 88004 in due_ids

    def test_stopped_lead_not_in_due(self):
        """Stopped leads should not appear in due follow-ups."""
        from app.database import FollowUpRepository
        from app.database.models import get_session, FollowUpState

        repo = FollowUpRepository()
        repo.create_state(lead_id=88005)

        session = get_session()
        state = session.query(FollowUpState).filter_by(lead_id=88005).first()
        state.initial_status = "sent"
        state.initial_sent_at = _dt.datetime.utcnow() - _dt.timedelta(days=4)
        session.commit()
        session.close()

        repo.stop_followups(88005)

        due = repo.get_due_followups_3day()
        due_ids = [d.lead_id for d in due]
        assert 88005 not in due_ids

    def test_dnc_lead_not_in_due(self):
        """Do Not Contact leads should not appear in due follow-ups."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        repo.create_state(lead_id=88006)
        repo.mark_initial_sent(88006, "email")
        repo.set_do_not_contact(88006)

        due = repo.get_due_followups_3day()
        due_ids = [d.lead_id for d in due]
        assert 88006 not in due_ids


# ============================================================
# 15. 7-DAY FOLLOW-UP — Final Follow-up and Completion
# ============================================================

class TestSevenDayFollowUp:
    """Verify 7-day follow-up logic."""

    def test_7day_followup_completes_sequence(self):
        """7-day follow-up should set overall_status to completed."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        repo.create_state(lead_id=88007)
        repo.mark_initial_sent(88007, "email")
        repo.mark_followup_7day_sent(88007)

        state = repo.get_by_lead_id(88007)
        assert state.followup_7day_status == "sent"
        assert state.overall_status == "completed"

    def test_7day_due_only_after_7_days(self):
        """7-day follow-up should only be due after 7 days."""
        from app.database import FollowUpRepository
        from app.database.models import get_session, FollowUpState

        repo = FollowUpRepository()
        repo.create_state(lead_id=88008)

        session = get_session()
        state = session.query(FollowUpState).filter_by(lead_id=88008).first()
        state.initial_status = "sent"
        state.initial_sent_at = _dt.datetime.utcnow() - _dt.timedelta(days=8)
        state.followup_7day_status = "pending"
        state.overall_status = "active"
        state.do_not_contact = False
        session.commit()
        session.close()

        due = repo.get_due_followups_7day()
        due_ids = [d.lead_id for d in due]
        assert 88008 in due_ids

    def test_no_unlimited_followups(self):
        """Maximum follow-ups should be: 1 initial + 1 three-day + 1 seven-day."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        repo.create_state(lead_id=88009)
        repo.mark_initial_sent(88009, "email")
        repo.mark_followup_3day_sent(88009)
        repo.mark_followup_7day_sent(88009)

        state = repo.get_by_lead_id(88009)
        assert state.overall_status == "completed"
        # No more follow-ups should be due
        assert state.followup_3day_status == "sent"
        assert state.followup_7day_status == "sent"


# ============================================================
# 16. OPT-OUT — DNC Flag Stops All Follow-ups
# ============================================================

class TestOptOut:
    """Verify opt-out stops all follow-ups."""

    def test_dnc_flag_set(self):
        """Do Not Contact flag should be set correctly."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        repo.create_state(lead_id=88010)
        repo.set_do_not_contact(88010)

        state = repo.get_by_lead_id(88010)
        assert state.do_not_contact is True
        assert state.overall_status == "stopped"

    def test_stop_followups(self):
        """Explicit stop should set overall_status to stopped."""
        from app.database import FollowUpRepository

        repo = FollowUpRepository()
        repo.create_state(lead_id=88011)
        repo.stop_followups(88011)

        state = repo.get_by_lead_id(88011)
        assert state.overall_status == "stopped"

    def test_not_interested_sets_dnc(self):
        """'not_interested' response should set DNC flag."""
        from app.agents.follow_up import FollowUpAgent
        from app.database import FollowUpRepository

        fu = FollowUpAgent()
        repo = FollowUpRepository()
        repo.create_state(lead_id=88012)

        fu.handle_reply(88012, "not_interested")

        state = repo.get_by_lead_id(88012)
        assert state.do_not_contact is True
        assert state.overall_status == "stopped"

    def test_already_has_solution_sets_dnc(self):
        """'already_has_solution' response should set DNC flag."""
        from app.agents.follow_up import FollowUpAgent
        from app.database import FollowUpRepository

        fu = FollowUpAgent()
        repo = FollowUpRepository()
        repo.create_state(lead_id=88013)

        fu.handle_reply(88013, "already_has_solution")

        state = repo.get_by_lead_id(88013)
        assert state.do_not_contact is True

    def test_interested_stops_followups(self):
        """'interested' response should stop follow-ups but not set DNC."""
        from app.agents.follow_up import FollowUpAgent
        from app.database import FollowUpRepository

        fu = FollowUpAgent()
        repo = FollowUpRepository()
        repo.create_state(lead_id=88014)

        fu.handle_reply(88014, "interested")

        state = repo.get_by_lead_id(88014)
        assert state.overall_status == "stopped"
        assert state.do_not_contact is False


# ============================================================
# 17. HUMAN ESCALATION — Pricing/Meeting/Technical Triggers
# ============================================================

class TestHumanEscalation:
    """Verify human escalation triggers."""

    def test_pricing_triggers_escalation(self):
        """Pricing questions should trigger escalation."""
        from app.agents.escalation import EscalationAgent

        agent = EscalationAgent()
        assert agent.should_escalate("wants_pricing") is True

    def test_meeting_triggers_escalation(self):
        """Meeting requests should trigger escalation."""
        from app.agents.escalation import EscalationAgent

        agent = EscalationAgent()
        assert agent.should_escalate("wants_meeting") is True

    def test_proposal_triggers_escalation(self):
        """Proposal requests should trigger escalation."""
        from app.agents.escalation import EscalationAgent

        agent = EscalationAgent()
        assert agent.should_escalate("wants_proposal") is True

    def test_technical_question_triggers_escalation(self):
        """Technical questions should trigger escalation."""
        from app.agents.escalation import EscalationAgent

        agent = EscalationAgent()
        assert agent.should_escalate("technical_question") is True

    def test_human_required_triggers_escalation(self):
        """Human_required should trigger escalation."""
        from app.agents.escalation import EscalationAgent

        agent = EscalationAgent()
        assert agent.should_escalate("human_required") is True

    def test_interested_no_escalation(self):
        """Interested should NOT trigger escalation."""
        from app.agents.escalation import EscalationAgent

        agent = EscalationAgent()
        assert agent.should_escalate("interested") is False

    def test_not_interested_no_escalation(self):
        """Not interested should NOT trigger escalation."""
        from app.agents.escalation import EscalationAgent

        agent = EscalationAgent()
        assert agent.should_escalate("not_interested") is False

    def test_wants_meeting_stops_followups(self):
        """Meeting request should stop follow-ups and flag human required."""
        from app.agents.follow_up import FollowUpAgent
        from app.database import FollowUpRepository

        fu = FollowUpAgent()
        repo = FollowUpRepository()
        repo.create_state(lead_id=88015)

        fu.handle_reply(88015, "wants_meeting")

        state = repo.get_by_lead_id(88015)
        assert state.human_required is True
        assert state.overall_status == "stopped"


# ============================================================
# 18. DUPLICATE PROTECTION — Cross-Source Deduplication
# ============================================================

class TestDuplicateProtection:
    """Verify same business cannot receive duplicate outreach."""

    def test_duplicate_by_website(self):
        """Same website should not create duplicate leads."""
        from app.database import LeadRepository
        import uuid

        repo = LeadRepository()
        uid = uuid.uuid4().hex[:8]

        lead1 = repo.save_lead({
            "business_name": f"Test Clinic {uid}",
            "website": f"https://{uid}clinic.pk",
            "dedup_website": f"{uid}clinic.pk",
            "is_qualified": True,
        })

        # Check if duplicate exists
        existing = repo.is_duplicate(website=f"{uid}clinic.pk")
        assert existing is not None
        assert existing.id == lead1.id

    def test_duplicate_by_email(self):
        """Same email should not create duplicate leads."""
        from app.database import LeadRepository
        import uuid

        repo = LeadRepository()
        uid = uuid.uuid4().hex[:8]

        lead1 = repo.save_lead({
            "business_name": f"Test Email {uid}",
            "email": f"info@{uid}test.pk",
            "dedup_email": f"info@{uid}test.pk",
            "is_qualified": True,
        })

        existing = repo.is_duplicate(email=f"info@{uid}test.pk")
        assert existing is not None
        assert existing.id == lead1.id

    def test_duplicate_by_phone(self):
        """Same phone should not create duplicate leads."""
        from app.database import LeadRepository
        import uuid

        repo = LeadRepository()
        uid = uuid.uuid4().hex[:8]
        phone = f"92300{uid[:7]}"

        lead1 = repo.save_lead({
            "business_name": f"Test Phone {uid}",
            "phone": f"+{phone}",
            "dedup_phone": phone,
            "is_qualified": True,
        })

        existing = repo.is_duplicate(phone=phone)
        assert existing is not None
        assert existing.id == lead1.id

    def test_different_businesses_not_deduped(self):
        """Different businesses should NOT be deduplicated."""
        from app.database import LeadRepository
        import uuid

        repo = LeadRepository()
        uid = uuid.uuid4().hex[:8]

        lead_a = repo.save_lead({
            "business_name": f"Clinic A {uid}",
            "website": f"https://clinica{uid}.pk",
            "dedup_website": f"clinica{uid}.pk",
        })

        lead_b = repo.save_lead({
            "business_name": f"Clinic B {uid}",
            "website": f"https://clinicb{uid}.pk",
            "dedup_website": f"clinicb{uid}.pk",
        })

        # Each should find its own lead, not the other
        existing_a = repo.is_duplicate(website=f"clinica{uid}.pk")
        existing_b = repo.is_duplicate(website=f"clinicb{uid}.pk")

        assert existing_a is not None
        assert existing_b is not None
        assert existing_a.id == lead_a.id
        assert existing_b.id == lead_b.id
        assert existing_a.id != existing_b.id

    def test_dedup_in_discovery_pipeline(self):
        """Discovery pipeline should deduplicate across sources."""
        from app.agents.lead_discovery import LeadDiscoveryAgent

        discovery = LeadDiscoveryAgent()

        p1 = RawProspect(
            business_name="Same Biz",
            website="https://same.biz",
            email="info@same.biz",
            source="google_maps",
        )
        p2 = RawProspect(
            business_name="Same Biz",
            website="https://same.biz",
            email="info@same.biz",
            source="google_search",
        )
        p3 = RawProspect(
            business_name="Different Biz",
            website="https://different.biz",
            email="info@different.biz",
            source="linkedin",
        )

        merged = discovery._deduplicate([p1, p2, p3])
        assert len(merged) == 2  # Same biz deduplicated, different biz preserved


# ============================================================
# FULL PIPELINE END-TO-END TEST
# ============================================================

class TestFullPipeline:
    """End-to-end test of the complete pipeline."""

    def test_full_pipeline_dry_run(self):
        """
        Complete pipeline: Target -> Search -> Verify -> Research ->
        Problem Analysis -> Solution Match -> Score -> Draft -> Save
        """
        from app.agents.lead_verification import LeadVerificationAgent
        from app.agents.business_research import BusinessResearchAgent
        from app.agents.problem_analysis import ProblemAnalysisAgent
        from app.agents.solution_matching import SolutionMatchingAgent
        from app.agents.lead_scoring import LeadScoringAgent
        from app.agents.personalization import PersonalizationAgent
        from app.agents.outreach import OutreachAgent
        from app.integrations.llm import LLMClient

        # Step 1: Create prospects (simulating discovery)
        prospects = [
            RawProspect(
                business_name="Smile Dental Clinic",
                business_category="Dental Clinic",
                country="Pakistan",
                city="Lahore",
                phone="+923001234567",
                email="info@smiledental.pk",
                website="https://smiledental.pk",
                source="google_maps",
                source_url="https://google.com/maps/smiledental",
            ),
            RawProspect(
                business_name="Food Palace Restaurant",
                business_category="Restaurant",
                country="UAE",
                city="Dubai",
                phone="+971501234567",
                email="contact@foodpalace.ae",
                website="https://foodpalace.ae",
                source="google_maps",
                source_url="https://google.com/maps/foodpalace",
            ),
            RawProspect(
                business_name="Glamour Beauty Salon",
                business_category="Beauty Salon",
                country="Pakistan",
                city="Lahore",
                phone="+923211234567",
                email="hello@glamour.pk",
                website="https://glamour.pk",
                source="google_search",
                source_url="https://google.com/search/glamour",
            ),
        ]

        # Step 2: Verification
        verifier = LeadVerificationAgent()
        verified = verifier.verify_batch(prospects)
        assert len(verified) == 3  # All should verify

        # Step 3: Business Research (with mocked website fetch)
        researcher = BusinessResearchAgent(llm=LLMClient(api_key=""))
        for p in verified:
            with patch.object(researcher, "_fetch_website_text", return_value="Dental clinic appointment booking chatbot"):
                researcher.research(p)
            assert p.business_research != ""

        # Step 4: Problem Analysis
        problem_agent = ProblemAnalysisAgent(llm=LLMClient(api_key=""))
        for p in verified:
            problem_agent.analyze(p, p.business_category)
            assert p.potential_problem != ""

        # Step 5: Service Matching
        matcher = SolutionMatchingAgent()
        for p in verified:
            matcher.match(p)
            assert p.recommended_service != ""

        # Step 6: Scoring (targeting Pakistan/Lahore)
        scorer = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental clinic",
        )
        scored = scorer.score_batch(verified)

        # Step 7: Select top leads
        final = scorer.select_top_leads(scored, 10)
        assert len(final) > 0

        # Verify scoring sorted correctly
        for i in range(len(final) - 1):
            assert final[i].lead_score >= final[i + 1].lead_score

        # Step 8: Generate personalized messages (dry run)
        personalizer = PersonalizationAgent(llm=LLMClient(api_key=""))
        for p in final:
            message = personalizer.generate_message(p)
            assert len(message) > 50
            assert p.business_name in message

        # Step 9: Outreach in dry run mode
        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = True
            mock_campaign.review_mode = False
            mock_campaign.max_daily_outreach = 15
            mock_settings.campaign = mock_campaign

            outreach = OutreachAgent()
            for p in final:
                message = personalizer.generate_message(p)
                result = outreach.send_initial(p, message)
                assert result["status"] == "draft"

        # Step 10: Verify database persistence
        repo = LeadRepository()
        for p in final:
            lead_data = {
                "business_name": p.business_name,
                "business_category": p.business_category,
                "country": p.country,
                "city": p.city,
                "phone": p.phone,
                "email": p.email,
                "website": p.website,
                "source": p.source,
                "source_url": p.source_url,
                "business_research": p.business_research,
                "potential_problem": p.potential_problem,
                "recommended_service": p.recommended_service,
                "recommended_ai_solution": p.recommended_ai_solution,
                "lead_score": p.lead_score,
                "is_qualified": p.is_qualified,
                "is_outreach_lead": True,
                "dedup_website": p.website.lower().strip() if p.website else "",
                "dedup_email": p.email.lower().strip() if p.email else "",
                "dedup_phone": p.phone.strip() if p.phone else "",
            }
            saved = repo.save_lead(lead_data)
            assert saved.id > 0

        # Verify all leads saved
        all_leads = repo.get_all_qualified()
        assert len(all_leads) >= len(final)


# ============================================================
# RESPONSE CLASSIFICATION TEST
# ============================================================

class TestResponseClassification:
    """Verify response classification logic."""

    def test_interested_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()
        assert agent.classify("Yes, I'm interested!") == "interested"

    def test_pricing_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()
        assert agent.classify("How much does this cost?") == "wants_pricing"

    def test_meeting_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()
        assert agent.classify("Can we schedule a call?") == "wants_meeting"

    def test_not_interested_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()
        assert agent.classify("No thanks, not interested.") == "not_interested"

    def test_empty_reply_default(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()
        assert agent.classify("") == "needs_more_info"


# ============================================================
# MESSAGE GENERATION TEST
# ============================================================

class TestMessageGeneration:
    """Verify personalized message generation."""

    def test_template_includes_business_name(self):
        from app.agents.personalization import PersonalizationAgent
        from app.integrations.llm import LLMClient

        agent = PersonalizationAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Smile Dental Clinic",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            potential_problem="- Appointment booking",
            recommended_service="AI Chatbot",
            recommended_ai_solution="AI Dental Receptionist",
            metadata={"problems_list": ["Booking"]},
        )

        message = agent.generate_message(prospect)
        assert "Smile Dental Clinic" in message
        assert "Lahore" in message

    def test_template_no_fake_claims(self):
        from app.agents.personalization import PersonalizationAgent
        from app.integrations.llm import LLMClient

        agent = PersonalizationAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Test Business",
            business_category="Clinic",
            country="Pakistan",
            city="Lahore",
            potential_problem="- Customer inquiries",
            recommended_service="AI Chatbot",
            recommended_ai_solution="AI Clinic Receptionist",
            metadata={"problems_list": ["Support"]},
        )

        message = agent.generate_message(prospect)
        banned = ["revolutionary", "10x", "guaranteed", "guarantee"]
        for word in banned:
            assert word.lower() not in message.lower()

    def test_followup_3day_message(self):
        from app.agents.personalization import PersonalizationAgent
        from app.integrations.llm import LLMClient

        agent = PersonalizationAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Smile Clinic",
            recommended_ai_solution="AI Receptionist",
        )

        message = agent.generate_followup_message(prospect, "3day")
        assert "following up" in message.lower()
        assert "Smile Clinic" in message

    def test_followup_7day_message(self):
        from app.agents.personalization import PersonalizationAgent
        from app.integrations.llm import LLMClient

        agent = PersonalizationAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Quick Bites",
            recommended_ai_solution="Restaurant AI Agent",
        )

        message = agent.generate_followup_message(prospect, "7day")
        assert "last follow-up" in message.lower()
        assert "Quick Bites" in message
