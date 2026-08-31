"""Tests for follow-up integration: 3-day and 7-day timing with database."""

import datetime as _dt
import pytest

from app.database.models import get_session, FollowUpState
from app.database.repository import FollowUpRepository, LeadRepository, CounterRepository


class TestFollowUpStateManagement:
    """Test follow-up state creation, updates, and queries."""

    def test_create_state(self):
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=88001, initial_channel="email")
        assert state.lead_id == 88001
        assert state.initial_channel == "email"
        assert state.overall_status == "active"

    def test_mark_initial_sent(self):
        repo = FollowUpRepository()
        repo.create_state(lead_id=88002)
        repo.mark_initial_sent(88002, "email", sheets_row_id="5")

        state = repo.get_by_lead_id(88002)
        assert state.initial_status == "sent"
        assert state.initial_channel == "email"
        assert state.initial_sent_at is not None
        assert state.sheets_row_id == "5"

    def test_mark_3day_sent(self):
        repo = FollowUpRepository()
        repo.create_state(lead_id=88003)
        repo.mark_initial_sent(88003, "whatsapp")
        repo.mark_followup_3day_sent(88003)

        state = repo.get_by_lead_id(88003)
        assert state.followup_3day_status == "sent"
        assert state.followup_3day_sent_at is not None

    def test_mark_7day_sent_completes(self):
        repo = FollowUpRepository()
        repo.create_state(lead_id=88004)
        repo.mark_initial_sent(88004, "email")
        repo.mark_followup_7day_sent(88004)

        state = repo.get_by_lead_id(88004)
        assert state.followup_7day_status == "sent"
        assert state.overall_status == "completed"

    def test_due_followups_3day_requires_old_initial(self):
        """3-day follow-up should only be due if initial was sent >3 days ago."""
        repo = FollowUpRepository()
        repo.create_state(lead_id=88005)

        # Update via SQLAlchemy session directly
        session = get_session()
        state = session.query(FollowUpState).filter_by(lead_id=88005).first()
        state.initial_status = "sent"
        state.initial_sent_at = _dt.datetime.utcnow() - _dt.timedelta(days=4)
        state.followup_3day_status = "pending"
        state.overall_status = "active"
        state.do_not_contact = False
        session.commit()
        session.close()

        due = repo.get_due_followups_3day()
        due_ids = [d.lead_id for d in due]
        assert 88005 in due_ids

    def test_due_followups_excludes_stopped(self):
        """Stopped leads should not appear in due follow-ups."""
        repo = FollowUpRepository()
        repo.create_state(lead_id=88006)
        repo.mark_initial_sent(88006, "email")
        repo.stop_followups(88006)

        due = repo.get_due_followups_3day()
        due_ids = [d.lead_id for d in due]
        assert 88006 not in due_ids

    def test_due_followups_excludes_dnc(self):
        """Do Not Contact leads should not appear in due follow-ups."""
        repo = FollowUpRepository()
        repo.create_state(lead_id=88007)
        repo.mark_initial_sent(88007, "email")
        repo.set_do_not_contact(88007)

        due = repo.get_due_followups_3day()
        due_ids = [d.lead_id for d in due]
        assert 88007 not in due_ids

    def test_response_categories(self):
        """Response classification should update state correctly."""
        from app.agents.follow_up import FollowUpAgent
        agent = FollowUpAgent()
        repo = FollowUpRepository()
        repo.create_state(lead_id=88008)

        agent.handle_reply(88008, "not_interested")
        state = repo.get_by_lead_id(88008)
        assert state.do_not_contact is True
        assert state.overall_status == "stopped"

    def test_interested_stops_followups(self):
        """Interested response should stop follow-ups."""
        from app.agents.follow_up import FollowUpAgent
        agent = FollowUpAgent()
        repo = FollowUpRepository()
        repo.create_state(lead_id=88009)

        agent.handle_reply(88009, "interested")
        state = repo.get_by_lead_id(88009)
        assert state.overall_status == "stopped"
        assert state.do_not_contact is False

    def test_human_required_escalates(self):
        """Human required response should flag for escalation."""
        from app.agents.follow_up import FollowUpAgent
        agent = FollowUpAgent()
        repo = FollowUpRepository()
        repo.create_state(lead_id=88010)

        agent.handle_reply(88010, "wants_meeting")
        state = repo.get_by_lead_id(88010)
        assert state.human_required is True
        assert state.overall_status == "stopped"


class TestCounterRepository:
    """Test the daily counter persistence."""

    def test_increment_and_read(self):
        repo = CounterRepository()
        test_date = "2099-06-15"
        initial = repo.get_outreach_count(test_date)
        repo.increment_outreach(test_date)
        repo.increment_outreach(test_date)
        repo.increment_outreach(test_date)

        count = repo.get_outreach_count(test_date)
        assert count == initial + 3

    def test_can_send_more(self):
        repo = CounterRepository()
        test_date = "2099-06-16"
        initial = repo.get_outreach_count(test_date)
        repo.increment_outreach(test_date)
        after = repo.get_outreach_count(test_date)

        assert repo.can_send_more(after + 5, test_date) is True
        assert repo.can_send_more(after, test_date) is False
