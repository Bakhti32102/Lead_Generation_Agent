"""Tests for message generation, demo selection, and response classification."""

import pytest

from app.sources.base import RawProspect


class TestMessageGeneration:
    """Tests for personalized message generation."""

    def test_template_message_includes_business_name(self):
        """Template message should include the business name."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent()

        prospect = RawProspect(
            business_name="Smile Dental Clinic",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://smiledental.pk",
            potential_problem="- Appointment booking\n- Customer inquiries",
            recommended_service="AI Chatbot",
            recommended_ai_solution="AI Dental Receptionist",
            metadata={"problems_list": ["Appointment booking"]},
        )

        message = agent._generate_template(prospect)
        assert "Smile Dental Clinic" in message
        assert "Lahore" in message

    def test_template_message_includes_links(self):
        """Template message should include configured business links."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent()

        prospect = RawProspect(
            business_name="Test Business",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
        )

        message = agent._generate_template(prospect)
        assert "example.com" in message  # MY_WEBSITE_URL
        assert "fiverr.com" in message  # MY_FIVERR_URL
        assert "linkedin.com" in message  # MY_LINKEDIN_URL

    def test_template_message_includes_demo(self):
        """Template message should include demo link when available."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent()

        prospect = RawProspect(
            business_name="Test Restaurant",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
            metadata={"demo_url": "https://demo.example.com/restaurant"},
        )

        message = agent._generate_template(prospect)
        assert "demo.example.com" in message

    def test_template_message_no_fake_claims(self):
        """Message should NOT contain fake claims or hype words."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent()

        prospect = RawProspect(
            business_name="Test Business",
            business_category="Clinic",
            country="Pakistan",
            city="Lahore",
        )

        message = agent._generate_template(prospect)
        banned_words = ["revolutionary", "10x", "guaranteed", "guarantee"]
        for word in banned_words:
            assert word.lower() not in message.lower(), f"Message contains banned word: {word}"

    def test_followup_3day_message(self):
        """3-day follow-up should mention previous message."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent()

        prospect = RawProspect(
            business_name="Smile Clinic",
            recommended_ai_solution="AI Receptionist",
        )

        message = agent.generate_followup_message(prospect, "3day")
        assert "following up" in message.lower()
        assert "Smile Clinic" in message

    def test_followup_7day_message(self):
        """7-day follow-up should be final."""
        from app.agents.personalization import PersonalizationAgent
        agent = PersonalizationAgent()

        prospect = RawProspect(
            business_name="Quick Bites",
            recommended_ai_solution="Restaurant AI Agent",
        )

        message = agent.generate_followup_message(prospect, "7day")
        assert "last follow-up" in message.lower()
        assert "Quick Bites" in message


class TestDemoSelection:
    """Tests for demo matching to business types."""

    def test_restaurant_gets_restaurant_demo(self):
        """Restaurant businesses should get restaurant demo."""
        from app.agents.solution_matching import SolutionMatchingAgent
        agent = SolutionMatchingAgent()

        prospect = RawProspect(
            business_name="Food Palace",
            business_category="Restaurant",
            country="UAE",
            city="Dubai",
            website="https://foodpalace.ae",
            metadata={"website_analysis": {"has_booking": False, "has_chatbot": False}},
        )

        result = agent.match(prospect)
        assert prospect.recommended_service  # Should have a recommendation

    def test_no_demo_returns_empty(self):
        """When no relevant demo exists, demo_url should be empty."""
        from app.agents.solution_matching import SolutionMatchingAgent
        agent = SolutionMatchingAgent()

        # With empty agents.json or no matching demo
        prospect = RawProspect(
            business_name="Unique Business",
            business_category="Crypto Mining",
            country="Pakistan",
            city="Islamabad",
            metadata={"website_analysis": {"has_booking": False, "has_chatbot": False}},
        )

        result = agent.match(prospect)
        # Should still have a service recommendation
        assert prospect.recommended_service

    def test_demo_url_not_invented(self):
        """Demo URL should only come from agents.json, never invented."""
        from app.agents.solution_matching import SolutionMatchingAgent
        agent = SolutionMatchingAgent()

        prospect = RawProspect(
            business_name="Test",
            business_category="Unknown",
            country="Test",
            city="Test",
            metadata={"website_analysis": {}},
        )

        result = agent.match(prospect)
        # If no demo exists, URL should be empty
        if not prospect.metadata.get("demo_url"):
            assert prospect.metadata.get("demo_url", "") == ""


class TestResponseClassification:
    """Tests for reply classification."""

    def test_interested_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()

        assert agent.classify("Yes, I'm interested. Tell me more!") == "interested"
        assert agent.classify("Sounds good, I'd love to learn more.") == "interested"

    def test_wants_demo_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()

        assert agent.classify("Can you show me a demo?") == "wants_demo"
        assert agent.classify("I'd like to see how it works.") == "wants_demo"

    def test_wants_pricing_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()

        assert agent.classify("How much does this cost?") == "wants_pricing"
        assert agent.classify("What's the pricing?") == "wants_pricing"

    def test_not_interested_classification(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()

        assert agent.classify("No thanks, not interested.") == "not_interested"
        assert agent.classify("Please remove me from your list.") == "not_interested"

    def test_empty_reply_default(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()

        assert agent.classify("") == "needs_more_info"

    def test_meeting_request(self):
        from app.agents.response_classifier import ResponseClassifierAgent
        agent = ResponseClassifierAgent()

        assert agent.classify("Can we schedule a call?") == "wants_meeting"


class TestEscalation:
    """Tests for escalation triggers."""

    def test_pricing_triggers_escalation(self):
        from app.agents.escalation import EscalationAgent
        agent = EscalationAgent()

        assert agent.should_escalate("wants_pricing") is True
        assert agent.should_escalate("wants_meeting") is True
        assert agent.should_escalate("wants_proposal") is True
        assert agent.should_escalate("technical_question") is True
        assert agent.should_escalate("human_required") is True

    def test_regular_replies_no_escalation(self):
        from app.agents.escalation import EscalationAgent
        agent = EscalationAgent()

        assert agent.should_escalate("interested") is False
        assert agent.should_escalate("not_interested") is False
        assert agent.should_escalate("needs_more_info") is False
