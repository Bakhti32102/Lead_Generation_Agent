"""Tests for daily lead limits and opt-out mechanisms."""

import datetime as _dt
import pytest


class TestDailyLeadLimit:
    """Daily limits must survive restarts and never be exceeded."""

    def test_counter_starts_at_zero(self):
        """Fresh day counter should start at 0."""
        from app.database import CounterRepository
        repo = CounterRepository()
        test_date = "2099-12-31"
        count = repo.get_outreach_count(test_date)
        assert count == 0

    def test_counter_increments(self):
        """Counter should increment correctly."""
        from app.database import CounterRepository
        repo = CounterRepository()
        test_date = "2099-12-30"
        # Reset to known state
        initial = repo.get_outreach_count(test_date)
        repo.increment_outreach(test_date)
        after = repo.get_outreach_count(test_date)
        assert after == initial + 1

    def test_counter_persists(self):
        """Counter should persist across different instances."""
        from app.database import CounterRepository
        test_date = "2099-12-29"
        repo1 = CounterRepository()
        initial = repo1.get_outreach_count(test_date)
        repo1.increment_outreach(test_date)
        repo1.increment_outreach(test_date)

        repo2 = CounterRepository()
        count = repo2.get_outreach_count(test_date)
        assert count == initial + 2

    def test_can_send_more_respects_limit(self):
        """can_send_more should return False when limit is reached."""
        from app.database import CounterRepository
        repo = CounterRepository()
        test_date = "2099-12-28"
        initial = repo.get_outreach_count(test_date)

        # Increment a few times
        for _ in range(3):
            repo.increment_outreach(test_date)

        after = repo.get_outreach_count(test_date)
        assert repo.can_send_more(after + 5, test_date) is True
        assert repo.can_send_more(after, test_date) is False
        assert repo.can_send_more(after - 1, test_date) is False


class TestOptOut:
    """Do Not Contact must stop all follow-ups."""

    def test_do_not_contact_flag(self):
        """Setting Do Not Contact should stop all follow-ups."""
        from app.database import FollowUpRepository
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=99999)
        repo.set_do_not_contact(99999)

        updated = repo.get_by_lead_id(99999)
        assert updated.do_not_contact is True
        assert updated.overall_status == "stopped"

    def test_stop_followups(self):
        """Explicit stop should set overall_status to stopped."""
        from app.database import FollowUpRepository
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=99998)
        repo.stop_followups(99998)

        updated = repo.get_by_lead_id(99998)
        assert updated.overall_status == "stopped"

    def test_human_required_flag(self):
        """Human required should be set correctly."""
        from app.database import FollowUpRepository
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=99997)
        repo.set_human_required(99997)

        updated = repo.get_by_lead_id(99997)
        assert updated.human_required is True


class TestFollowUpTiming:
    """Follow-up timing logic: 3-day and 7-day windows."""

    def test_initial_sent_creates_state(self):
        """Creating initial sent state should persist correctly."""
        from app.database import FollowUpRepository
        import datetime as _dt
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=99996)
        repo.mark_initial_sent(99996, "email")

        updated = repo.get_by_lead_id(99996)
        assert updated.initial_status == "sent"
        assert updated.initial_channel == "email"
        assert updated.initial_sent_at is not None

    def test_3day_followup_marking(self):
        """3-day follow-up should be marked correctly."""
        from app.database import FollowUpRepository
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=99995)
        repo.mark_initial_sent(99995, "email")
        repo.mark_followup_3day_sent(99995)

        updated = repo.get_by_lead_id(99995)
        assert updated.followup_3day_status == "sent"

    def test_7day_followup_completes_sequence(self):
        """7-day follow-up should set overall_status to completed."""
        from app.database import FollowUpRepository
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=99994)
        repo.mark_initial_sent(99994, "email")
        repo.mark_followup_7day_sent(99994)

        updated = repo.get_by_lead_id(99994)
        assert updated.followup_7day_status == "sent"
        assert updated.overall_status == "completed"

    def test_stopped_lead_not_in_due_followups(self):
        """Stopped leads should not appear in due follow-ups."""
        from app.database import FollowUpRepository
        from datetime import datetime, timedelta
        repo = FollowUpRepository()
        state = repo.create_state(lead_id=99993)

        # Manually set initial_sent_at to 4 days ago
        from app.database.models import get_session, FollowUpState
        session = get_session()
        s = session.query(FollowUpState).filter_by(lead_id=99993).first()
        if s:
            s.initial_status = "sent"
            s.initial_sent_at = datetime.utcnow() - timedelta(days=4)
            session.commit()
        session.close()

        # Stop the lead
        repo.stop_followups(99993)

        # Should not be in due 3-day follow-ups
        due = repo.get_due_followups_3day()
        due_ids = [d.lead_id for d in due]
        assert 99993 not in due_ids
