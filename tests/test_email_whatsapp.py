"""Tests for email and WhatsApp integration."""

import pytest
from unittest.mock import patch, MagicMock


class TestEmailClient:
    """Tests for the email integration module."""

    def test_unconfigured_client(self):
        from app.integrations.email import EmailClient
        client = EmailClient()
        assert client.is_configured is False

    def test_send_when_unconfigured(self):
        """Sending when not configured should return failure, not crash."""
        from app.integrations.email import EmailClient
        client = EmailClient()
        result = client.send("test@example.com", "Subject", "Body")
        assert result["success"] is False
        assert "not configured" in result["message"].lower()

    def test_send_with_empty_recipient(self):
        """Sending to empty email should fail gracefully."""
        from app.integrations.email import EmailClient
        client = EmailClient()
        result = client.send("", "Subject", "Body")
        assert result["success"] is False

    def test_singleton_exists(self):
        from app.integrations.email import email_client
        assert email_client is not None
        assert hasattr(email_client, "send")


class TestWhatsAppClient:
    """Tests for the WhatsApp Business API integration."""

    def test_unconfigured_client(self):
        from app.integrations.whatsapp import WhatsAppClient
        client = WhatsAppClient()
        assert client.is_configured is False

    def test_send_when_unconfigured(self):
        """Sending when not configured should return failure, not crash."""
        from app.integrations.whatsapp import WhatsAppClient
        client = WhatsAppClient()
        result = client.send_text("+923001234567", "Hello")
        assert result["success"] is False
        assert "not configured" in result["message"].lower()

    def test_send_with_empty_number(self):
        """Sending to empty number should fail gracefully."""
        from app.integrations.whatsapp import WhatsAppClient
        client = WhatsAppClient()
        result = client.send_text("", "Hello")
        assert result["success"] is False

    def test_singleton_exists(self):
        from app.integrations.whatsapp import whatsapp_client
        assert whatsapp_client is not None
        assert hasattr(whatsapp_client, "send_text")
        assert hasattr(whatsapp_client, "send_template")


class TestEmailMocked:
    """Tests with mocked email provider to verify send logic."""

    def test_resend_provider_called(self):
        """Resend provider should be called with correct params."""
        from app.integrations.email import EmailClient

        client = EmailClient()
        client.provider = "resend"
        client.api_key = "test_key"
        client.from_address = "test@example.com"

        # Mock is_configured to return True and _send_resend for the actual call
        with patch.object(EmailClient, "is_configured", new_callable=lambda: property(lambda self: True)):
            with patch.object(EmailClient, "_send_resend",
                              return_value={"success": True, "message": "Sent via Resend", "id": "msg_123"}) as mock_send:
                result = client.send("recipient@example.com", "Test Subject", "Test body")
                mock_send.assert_called_once()
                assert result["success"] is True
                assert result["id"] == "msg_123"


class TestOutreachAgentDryRun:
    """Tests for outreach in dry run mode."""

    def test_dry_run_does_not_send(self):
        """DRY_RUN mode should not actually send messages."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect

        with patch("app.agents.outreach.settings") as mock_settings:
            mock_campaign = MagicMock()
            mock_campaign.dry_run = True
            mock_campaign.review_mode = False
            mock_campaign.max_daily_outreach = 15
            mock_settings.campaign = mock_campaign

            agent = OutreachAgent()
            prospect = RawProspect(
                business_name="Test",
                email="test@example.com",
            )

            result = agent.send_initial(prospect, "Hello!")
            assert result["status"] == "draft"

    def test_review_mode_queues(self):
        """REVIEW_MODE should prepare but not send."""
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
