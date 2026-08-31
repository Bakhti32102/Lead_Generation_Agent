"""
APScheduler-based Scheduler.
Runs daily campaigns and follow-up processing automatically.
"""

from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

from app.config.settings import settings
from app.database.models import init_db

logger = logging.getLogger(__name__)


class LeadGenerationScheduler:
    """Scheduler for automatic daily campaign execution."""

    def __init__(self):
        self.scheduler = None
        self._setup_scheduler()

    def _setup_scheduler(self):
        """Initialize the APScheduler."""
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger
            from apscheduler.triggers.interval import IntervalTrigger

            self.scheduler = BackgroundScheduler()
            self.CronTrigger = CronTrigger
            self.IntervalTrigger = IntervalTrigger
            self._BackgroundScheduler = BackgroundScheduler
        except ImportError:
            logger.error("APScheduler not installed. Install with: pip install apscheduler")
            return

    def start(self, interval_hours: int = 24):
        """Start the scheduler."""
        if not self.scheduler:
            logger.error("Scheduler not initialized. Install apscheduler.")
            return

        init_db()
        logger.info("Starting Lead Generation Scheduler...")

        # Schedule daily campaign
        self.scheduler.add_job(
            func=self._run_daily_campaign,
            trigger=self.IntervalTrigger(hours=interval_hours),
            id="daily_campaign",
            name="Daily Lead Generation Campaign",
            replace_existing=True,
        )

        # Schedule follow-up processing (runs every 6 hours)
        self.scheduler.add_job(
            func=self._run_followups,
            trigger=self.IntervalTrigger(hours=6),
            id="followup_processing",
            name="Follow-up Processing",
            replace_existing=True,
        )

        # Schedule daily report generation
        self.scheduler.add_job(
            func=self._generate_daily_report,
            trigger=self.CronTrigger(hour=23, minute=59),
            id="daily_report",
            name="Daily Report Generation",
            replace_existing=True,
        )

        # Handle graceful shutdown
        def signal_handler(sig, frame):
            logger.info("Shutting down scheduler...")
            self.stop()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        self.scheduler.start()
        logger.info(f"Scheduler started. Campaigns every {interval_hours} hours.")
        logger.info("Press Ctrl+C to stop.")

        # Keep the main thread alive
        try:
            while True:
                import time
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self.stop()

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
                logger.info("Scheduler stopped.")
            except Exception:
                pass  # Scheduler may not be running

    def _run_daily_campaign(self):
        """Execute a daily campaign."""
        logger.info("Running scheduled daily campaign...")
        try:
            from app.scheduler.daily_campaign import DailyCampaign
            campaign = DailyCampaign()
            summary = campaign.run()
            logger.info(f"Scheduled campaign completed: {summary['status']}")
            logger.info(f"  Discovered: {summary['discovered']}, Qualified: {summary['qualified']}, Final: {summary['final_leads']}")
        except Exception as e:
            logger.error(f"Scheduled campaign failed: {e}", exc_info=True)

    def _run_followups(self):
        """Process due follow-ups."""
        logger.info("Running scheduled follow-up processing...")
        try:
            from app.scheduler.followups import FollowUpScheduler
            scheduler = FollowUpScheduler()
            results = scheduler.run()
            logger.info(f"Follow-up processing completed: {results}")
        except Exception as e:
            logger.error(f"Follow-up processing failed: {e}", exc_info=True)

    def _generate_daily_report(self):
        """Generate daily report."""
        logger.info("Generating daily report...")
        try:
            from app.scheduler.daily_campaign import DailyCampaign
            campaign = DailyCampaign()
            # Just generate the report without running a new campaign
            from app.config.settings import LOG_DIR
            report_file = LOG_DIR / f"report_{datetime.now().strftime('%Y-%m-%d')}.txt"

            # Get today's stats
            from app.database import LeadRepository, CampaignRepository
            lead_repo = LeadRepository()
            campaign_repo = CampaignRepository()

            today_leads = lead_repo.get_qualified_leads_for_date()
            today_run = campaign_repo.get_today_run()

            report = f"""
Daily Report - {datetime.now().strftime('%Y-%m-%d %H:%M')}

Campaign Status: {today_run.status if today_run else 'No campaign today'}
Discovered: {today_run.discovered_count if today_run else 0}
Qualified: {today_run.qualified_count if today_run else 0}
Final Leads: {today_run.final_count if today_run else 0}
Emails Sent: {today_run.emails_sent if today_run else 0}
WhatsApp Sent: {today_run.whatsapp_sent if today_run else 0}

Total Qualified Leads: {len(today_leads)}
"""
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report)
            logger.info(f"Daily report saved to {report_file}")
        except Exception as e:
            logger.error(f"Daily report generation failed: {e}", exc_info=True)
