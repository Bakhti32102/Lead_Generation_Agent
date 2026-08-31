"""Tests for the lead scoring system."""

import pytest

from app.sources.base import RawProspect
from app.agents.lead_scoring import LeadScoringAgent


class TestLeadScoring:
    """Tests for the 100-point scoring system."""

    def _make_prospect(self, **kwargs):
        defaults = {
            "business_name": "Test Business",
            "business_category": "Dental Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        }
        defaults.update(kwargs)
        return RawProspect(**defaults)

    def test_category_match_adds_points(self):
        """Matching category should add +15 points."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )
        match = self._make_prospect(business_category="Dental Clinic")
        no_match = self._make_prospect(business_category="Restaurant")

        assert scoring.score(match) > scoring.score(no_match)

    def test_location_match_adds_points(self):
        """Matching city+country should add +10 points."""
        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental",
        )
        match = self._make_prospect(country="Pakistan", city="Lahore")
        no_match = self._make_prospect(country="UAE", city="Dubai")

        assert scoring.score(match) > scoring.score(no_match)

    def test_recent_requirement_adds_points(self):
        """Recent requirement source should add significant points."""
        scoring = LeadScoringAgent(target_country="uae", target_city="dubai", target_category="ai")

        recent = self._make_prospect(
            source="linkedin",
            freshness="verified_recent",
            metadata={"problems_list": ["Need chatbot"], "demo_url": "https://demo.com"},
        )
        not_recent = self._make_prospect(
            source="google_maps",
            metadata={"problems_list": [], "demo_url": ""},
        )

        assert scoring.score(recent) > scoring.score(not_recent)

    def test_email_adds_points(self):
        """Having an email should add +10 points."""
        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")
        with_email = self._make_prospect(email="info@clinic.com")
        without_email = self._make_prospect(email="")

        assert scoring.score(with_email) > scoring.score(without_email)

    def test_phone_adds_points(self):
        """Having a phone should add +10 points."""
        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")
        with_phone = self._make_prospect(phone="+923001234567")
        without_phone = self._make_prospect(phone="")

        assert scoring.score(with_phone) > scoring.score(without_phone)

    def test_website_adds_points(self):
        """Having a website should add +5 points."""
        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")
        with_site = self._make_prospect(website="https://clinic.com")
        without_site = self._make_prospect(website="")

        assert scoring.score(with_site) > scoring.score(without_site)

    def test_automation_opportunity_adds_points(self):
        """Having automation problems listed should add +10-20 points."""
        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")
        with_problems = self._make_prospect(
            metadata={"problems_list": ["Booking", "Customer support", "FAQs"]}
        )
        without_problems = self._make_prospect(
            metadata={"problems_list": []}
        )

        assert scoring.score(with_problems) > scoring.score(without_problems)

    def test_perfect_lead_scores_high(self):
        """A lead matching all criteria should score 80+."""
        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental clinic",
        )

        perfect = self._make_prospect(
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://smiledental.pk",
            email="info@smiledental.pk",
            phone="+923001234567",
            source="linkedin",
            google_maps_url="https://maps.google.com/cid/123",
            address="123 Main St",
            freshness="verified_recent",
            metadata={
                "problems_list": ["Appointment booking", "Customer inquiries", "WhatsApp"],
                "demo_url": "https://demo.example.com",
            },
        )

        score = scoring.score(perfect)
        assert score >= 80

    def test_worst_lead_scores_low(self):
        """A lead matching nothing should score below 30."""
        scoring = LeadScoringAgent(
            target_country="uae",
            target_city="dubai",
            target_category="dental clinic",
        )

        worst = self._make_prospect(
            business_name="Random Gym",
            business_category="Gym",
            country="India",
            city="Mumbai",
            website="",
            email="",
            phone="",
            source="google_search",
            metadata={"problems_list": [], "demo_url": ""},
        )

        score = scoring.score(worst)
        assert score < 30

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")
        p = self._make_prospect(
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://clinic.com",
            email="info@clinic.com",
            phone="+923001234567",
            source="linkedin",
            freshness="verified_recent",
            google_maps_url="https://maps.google.com/cid/123",
            address="123 Main St",
            metadata={
                "problems_list": ["Booking", "Support", "FAQs"],
                "demo_url": "https://demo.com",
            },
        )
        score = scoring.score(p)
        assert score <= 100

    def test_batch_scoring_sorts_descending(self):
        """Batch scoring should sort prospects by score descending."""
        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental",
        )

        p1 = self._make_prospect(
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
        )
        p2 = self._make_prospect(
            business_name="Perfect Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://dental.pk",
            email="info@dental.pk",
            phone="+923001234567",
        )

        result = scoring.score_batch([p1, p2])
        assert result[0].lead_score >= result[1].lead_score

    def test_select_top_leads_respects_limit(self):
        """select_top_leads should respect the max_count parameter."""
        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental",
        )

        leads = []
        for i in range(20):
            p = self._make_prospect(
                business_name=f"Clinic {i}",
                business_category="Dental Clinic",
                country="Pakistan",
                city="Lahore",
                website=f"https://clinic{i}.pk",
                email=f"info@clinic{i}.pk",
            )
            leads.append(p)

        scored = scoring.score_batch(leads)
        selected = scoring.select_top_leads(scored, 10)

        assert len(selected) <= 10

    def test_threshold_qualification(self):
        """Only leads above threshold should be qualified."""
        from app.config.settings import settings
        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="dental",
        )

        # Strong lead
        strong = self._make_prospect(
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://dental.pk",
            email="info@dental.pk",
            phone="+923001234567",
        )

        # Weak lead
        weak = self._make_prospect(
            business_category="Gym",
            country="India",
            city="Mumbai",
        )

        scoring.score_batch([strong, weak])

        assert strong.is_qualified is True
        assert weak.is_qualified is False
