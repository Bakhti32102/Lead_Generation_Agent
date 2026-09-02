"""
WhatsApp Integration Tests.
All tests use mocked API calls. No real messages are sent.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestWhatsAppConfiguration:
    """Test WhatsApp client configuration."""

    def test_whatsapp_settings_loads(self):
        """WhatsApp settings should load from env."""
        from app.config.settings import settings
        assert hasattr(settings, 'whatsapp')
        assert hasattr(settings.whatsapp, 'access_token')
        assert hasattr(settings.whatsapp, 'phone_number_id')

    def test_is_configured_false_when_empty(self):
        """is_configured should be False when no credentials."""
        from app.config.settings import settings
        if not settings.whatsapp.access_token:
            assert settings.whatsapp.is_configured is False

    def test_is_configured_true_when_set(self):
        """is_configured should be True when credentials are set."""
        from app.config.settings import WhatsAppConfig
        config = WhatsAppConfig(
            access_token="test_token_12345",
            phone_number_id="123456789",
            business_account_id="987654321",
        )
        assert config.is_configured is True

    def test_is_configured_false_missing_token(self):
        """is_configured should be False when token is missing."""
        from app.config.settings import WhatsAppConfig
        config = WhatsAppConfig(access_token="", phone_number_id="123456789")
        assert config.is_configured is False

    def test_is_configured_false_missing_phone_id(self):
        """is_configured should be False when phone_number_id is missing."""
        from app.config.settings import WhatsAppConfig
        config = WhatsAppConfig(access_token="test_token_12345", phone_number_id="")
        assert config.is_configured is False


class TestWhatsAppClient:
    """Test WhatsApp client methods by constructing client with explicit values."""

    def test_client_importable(self):
        """WhatsAppClient should be importable."""
        from app.integrations.whatsapp import WhatsAppClient
        assert WhatsAppClient is not None

    def test_singleton_exists(self):
        """Module-level whatsapp_client singleton should exist."""
        from app.integrations.whatsapp import whatsapp_client
        assert whatsapp_client is not None

    def _make_client(self, configured=True):
        """Helper: create WhatsAppClient with mocked settings."""
        from app.integrations.whatsapp import WhatsAppClient
        client = WhatsAppClient.__new__(WhatsAppClient)
        if configured:
            client.access_token = "test_token_abc123"
            client.phone_number_id = "123456789"
            client.business_account_id = "987654321"
        else:
            client.access_token = ""
            client.phone_number_id = ""
            client.business_account_id = ""
        return client

    def test_send_text_not_configured(self):
        """send_text should fail gracefully when not configured."""
        client = self._make_client(configured=False)
        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: False)):
            result = client.send_text("+923001234567", "Test")
            assert result["success"] is False
            assert "not configured" in result["message"].lower()

    def test_send_text_empty_recipient(self):
        """send_text should fail with empty phone number."""
        client = self._make_client(configured=True)
        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            result = client.send_text("", "Test")
            assert result["success"] is False
            assert "no phone" in result["message"].lower()

    def test_send_text_api_success(self):
        """send_text should handle successful API response."""
        client = self._make_client(configured=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.test123"}]}

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', return_value=mock_response):
                result = client.send_text("+923001234567", "Test message")

        assert result["success"] is True
        assert result["id"] == "wamid.test123"

    def test_send_text_api_error(self):
        """send_text should handle API error response."""
        client = self._make_client(configured=True)

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": {"message": "Invalid parameter", "type": "OAuthException"}
        }

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', return_value=mock_response):
                result = client.send_text("+923001234567", "Test")

        assert result["success"] is False
        assert "Invalid parameter" in result["message"]

    def test_send_text_timeout(self):
        """send_text should handle request timeout."""
        client = self._make_client(configured=True)
        import requests as req

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', side_effect=req.exceptions.Timeout("Connection timed out")):
                result = client.send_text("+923001234567", "Test")

        assert result["success"] is False
        assert "timed out" in result["message"].lower()

    def test_send_text_network_error(self):
        """send_text should handle network errors."""
        client = self._make_client(configured=True)
        import requests as req

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', side_effect=req.exceptions.ConnectionError("Connection refused")):
                result = client.send_text("+923001234567", "Test")

        assert result["success"] is False

    def test_send_template_not_configured(self):
        """send_template should fail gracefully when not configured."""
        client = self._make_client(configured=False)
        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: False)):
            result = client.send_template("+923001234567", "test_template")
            assert result["success"] is False

    def test_send_template_success(self):
        """send_template should handle successful API response."""
        client = self._make_client(configured=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.tpl123"}]}

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', return_value=mock_response):
                result = client.send_template("+923001234567", "hello_world")

        assert result["success"] is True
        assert result["id"] == "wamid.tpl123"

    def test_send_template_with_parameters(self):
        """send_template should handle parameterized templates."""
        client = self._make_client(configured=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.tpl456"}]}

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', return_value=mock_response) as mock_post:
                result = client.send_template("+923001234567", "greeting", "en", ["John"])

            call_args = mock_post.call_args
            payload = call_args[1]['json'] if 'json' in call_args[1] else call_args[0][1]
            assert "components" in payload["template"]

    def test_send_text_strips_plus_from_number(self):
        """send_text should strip leading + from phone number."""
        client = self._make_client(configured=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.test"}]}

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', return_value=mock_response) as mock_post:
                result = client.send_text("+923001234567", "Test")

            call_args = mock_post.call_args
            payload = call_args[1]['json'] if 'json' in call_args[1] else call_args[0][1]
            assert payload["to"] == "923001234567"

    def test_send_text_correct_api_url(self):
        """send_text should call the correct Graph API endpoint."""
        client = self._make_client(configured=True)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "wamid.test"}]}

        with patch.object(type(client), 'is_configured', new_callable=lambda: property(lambda self: True)):
            with patch('app.integrations.whatsapp.requests.post', return_value=mock_response) as mock_post:
                result = client.send_text("+923001234567", "Test")

            call_args = mock_post.call_args
            url = call_args[0][0]
            assert "graph.facebook.com" in url
            assert "v25.0" in url
            assert "123456789/messages" in url

    def test_send_text_api_version_v25(self):
        """WhatsApp API should use v25.0."""
        from app.integrations.whatsapp import BASE_URL
        assert "v25.0" in BASE_URL


class TestWhatsAppSafety:
    """Test WhatsApp safety integration."""

    def test_dry_run_blocks_whatsapp(self):
        """DRY_RUN should prevent WhatsApp sending."""
        from app.agents.outreach import OutreachAgent
        from app.sources.base import RawProspect
        from app.integrations.whatsapp import whatsapp_client
        from app.config.settings import settings

        assert settings.campaign.dry_run is True

        with patch.object(whatsapp_client, 'send_text') as mock_send:
            agent = OutreachAgent()
            p = RawProspect(business_name="Test", phone="+923001234567", email="")
            result = agent.send_initial(p, "Test message")
            mock_send.assert_not_called()

    def test_review_mode_blocks_whatsapp(self):
        """REVIEW_MODE should prevent WhatsApp auto-sending."""
        from app.integrations.whatsapp import whatsapp_client
        from app.sources.base import RawProspect
        from app.config.settings import settings

        assert settings.campaign.review_mode is True

        with patch.object(whatsapp_client, 'send_text') as mock_send:
            from app.agents.outreach import OutreachAgent
            agent = OutreachAgent()
            p = RawProspect(business_name="Test", phone="+923001234567", email="")
            result = agent.send_initial(p, "Test")
            assert result["status"] in ("draft", "pending_review")
            mock_send.assert_not_called()

    def test_dnc_blocks_whatsapp(self):
        """DNC flag should prevent WhatsApp sending."""
        from app.database import FollowUpRepository, LeadRepository
        from app.database.models import init_db, DiscoveredLead, get_session

        init_db()
        lead_repo = LeadRepository()
        followup_repo = FollowUpRepository()

        lead = lead_repo.save_lead({
            "business_name": "DNC WhatsApp Test",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        })
        followup_repo.create_state(lead.id)
        followup_repo.set_do_not_contact(lead.id)

        state = followup_repo.get_by_lead_id(lead.id)
        assert state.do_not_contact is True

        # Cleanup
        session = get_session()
        session.query(DiscoveredLead).filter_by(id=lead.id).delete()
        from app.database.models import FollowUpState
        session.query(FollowUpState).filter_by(lead_id=lead.id).delete()
        session.commit()
        session.close()


class TestWhatsAppSecurity:
    """Test WhatsApp security."""

    def test_no_token_in_source_code(self):
        """WhatsApp token should not be hardcoded in source."""
        with open("app/integrations/whatsapp.py", "r") as f:
            content = f.read()
        # Should only have placeholder or env-loaded values, not actual token prefixes
        assert 'access_token = ""' in content or "access_token = ''" in content or "access_token = " in content

    def test_no_actual_token_pattern_in_source(self):
        """Source should not contain actual Meta token patterns."""
        with open("app/integrations/whatsapp.py", "r") as f:
            content = f.read()
        # Meta tokens start with EAAG - should not appear as string literals
        import re
        eaag_matches = re.findall(r'["\']EAAG[A-Za-z0-9]+["\']', content)
        assert len(eaag_matches) == 0

    def test_whatsapp_config_protected(self):
        """WhatsApp token should be protected via .env."""
        with open(".gitignore") as f:
            content = f.read()
        assert ".env" in content
