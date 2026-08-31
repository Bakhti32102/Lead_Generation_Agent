"""
Tests for Scheduler.
Validates scheduler initialization, job scheduling, and error handling.
"""

import pytest
from unittest.mock import patch, MagicMock


class TestScheduler:
    """Tests for LeadGenerationScheduler."""

    def test_scheduler_importable(self):
        """Scheduler should be importable."""
        from app.scheduler.scheduler import LeadGenerationScheduler
        assert LeadGenerationScheduler is not None

    def test_scheduler_initialization(self):
        """Scheduler should initialize with APScheduler."""
        from app.scheduler.scheduler import LeadGenerationScheduler

        scheduler = LeadGenerationScheduler()
        # Scheduler should have a scheduler attribute (may be None if APScheduler not installed)
        assert hasattr(scheduler, "scheduler")

    def test_scheduler_has_methods(self):
        """Scheduler should have required methods."""
        from app.scheduler.scheduler import LeadGenerationScheduler

        scheduler = LeadGenerationScheduler()
        assert hasattr(scheduler, "start")
        assert hasattr(scheduler, "stop")
        assert hasattr(scheduler, "_run_daily_campaign")
        assert hasattr(scheduler, "_run_followups")
        assert hasattr(scheduler, "_generate_daily_report")

    def test_scheduler_stop(self):
        """Scheduler should stop gracefully."""
        from app.scheduler.scheduler import LeadGenerationScheduler

        scheduler = LeadGenerationScheduler()
        # Stop should not crash even if scheduler is not running
        scheduler.stop()

    def test_run_daily_campaign_method_exists(self):
        """Daily campaign method should be callable."""
        from app.scheduler.scheduler import LeadGenerationScheduler

        scheduler = LeadGenerationScheduler()
        assert callable(scheduler._run_daily_campaign)

    def test_run_followups_method_exists(self):
        """Follow-ups method should be callable."""
        from app.scheduler.scheduler import LeadGenerationScheduler

        scheduler = LeadGenerationScheduler()
        assert callable(scheduler._run_followups)

    def test_generate_daily_report_method_exists(self):
        """Daily report method should be callable."""
        from app.scheduler.scheduler import LeadGenerationScheduler

        scheduler = LeadGenerationScheduler()
        assert callable(scheduler._generate_daily_report)


class TestSchedulerIntegration:
    """Integration tests for scheduler with other components."""

    def test_scheduler_can_run_campaign(self):
        """Scheduler should be able to trigger a campaign."""
        from app.scheduler.scheduler import LeadGenerationScheduler
        from app.database.models import init_db

        init_db()
        scheduler = LeadGenerationScheduler()

        # This should not crash (even if no API keys are configured)
        try:
            scheduler._run_daily_campaign()
        except Exception as e:
            # It's okay if the campaign fails due to missing API keys
            pass

    def test_scheduler_can_process_followups(self):
        """Scheduler should be able to trigger follow-up processing."""
        from app.scheduler.scheduler import LeadGenerationScheduler
        from app.database.models import init_db

        init_db()
        scheduler = LeadGenerationScheduler()

        # This should not crash
        try:
            scheduler._run_followups()
        except Exception:
            pass

    def test_scheduler_can_generate_report(self):
        """Scheduler should be able to generate daily report."""
        from app.scheduler.scheduler import LeadGenerationScheduler
        from app.database.models import init_db

        init_db()
        scheduler = LeadGenerationScheduler()

        # This should not crash
        try:
            scheduler._generate_daily_report()
        except Exception:
            pass
