"""
Tests for Fiverr Outreach Integration.
Validates message generation, tracking, and configuration.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.integrations.fiverr import FiverrClient


class TestFiverrClient:
    """Tests for FiverrClient."""

    def test_fiverr_client_exists(self):
        """FiverrClient should be importable."""
        client = FiverrClient()
        assert hasattr(client, "is_configured")
        assert hasattr(client, "generate_buyer_request")
        assert hasattr(client, "generate_proposal")

    def test_fiverr_not_configured(self):
        """FiverrClient should report not configured when URL is missing."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.fiverr_url = ""
            client = FiverrClient()
            assert not client.is_configured

    def test_fiverr_configured(self):
        """FiverrClient should report configured when URL is set."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.fiverr_url = "https://www.fiverr.com/yourprofile"
            client = FiverrClient()
            assert client.is_configured

    def test_generate_buyer_request(self):
        """Buyer request generation should produce formatted message."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.name = "AI Developer"
            mock_settings.my_business.description = "Building AI agents"
            mock_settings.my_business.fiverr_url = "https://www.fiverr.com/yourprofile"

            client = FiverrClient()
            message = client.generate_buyer_request(
                business_name="Smile Dental",
                business_category="Dental Clinic",
                city="Lahore",
                country="Pakistan",
                requirement="Need chatbot for appointment booking",
                demo_url="https://demo.example.com",
                solution="AI Dental Receptionist",
            )

            assert "Smile Dental" in message
            assert "Lahore" in message
            assert "Dental Clinic" in message
            assert "chatbot" in message.lower() or "AI" in message
            assert "https://demo.example.com" in message
            assert "https://www.fiverr.com/yourprofile" in message
            assert "AI Developer" in message

    def test_generate_proposal(self):
        """Proposal generation should produce structured proposal."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.name = "AI Developer"
            mock_settings.my_business.fiverr_url = "https://www.fiverr.com/yourprofile"

            client = FiverrClient()
            proposal = client.generate_proposal(
                business_name="Quick Bites",
                business_category="Restaurant",
                problem="manual reservation handling",
                solution="AI Reservation Agent",
                demo_url="https://restaurant-demo.com",
            )

            assert "Quick Bites" in proposal
            assert "Restaurant" in proposal
            assert "reservation" in proposal.lower()
            assert "https://restaurant-demo.com" in proposal
            assert "Project Proposal" in proposal

    def test_format_for_fiverr_character_limit(self):
        """Fiverr formatting should respect 2500 character limit."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.fiverr_url = "https://www.fiverr.com/yourprofile"

            client = FiverrClient()
            long_message = "A" * 3000
            formatted = client.format_for_fiverr(long_message)

            assert len(formatted) <= 2500
            assert formatted.endswith("...")

    def test_track_outreach(self):
        """Outreach tracking should return tracking information."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.fiverr_url = "https://www.fiverr.com/yourprofile"

            client = FiverrClient()
            tracking = client.track_outreach(
                business_name="Test Business",
                message_type="buyer_request",
                message="Test message",
            )

            assert tracking["business_name"] == "Test Business"
            assert tracking["message_type"] == "buyer_request"
            assert tracking["channel"] == "fiverr"
            assert tracking["status"] == "prepared"
            assert "timestamp" in tracking

    def test_get_fiverr_profile_url(self):
        """Should return the configured Fiverr URL."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.fiverr_url = "https://www.fiverr.com/testuser"

            client = FiverrClient()
            assert client.get_fiverr_profile_url() == "https://www.fiverr.com/testuser"


class TestFiverrIntegration:
    """Integration tests for Fiverr with outreach pipeline."""

    def test_fiverr_singleton_exists(self):
        """Fiverr singleton should be accessible."""
        from app.integrations.fiverr import fiverr_client
        assert fiverr_client is not None

    @patch("app.integrations.fiverr.settings")
    def test_fiverr_in_outreach_agent(self, mock_settings):
        """Outreach agent should support Fiverr channel."""
        mock_settings.campaign.dry_run = True
        mock_settings.campaign.review_mode = False
        mock_settings.campaign.max_daily_outreach = 15
        mock_settings.my_business.fiverr_url = "https://www.fiverr.com/testuser"
        mock_settings.my_business.name = "Test"
        mock_settings.my_business.description = "AI Developer"

        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        outreach = OutreachAgent()
        prospect = RawProspect(
            business_name="Test Business",
            business_category="Restaurant",
            city="Lahore",
            country="Pakistan",
        )

        # In dry run mode, should return draft
        result = outreach.send_initial(prospect, "Test message")
        assert result["status"] == "draft"

    def test_fiverr_buyer_request_includes_all_info(self):
        """Buyer request should include all required information."""
        with patch("app.integrations.fiverr.settings") as mock_settings:
            mock_settings.my_business.name = "AI Solutions"
            mock_settings.my_business.description = "Custom AI development"
            mock_settings.my_business.fiverr_url = "https://www.fiverr.com/aisolutions"

            client = FiverrClient()
            message = client.generate_buyer_request(
                business_name="Beauty Salon",
                business_category="Beauty",
                city="Dubai",
                country="UAE",
                requirement="Need appointment booking system",
                solution="AI Booking Agent",
            )

            # Verify all key elements are present
            assert "Beauty Salon" in message
            assert "Dubai" in message
            assert "UAE" in message
            assert "Beauty" in message
            assert "appointment" in message.lower() or "booking" in message.lower()
            assert "AI Solutions" in message
            assert "https://www.fiverr.com/aisolutions" in message
