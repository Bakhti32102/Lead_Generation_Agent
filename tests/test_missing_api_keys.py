"""Tests for graceful handling of missing API keys and API failures."""

import pytest
from unittest.mock import patch, MagicMock


class TestMissingAPIKeys:
    """All modules should handle missing API keys without crashing."""

    def test_llm_unconfigured_no_crash(self):
        """LLM client should not crash when API key is missing."""
        from app.integrations.llm import LLMClient
        client = LLMClient(api_key="")
        assert client.is_configured is False

    def test_llm_unconfigured_chat_raises(self):
        """LLM chat should raise RuntimeError when unconfigured."""
        from app.integrations.llm import LLMClient
        client = LLMClient(api_key="")
        with pytest.raises(RuntimeError, match="not configured"):
            client.chat([{"role": "user", "content": "Hello"}])

    def test_search_source_unconfigured(self):
        """Search source should return empty results when unconfigured."""
        from app.sources.google_search import GoogleSearchSource
        source = GoogleSearchSource()
        # With empty API key, is_configured should be False
        if not source.is_configured:
            results = source.search("Pakistan", "Lahore", "Dental Clinics")
            assert results == []

    def test_google_maps_unconfigured(self):
        """Google Maps source should return empty when unconfigured."""
        from app.sources.google_maps import GoogleMapsSource
        source = GoogleMapsSource()
        if not source.is_configured:
            results = source.search("Pakistan", "Lahore", "Dental Clinics")
            assert results == []

    def test_linkedin_source_unconfigured(self):
        """LinkedIn source should return empty when search API is unconfigured."""
        from app.sources.linkedin import LinkedInSource
        source = LinkedInSource()
        if not source.is_configured:
            results = source.search("Pakistan", "Lahore", "Dental Clinics")
            assert results == []

    def test_public_jobs_source_unconfigured(self):
        """Public jobs source should return empty when search API is unconfigured."""
        from app.sources.public_jobs import PublicJobSource
        source = PublicJobSource()
        if not source.is_configured:
            results = source.search("Pakistan", "Lahore", "Dental Clinics")
            assert results == []

    def test_google_sheets_unconfigured(self):
        """Google Sheets client should not crash when unconfigured."""
        from app.integrations.google_sheets import GoogleSheetsClient
        client = GoogleSheetsClient()
        # Should not crash
        rows = client.read_all_rows()
        assert isinstance(rows, list)

    def test_email_unconfigured(self):
        """Email client should return failure when unconfigured."""
        from app.integrations.email import EmailClient
        client = EmailClient()
        result = client.send("test@example.com", "Subject", "Body")
        assert result["success"] is False

    def test_whatsapp_unconfigured(self):
        """WhatsApp client should return failure when unconfigured."""
        from app.integrations.whatsapp import WhatsAppClient
        client = WhatsAppClient()
        result = client.send_text("+1234567890", "Hello")
        assert result["success"] is False


class TestAPIFailures:
    """Tests for graceful handling of API failures."""

    def test_search_failure_returns_empty(self):
        """Search API failure should return empty list, not crash."""
        from app.sources.google_search import GoogleSearchSource
        source = GoogleSearchSource()

        with patch.object(source, "_search_tavily", side_effect=Exception("API Error")):
            results = source._execute_search("test query", max_results=5)
            assert results == []

    def test_llm_failure_in_research(self):
        """LLM failure in business research should fall back to basic analysis."""
        from app.agents.business_research import BusinessResearchAgent
        from app.integrations.llm import LLMClient
        from app.sources.base import RawProspect

        agent = BusinessResearchAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Test Clinic",
            business_category="Clinic",
            website="https://testclinic.com",
        )

        # Should fall back to basic analysis without crashing
        # (will fail to fetch website but should not crash)
        with patch.object(agent, "_fetch_website_text", return_value="Dental clinic with booking system"):
            result = agent.research(prospect)
            assert result.metadata.get("website_analysis") is not None

    def test_problem_analysis_without_llm(self):
        """Problem analysis should work deterministically without LLM."""
        from app.agents.problem_analysis import ProblemAnalysisAgent
        from app.integrations.llm import LLMClient
        from app.sources.base import RawProspect

        agent = ProblemAnalysisAgent(llm=LLMClient(api_key=""))

        prospect = RawProspect(
            business_name="Smile Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
        )

        result = agent.analyze(prospect, "Dental Clinic")
        assert result.potential_problem  # Should have some problem identified
        assert result.recommended_ai_solution  # Should have a recommended solution

    def test_scoring_without_metadata(self):
        """Lead scoring should work even with empty metadata."""
        from app.agents.lead_scoring import LeadScoringAgent
        from app.sources.base import RawProspect

        scoring = LeadScoringAgent(target_country="", target_city="", target_category="")
        prospect = RawProspect(
            business_name="Minimal Business",
            business_category="",
            country="",
            city="",
            metadata={},
        )

        score = scoring.score(prospect)
        assert isinstance(score, int)
        assert 0 <= score <= 100

    def test_service_matching_without_demos(self):
        """Service matching should still recommend services without demos."""
        from app.agents.solution_matching import SolutionMatchingAgent
        from app.sources.base import RawProspect

        agent = SolutionMatchingAgent()
        prospect = RawProspect(
            business_name="Test",
            business_category="Restaurant",
            website="https://test.com",
            metadata={"website_analysis": {"has_booking": False, "has_chatbot": False, "website_quality": "average"}},
        )

        result = agent.match(prospect)
        assert prospect.recommended_service  # Should have a recommendation


class TestConfigStatus:
    """Tests for the configuration status checker."""

    def test_status_shows_all_services(self):
        from app.config.settings import Settings
        s = Settings()
        status = s.print_status()
        assert "LLM API" in status
        assert "Search API" in status
        assert "Email API" in status
        assert "WhatsApp API" in status

    def test_status_does_not_expose_keys(self):
        """Status should never expose actual API keys."""
        from app.config.settings import Settings
        s = Settings()
        status = s.print_status()
        # Should not contain key-like strings
        assert "sk-" not in status
        assert "key=" not in status.lower()
