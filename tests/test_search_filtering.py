"""Tests for search filtering: country restriction, city restriction, category restriction."""

import pytest

from app.sources.base import RawProspect


class TestSearchRestrictions:
    """Ensure search only targets the specified country/city/category."""

    def test_country_restriction_enforced(self):
        """When country=UAE, city=Dubai, results should NOT include Pakistan businesses."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="uae",
            target_city="dubai",
            target_category="dental clinic",
        )

        # Dubai business — should score high
        dubai_prospect = RawProspect(
            business_name="Dubai Dental Center",
            business_category="dental clinic",
            country="UAE",
            city="Dubai",
            website="https://dubaidental.ae",
            email="info@dubaidental.ae",
        )
        dubai_score = scoring.score(dubai_prospect)

        # Pakistan business — should score lower (no location match)
        pakistan_prospect = RawProspect(
            business_name="Lahore Dental Care",
            business_category="dental clinic",
            country="Pakistan",
            city="Lahore",
            website="https://lahoredental.pk",
            email="info@lahoredental.pk",
        )
        pakistan_score = scoring.score(pakistan_prospect)

        # Dubai should score higher because of location match
        assert dubai_score > pakistan_score

    def test_city_restriction(self):
        """When city=Lahore, Lahore businesses should score higher than Karachi."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="pakistan",
            target_city="lahore",
            target_category="restaurant",
        )

        lahore = RawProspect(
            business_name="Lahore Food House",
            business_category="Restaurant",
            country="Pakistan",
            city="Lahore",
        )
        karachi = RawProspect(
            business_name="Karachi Biryani",
            business_category="Restaurant",
            country="Pakistan",
            city="Karachi",
        )

        assert scoring.score(lahore) > scoring.score(karachi)

    def test_category_restriction(self):
        """When category=Dental Clinics, dental clinics should score higher than restaurants."""
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
            business_name="Food Garden",
            business_category="Restaurant",
            country="Pakistan",
            city="Lahore",
        )

        dental_score = scoring.score(dental)
        restaurant_score = scoring.score(restaurant)

        assert dental_score > restaurant_score

    def test_all_criteria_match_highest_score(self):
        """Prospect matching all criteria should score highest."""
        from app.agents.lead_scoring import LeadScoringAgent

        scoring = LeadScoringAgent(
            target_country="uae",
            target_city="dubai",
            target_category="beauty salon",
        )

        perfect = RawProspect(
            business_name="Glamour Salon",
            business_category="Beauty Salon",
            country="UAE",
            city="Dubai",
            website="https://glamour.ae",
            email="hi@glamour.ae",
            phone="+971501234567",
            source="google_maps",
            google_maps_url="https://maps.google.com/cid/123",
            metadata={"problems_list": ["Appointment booking", "Customer inquiries"],
                       "demo_url": "https://demo.example.com"},
        )
        bad_match = RawProspect(
            business_name="Random Gym",
            business_category="Gym",
            country="India",
            city="Mumbai",
        )

        perfect_score = scoring.score(perfect)
        bad_score = scoring.score(bad_match)

        assert perfect_score > bad_score
        assert perfect_score >= 80  # Should be high
        assert bad_score < 30  # Should be low


class TestCategoryExpansion:
    """Category should NOT be expanded unless explicitly allowed."""

    def test_exact_category_match(self):
        """Category 'dental clinic' should match 'dental clinic'."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        agent = ProblemAnalysisAgent()

        cat = agent._match_category("dental clinic")
        assert cat == "dental clinic"

    def test_partial_category_match(self):
        """'beauty parlor in Lahore' should match beauty-related category."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        agent = ProblemAnalysisAgent()

        cat = agent._match_category("beauty parlor")
        assert cat in ("beauty parlor", "beauty salon")

    def test_unrelated_category_no_match(self):
        """'gym' should not match 'dental clinic' template."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        agent = ProblemAnalysisAgent()

        dental_cat = agent._match_category("dental clinic")
        gym_cat = agent._match_category("gym")

        # They should match different templates
        assert dental_cat != gym_cat
