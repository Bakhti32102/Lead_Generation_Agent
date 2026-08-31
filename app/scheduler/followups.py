"""
Follow-ups Scheduler.
Runs daily to check for due follow-ups and process them.
"""

from __future__ import annotations

import logging

from app.database.models import init_db
from app.agents.follow_up import FollowUpAgent

logger = logging.getLogger(__name__)


class FollowUpScheduler:
    """Checks and processes due follow-ups daily."""

    def __init__(self):
        self.agent = FollowUpAgent()

    def run(self) -> dict:
        """Execute all due follow-ups and return summary."""
        init_db()
        logger.info("Starting follow-up processing...")

        results = self.agent.process_all_followups()
        logger.info(f"Follow-up processing complete: {results}")
        return results

    def run_3day_only(self) -> dict:
        """Process only 3-day follow-ups."""
        init_db()
        return self.agent.process_3day_followups()

    def run_7day_only(self) -> dict:
        """Process only 7-day follow-ups."""
        init_db()
        return self.agent.process_7day_followups()
