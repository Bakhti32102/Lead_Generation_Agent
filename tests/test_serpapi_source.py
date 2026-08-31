"""
Tests for SerpAPI Source.
Validates search functionality, error handling, and integration.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.sources.serpapi import SerpAPISource
from app.sources.base import RawProspect


class TestSerpAPISource:
    """Tests for SerpAPI search source."""

    def test_serpapi_source_exists(self):
        """SerpAPI source should be importable and have required methods."""
        source = SerpAPISource()
        assert hasattr(source, "name")
        assert hasattr(source, "is_configured")
        assert hasattr(source, "search")
        assert source.name == "serpapi"

    def test_serpapi_not_configured(self):
        """SerpAPI should report not configured when API key is missing."""
        with patch("app.sources.serpapi.settings") as mock_settings:
            mock_settings.search.api_key = ""
            mock_settings.search.provider = "serpapi"
            source = SerpAPISource()
            assert not source.is_configured

    def test_serpapi_wrong_provider(self):
        """SerpAPI should report not configured when using different provider."""
        with patch("app.sources.serpapi.settings") as mock_settings:
            mock_settings.search.api_key = "test_key"
            mock_settings.search.provider = "tavily"
            source = SerpAPISource()
            assert not source.is_configured

    def test_serpapi_configured(self):
        """SerpAPI should report configured when API key and provider are set."""
        with patch("app.sources.serpapi.settings") as mock_settings:
            mock_settings.search.api_key = "test_key"
            mock_settings.search.provider = "serpapi"
            source = SerpAPISource()
            assert source.is_configured

    def test_serpapi_search_returns_empty_when_not_configured(self):
        """SerpAPI search should return empty list when not configured."""
        with patch("app.sources.serpapi.settings") as mock_settings:
            mock_settings.search.api_key = ""
            source = SerpAPISource()
            results = source.search("Pakistan", "Lahore", "Dental Clinics")
            assert results == []

    def test_serpapi_country_code_conversion(self):
        """Country name should be converted to ISO code correctly."""
        assert SerpAPISource._country_code("Pakistan") == "pk"
        assert SerpAPISource._country_code("UAE") == "ae"
        assert SerpAPISource._country_code("United Kingdom") == "gb"
        assert SerpAPISource._country_code("USA") == "us"
        assert SerpAPISource._country_code("India") == "in"
        assert SerpAPISource._country_code("Unknown Country") == "us"

    def test_serpapi_extract_email(self):
        """Email extraction should work correctly."""
        assert SerpAPISource._extract_email("Contact us at info@clinic.com") == "info@clinic.com"
        assert SerpAPISource._extract_email("No email here") == ""

    def test_serpapi_extract_phone(self):
        """Phone extraction should work correctly."""
        phone = SerpAPISource._extract_phone("Call us at +92 300 123 4567")
        assert "92" in phone or "300" in phone

    def test_serpapi_clean_name(self):
        """Name cleaning should remove common suffixes."""
        assert SerpAPISource._clean_name("Smile Dental - Home") == "Smile Dental"
        assert SerpAPISource._clean_name("Clinic | Official") == "Clinic"
        assert SerpAPISource._clean_name("Business Name") == "Business Name"

    def test_serpapi_is_job_platform(self):
        """Job platform detection should work correctly."""
        assert SerpAPISource._is_job_platform("https://indeed.com/job/123")
        assert SerpAPISource._is_job_platform("https://upwork.com/freelancers/123")
        assert SerpAPISource._is_job_platform("https://linkedin.com/jobs/123")
        assert not SerpAPISource._is_job_platform("https://google.com")

    def test_serpapi_extract_company_from_title(self):
        """Company extraction from LinkedIn titles should work."""
        assert SerpAPISource._extract_company_from_title("AI Developer - TechCorp") == "TechCorp"
        assert SerpAPISource._extract_company_from_title("Chatbot Project | LinkedIn") == "Chatbot Project"
        assert SerpAPISource._extract_company_from_title("Simple Title") == "Simple Title"


class TestSerpAPIIntegration:
    """Integration tests for SerpAPI with discovery pipeline."""

    def test_serpapi_included_in_sources_init(self):
        """SerpAPI should be importable from sources package."""
        from app.sources import SerpAPISource
        assert SerpAPISource is not None

    def test_serpapi_in_lead_discovery(self):
        """SerpAPI should be available in lead discovery agent."""
        from app.agents.lead_discovery import LeadDiscoveryAgent
        discovery = LeadDiscoveryAgent()
        source_names = [s.name for s in discovery.sources]
        assert "serpapi" in source_names

    @patch("app.sources.serpapi.requests")
    @patch("app.sources.serpapi.settings")
    def test_serpapi_search_google(self, mock_settings, mock_requests):
        """Google search via SerpAPI should return prospects."""
        mock_settings.search.api_key = "test_key"
        mock_settings.search.provider = "serpapi"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "organic_results": [
                {
                    "title": "Smile Dental Clinic",
                    "link": "https://smiledental.com",
                    "snippet": "Best dental clinic in Lahore. Call +92 300 123 4567",
                    "displayed_link": "smiledental.com",
                }
            ]
        }
        mock_requests.get.return_value = mock_response

        source = SerpAPISource()
        results = source._search_google("Pakistan", "Lahore", "Dental Clinics", 10)

        assert len(results) == 1
        assert results[0].business_name == "Smile Dental Clinic"
        assert results[0].website == "https://smiledental.com"
        assert results[0].source == "serpapi_google"

    @patch("app.sources.serpapi.requests")
    @patch("app.sources.serpapi.settings")
    def test_serpapi_search_google_maps(self, mock_settings, mock_requests):
        """Google Maps search via SerpAPI should return prospects."""
        mock_settings.search.api_key = "test_key"
        mock_settings.search.provider = "serpapi"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "local_results": [
                {
                    "title": "City Dental Center",
                    "address": "123 Main St, Lahore",
                    "phone": "+92 300 987 6543",
                    "website": "https://citydental.pk",
                    "place_id_search": "https://google.com/maps/place/123",
                    "rating": 4.5,
                    "reviews": 120,
                    "type": "Dentist",
                    "thumbnail": "https://example.com/thumb.jpg",
                }
            ]
        }
        mock_requests.get.return_value = mock_response

        source = SerpAPISource()
        results = source._search_google_maps("Pakistan", "Lahore", "Dental Clinics", 10)

        assert len(results) == 1
        assert results[0].business_name == "City Dental Center"
        assert results[0].address == "123 Main St, Lahore"
        assert results[0].phone == "+92 300 987 6543"
        assert results[0].website == "https://citydental.pk"
        assert results[0].source == "serpapi_maps"
        assert results[0].metadata["rating"] == 4.5

    @patch("app.sources.serpapi.requests")
    @patch("app.sources.serpapi.settings")
    def test_serpapi_search_linkedin(self, mock_settings, mock_requests):
        """LinkedIn search via SerpAPI should return prospects."""
        mock_settings.search.api_key = "test_key"
        mock_settings.search.provider = "serpapi"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "organic_results": [
                {
                    "title": "Need AI Chatbot - TechCorp | LinkedIn",
                    "link": "https://linkedin.com/posts/123",
                    "snippet": "Looking for AI chatbot developer for customer support",
                }
            ]
        }
        mock_requests.get.return_value = mock_response

        source = SerpAPISource()
        results = source._search_linkedin("Pakistan", "Lahore", "Dental Clinics", 10)

        assert len(results) == 1
        assert results[0].source == "serpapi_linkedin"
        assert "linkedin.com" in results[0].source_url
        assert results[0].freshness == "probably_recent"

    @patch("app.sources.serpapi.requests")
    @patch("app.sources.serpapi.settings")
    def test_serpapi_search_jobs(self, mock_settings, mock_requests):
        """Job search via SerpAPI should filter for job platforms."""
        mock_settings.search.api_key = "test_key"
        mock_settings.search.provider = "serpapi"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "organic_results": [
                {
                    "title": "AI Developer Needed - Indeed",
                    "link": "https://indeed.com/job/123",
                    "snippet": "Looking for AI developer for chatbot project",
                },
                {
                    "title": "Random Blog Post",
                    "link": "https://example.com/blog",
                    "snippet": "Some random content",
                },
            ]
        }
        mock_requests.get.return_value = mock_response

        source = SerpAPISource()
        results = source._search_jobs("Pakistan", "Lahore", "Dental Clinics", 10)

        assert len(results) == 1
        assert results[0].source == "serpapi_jobs"
        assert "indeed.com" in results[0].source_url

    @patch("app.sources.serpapi.requests")
    @patch("app.sources.serpapi.settings")
    def test_serpapi_handles_request_exception(self, mock_settings, mock_requests):
        """SerpAPI should handle request exceptions gracefully."""
        mock_settings.search.api_key = "test_key"
        mock_settings.search.provider = "serpapi"
        mock_requests.get.side_effect = Exception("Connection timeout")

        source = SerpAPISource()
        results = source._search_google("Pakistan", "Lahore", "Dental Clinics", 10)

        assert results == []

    @patch("app.sources.serpapi.requests")
    @patch("app.sources.serpapi.settings")
    def test_serpapi_handles_invalid_json(self, mock_settings, mock_requests):
        """SerpAPI should handle invalid JSON responses gracefully."""
        mock_settings.search.api_key = "test_key"
        mock_settings.search.provider = "serpapi"

        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_requests.get.return_value = mock_response

        source = SerpAPISource()
        results = source._search_google("Pakistan", "Lahore", "Dental Clinics", 10)

        assert results == []

    @patch("app.sources.serpapi.requests")
    @patch("app.sources.serpapi.settings")
    def test_serpapi_handles_empty_results(self, mock_settings, mock_requests):
        """SerpAPI should handle empty results gracefully."""
        mock_settings.search.api_key = "test_key"
        mock_settings.search.provider = "serpapi"

        mock_response = MagicMock()
        mock_response.json.return_value = {"organic_results": []}
        mock_requests.get.return_value = mock_response

        source = SerpAPISource()
        results = source._search_google("Pakistan", "Lahore", "Nonexistent Category", 10)

        assert results == []
