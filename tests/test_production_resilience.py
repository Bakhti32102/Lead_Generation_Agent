"""
Regression tests for production resilience fixes:
1. LLM retry with backoff on 429 errors
2. FIFO cap preserves leads with active follow-up states
3. Template fallback clearly marked in lead metadata
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest


# ────────────────────────────────────────────────────────────────────
# TEST 1 — LLM retry on 429
# ────────────────────────────────────────────────────────────────────

class TestLLMRetryOnRateLimit:
    """Verify that the LLM client retries on 429 errors with backoff."""

    def test_is_rate_limit_detection(self):
        """429 and rate-limit messages are correctly detected."""
        from app.integrations.llm import LLMClient

        assert LLMClient._is_rate_limit(Exception("429 rate limit exceeded"))
        assert LLMClient._is_rate_limit(Exception("Rate limit reached for model groq"))
        assert LLMClient._is_rate_limit(Exception("TPM Limit: 8000"))
        assert LLMClient._is_rate_limit(Exception("too many requests"))
        assert LLMClient._is_rate_limit(Exception("rate_limit_exceeded"))

        # Non-rate-limit errors should NOT be detected
        assert not LLMClient._is_rate_limit(Exception("Connection timeout"))
        assert not LLMClient._is_rate_limit(Exception("Invalid API key"))
        assert not LLMClient._is_rate_limit(Exception("Model not found"))

    def test_backoff_delay_bounds(self):
        """Backoff delays are bounded and use exponential growth."""
        from app.integrations.llm import LLMClient

        exc = Exception("429 rate limit")

        # Attempt 0 → base 2s ± 25%
        delay_0 = LLMClient._backoff_delay(0, exc)
        assert 1.0 <= delay_0 <= 4.0, f"delay_0={delay_0}"

        # Attempt 1 → base 4s ± 25%
        delay_1 = LLMClient._backoff_delay(1, exc)
        assert 2.5 <= delay_1 <= 6.0, f"delay_1={delay_1}"

        # Attempt 2 → base 8s ± 25%
        delay_2 = LLMClient._backoff_delay(2, exc)
        assert 5.0 <= delay_2 <= 12.0, f"delay_2={delay_2}"

        # Delays should increase
        assert delay_0 < delay_1 < delay_2

    def test_retry_succeeds_after_rate_limit(self):
        """Client retries and succeeds after a transient 429."""
        from app.integrations.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.provider = "groq"
        client.model = "test-model"
        client.api_key = "test-key"
        client._client = MagicMock()
        client.MAX_RETRIES = 3

        # First call raises 429, second succeeds
        rate_limit_exc = Exception("Rate limit reached (429)")
        success_response = MagicMock()
        success_response.choices = [MagicMock(message=MagicMock(content="Hello"))]

        client._client.chat.completions.create.side_effect = [
            rate_limit_exc,
            success_response,
        ]

        with patch.object(client, "_is_rate_limit", return_value=True):
            with patch.object(client, "_backoff_delay", return_value=0.01):
                with patch("app.integrations.llm.time.sleep"):
                    result = client.chat(
                        messages=[{"role": "user", "content": "test"}]
                    )

        assert result == "Hello"

    def test_retry_exhausted_raises(self):
        """After MAX_RETRIES, the exception propagates."""
        from app.integrations.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.provider = "groq"
        client.model = "test-model"
        client.api_key = "test-key"
        client._client = MagicMock()
        client.MAX_RETRIES = 2

        rate_limit_exc = Exception("Rate limit reached (429)")
        client._client.chat.completions.create.side_effect = rate_limit_exc

        with patch.object(client, "_is_rate_limit", return_value=True):
            with patch.object(client, "_backoff_delay", return_value=0.01):
                with patch("app.integrations.llm.time.sleep"):
                    with pytest.raises(Exception, match="Rate limit"):
                        client.chat(
                            messages=[{"role": "user", "content": "test"}]
                        )

    def test_non_rate_limit_error_not_retried(self):
        """Non-429 errors propagate immediately without retry."""
        from app.integrations.llm import LLMClient

        client = LLMClient.__new__(LLMClient)
        client.provider = "groq"
        client.model = "test-model"
        client.api_key = "test-key"
        client._client = MagicMock()
        client.MAX_RETRIES = 3

        client._client.chat.completions.create.side_effect = (
            Exception("Invalid API key")
        )

        with pytest.raises(Exception, match="Invalid API key"):
            client.chat(messages=[{"role": "user", "content": "test"}])

        # Should have been called only once (no retry)
        assert client._client.chat.completions.create.call_count == 1


# ────────────────────────────────────────────────────────────────────
# TEST 2 — FIFO cap preserves active follow-ups
# ────────────────────────────────────────────────────────────────────

class TestFIFOCapPreservesFollowUps:
    """Verify that the FIFO cap does not delete leads with active follow-up states."""

    def test_fifo_skips_leads_with_active_followup(self):
        """Leads with active FollowUpState are not deleted by FIFO."""
        from app.database.repository import LeadRepository
        from app.database.models import DiscoveredLead, FollowUpState, get_session

        repo = LeadRepository()
        session = get_session()

        try:
            # Create 3 leads
            leads = []
            for i in range(3):
                lead = DiscoveredLead(
                    business_name=f"FIFO Test Lead {i}",
                    business_category="test",
                    country="Test",
                    city="Test",
                    is_outreach_lead=False,
                )
                session.add(lead)
                session.flush()
                leads.append(lead)

            # Create active follow-up for lead 0
            fu = FollowUpState(
                lead_id=leads[0].id,
                overall_status="active",
                initial_status="pending",
            )
            session.add(fu)

            # Create completed follow-up for lead 1
            fu2 = FollowUpState(
                lead_id=leads[1].id,
                overall_status="completed",
                initial_status="sent",
            )
            session.add(fu2)
            # lead 2 has no follow-up

            session.commit()

            # Run FIFO with a very low cap
            old_max = repo.MAX_LEADS
            repo.MAX_LEADS = 1
            try:
                deleted = repo.enforce_fifo_cap()
            finally:
                repo.MAX_LEADS = old_max

            # Verify: lead 0 (active follow-up) should survive
            surviving = session.query(DiscoveredLead).filter_by(
                business_name="FIFO Test Lead 0"
            ).first()
            assert surviving is not None, "Lead with active follow-up was deleted!"

            # lead 1 (completed follow-up) and lead 2 (no follow-up) may be deleted
            # lead 0 must survive regardless

        finally:
            # Cleanup
            for lid in [l.id for l in leads]:
                session.query(FollowUpState).filter_by(lead_id=lid).delete()
                session.query(DiscoveredLead).filter_by(id=lid).delete()
            session.commit()
            session.close()


# ────────────────────────────────────────────────────────────────────
# TEST 3 — Template fallback marking
# ────────────────────────────────────────────────────────────────────

class TestTemplateFallbackMarking:
    """Verify that template fallback messages are clearly marked."""

    def test_template_fallback_sets_metadata(self):
        """When LLM is not configured, message_source is 'template'."""
        from app.agents.personalization import PersonalizationAgent
        from app.sources.base import RawProspect

        agent = PersonalizationAgent.__new__(PersonalizationAgent)
        agent.llm = MagicMock()
        agent.llm.is_configured = False

        prospect = RawProspect(
            business_name="Test Dental",
            business_category="dentist",
            city="Melbourne",
            country="Australia",
        )

        message = agent.generate_message(prospect)

        assert prospect.metadata.get("message_source") == "template"
        assert "Test Dental" in message
        assert "dentist" in message.lower() or "dental" in message.lower()

    def test_llm_success_sets_metadata(self):
        """When LLM succeeds, message_source is 'llm'."""
        from app.agents.personalization import PersonalizationAgent
        from app.sources.base import RawProspect

        agent = PersonalizationAgent.__new__(PersonalizationAgent)
        agent.llm = MagicMock()
        agent.llm.is_configured = True
        agent.llm.generate.return_value = "Subject: Test\n\nHi team,"

        prospect = RawProspect(
            business_name="Test Dental",
            business_category="dentist",
            city="Melbourne",
            country="Australia",
        )

        message = agent.generate_message(prospect)

        assert prospect.metadata.get("message_source") == "llm"
        assert "Subject: Test" in message

    def test_llm_failure_falls_back_to_template(self):
        """When LLM raises an exception, falls back to template and marks it."""
        from app.agents.personalization import PersonalizationAgent
        from app.sources.base import RawProspect

        agent = PersonalizationAgent.__new__(PersonalizationAgent)
        agent.llm = MagicMock()
        agent.llm.is_configured = True
        agent.llm.generate.side_effect = Exception("429 rate limit")

        prospect = RawProspect(
            business_name="Test Dental",
            business_category="dentist",
            city="Melbourne",
            country="Australia",
        )

        message = agent.generate_message(prospect)

        # Should fall back to template
        assert prospect.metadata.get("message_source") == "template"
        assert "Test Dental" in message
        # Should NOT be the LLM response
        assert "Subject: A simpler way" in message
