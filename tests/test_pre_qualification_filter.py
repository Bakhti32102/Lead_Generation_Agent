"""
Tests for the 3-step pre-qualification filter.

A lead is skipped when ALL THREE are True:
  1. Has website
  2. Has website AI chatbot
  3. Has WhatsApp AI automation

Otherwise the lead proceeds with tagged automation_gaps.

Note: All test prospects include a reachable contact channel (email or
WhatsApp) to pass the strict contact filter before reaching automation check.
"""

import pytest
from app.agents.lead_verification import LeadVerificationAgent
from app.sources.base import RawProspect


class TestPreQualificationFilter:
    """3-step filter: website + website chatbot + WhatsApp automation."""

    def _make(self, **kwargs) -> RawProspect:
        defaults = dict(
            business_name="Test Clinic",
            business_category="dentist",
            city="Karachi",
            country="Pakistan",
            email="info@testclinic.com",  # Reachable channel required
        )
        defaults.update(kwargs)
        return RawProspect(**defaults)

    # ── Skip when fully automated ──

    def test_skip_when_all_three_present(self):
        """Website + chatbot + WhatsApp automation → skip."""
        p = self._make(
            website="https://clinic.com",
            metadata={
                "snippet": "We use tidio chatbot on our website and whatsapp automation for patients",
            },
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert result.metadata["skip_reason"] == "Already fully automated"
        assert result.metadata["automation_check"]["fully_automated"] is True

    def test_skip_when_chatbot_and_whatsapp_in_research(self):
        """Chatbot and WhatsApp signals in business_research → skip."""
        p = self._make(
            website="https://clinic.pk",
            business_research="The clinic uses whatsapp business api for patient queries and has a livechat widget on their website.",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["skip_reason"] == "Already fully automated"
        assert result.metadata["automation_check"]["has_website_chatbot"] is True
        assert result.metadata["automation_check"]["has_whatsapp_automation"] is True

    # ── Proceed when any one is missing ──

    def test_reject_when_no_website_and_no_other_contact(self):
        """No website + no phone + no email → rejected immediately."""
        p = self._make(website="", phone="", email="")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "reachable contact channel" in result.metadata["skip_reason"]

    def test_proceed_when_no_chatbot(self):
        """Website exists but no chatbot signals → proceed."""
        p = self._make(
            website="https://clinic.com",
            metadata={"snippet": "A dental clinic in Karachi offering general checkups"},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        check = result.metadata["automation_check"]
        assert check["has_website"] is True
        assert check["has_website_chatbot"] is False
        assert check["fully_automated"] is False
        # automation_gaps should list what's missing
        gaps = result.metadata.get("automation_gaps", [])
        assert "website AI chatbot" in gaps
        assert "WhatsApp AI automation" in gaps

    def test_proceed_when_no_whatsapp(self):
        """Has website + chatbot but no WhatsApp automation → proceed."""
        p = self._make(
            website="https://clinic.com",
            metadata={"snippet": "We use intercom chat widget on our site for customer support"},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        check = result.metadata["automation_check"]
        assert check["has_website_chatbot"] is True
        assert check["has_whatsapp_automation"] is False
        assert check["fully_automated"] is False
        gaps = result.metadata.get("automation_gaps", [])
        assert "WhatsApp AI automation" in gaps

    def test_proceed_when_only_website(self):
        """Just a website, no bot signals → proceed with two gaps."""
        p = self._make(website="https://clinic.com")
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        check = result.metadata["automation_check"]
        assert check["has_website"] is True
        assert check["has_website_chatbot"] is False
        assert check["has_whatsapp_automation"] is False
        assert check["fully_automated"] is False
        gaps = result.metadata.get("automation_gaps", [])
        assert "website AI chatbot" in gaps
        assert "WhatsApp AI automation" in gaps

    # ── Multiple signal detection ──

    def test_tidio_detected(self):
        """Tidio in website URL → chatbot detected."""
        p = self._make(
            website="https://clinic.tidio.com/chat",
            metadata={"snippet": ""},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        check = result.metadata["automation_check"]
        assert check["has_website_chatbot"] is True

    def test_whatsapp_api_detected(self):
        """api.whatsapp in metadata → WhatsApp automation detected."""
        p = self._make(
            website="https://clinic.com",
            metadata={"snippet": "Contact us via api.whatsapp.com/send for instant replies"},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        check = result.metadata["automation_check"]
        assert check["has_whatsapp_automation"] is True

    def test_crisp_chat_detected(self):
        """crisp.chat in snippet → chatbot detected."""
        p = self._make(
            website="https://clinic.com",
            metadata={"snippet": "Powered by crisp.chat for live customer support"},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        check = result.metadata["automation_check"]
        assert check["has_website_chatbot"] is True

    # ── Bounded source still gets filtered ──

    def test_bounded_source_still_filtered(self):
        """OSM source with all three automation layers → still skipped."""
        p = self._make(
            source="openstreetmap",
            website="https://clinic.com",
            phone="+923001234567",  # WhatsApp-capable mobile
            email="",
            metadata={"snippet": "We use whatsapp business api and tidio chat widget"},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["skip_reason"] == "Already fully automated"

    # ── No false positives ──

    def test_no_false_positive_on_clean_business(self):
        """Normal business with no automation signals → not skipped."""
        p = self._make(
            website="https://smiledental.pk",
            metadata={"snippet": "Smile Dental Clinic offers teeth whitening in Karachi"},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["automation_check"]["fully_automated"] is False
        assert result.metadata.get("skip_reason") is None
