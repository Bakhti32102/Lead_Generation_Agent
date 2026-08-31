"""
Follow-up Agent.
Manages the automated 3-day and 7-day follow-up sequences.
Respects all stop conditions and daily limits.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import List, Optional

from app.config.settings import settings
from app.database import FollowUpRepository, LeadRepository
from app.database.models import DiscoveredLead
from app.agents.outreach import OutreachAgent
from app.agents.personalization import PersonalizationAgent
from app.integrations.google_sheets import sheets_client

logger = logging.getLogger(__name__)


class FollowUpAgent:
    """Manages follow-up sequences for outreach leads."""

    def __init__(self):
        self.followup_repo = FollowUpRepository()
        self.lead_repo = LeadRepository()
        self.outreach = OutreachAgent()
        self.personalizer = PersonalizationAgent()

    def process_3day_followups(self) -> dict:
        """
        Process all leads due for 3-day follow-up.
        Returns summary of actions taken.
        """
        due_leads = self.followup_repo.get_due_followups_3day()
        logger.info(f"3-day follow-ups due: {len(due_leads)}")

        sent = 0
        failed = 0
        skipped = 0

        for state in due_leads:
            lead = self.lead_repo.get_lead(state.lead_id)
            if not lead:
                logger.warning(f"Lead not found for follow-up state {state.id}")
                continue

            # Reconstruct prospect
            prospect = self._lead_to_prospect(lead)

            # Check stop conditions
            if self._should_stop(prospect, lead):
                self.followup_repo.stop_followups(state.lead_id)
                skipped += 1
                continue

            # Check daily limit
            from app.database import CounterRepository
            if not CounterRepository().can_send_more(settings.campaign.max_daily_outreach):
                logger.warning("Daily limit reached during follow-up processing.")
                break

            # Generate follow-up message
            message = self.personalizer.generate_followup_message(prospect, "3day")

            # Send
            result = self.outreach.send_followup(
                prospect, message, "3day", state.lead_id
            )

            if result["success"]:
                sent += 1
                # Update Google Sheets
                self._update_sheets_followup(lead, "3-day", message)
            else:
                failed += 1
                logger.error(f"3-day follow-up failed for {lead.business_name}")

        summary = {
            "3day_total": len(due_leads),
            "3day_sent": sent,
            "3day_failed": failed,
            "3day_skipped": skipped,
        }
        logger.info(f"3-day follow-up summary: {summary}")
        return summary

    def process_7day_followups(self) -> dict:
        """
        Process all leads due for 7-day follow-up.
        Returns summary of actions taken.
        """
        due_leads = self.followup_repo.get_due_followups_7day()
        logger.info(f"7-day follow-ups due: {len(due_leads)}")

        sent = 0
        failed = 0
        skipped = 0

        for state in due_leads:
            lead = self.lead_repo.get_lead(state.lead_id)
            if not lead:
                continue

            prospect = self._lead_to_prospect(lead)

            if self._should_stop(prospect, lead):
                self.followup_repo.stop_followups(state.lead_id)
                skipped += 1
                continue

            from app.database import CounterRepository
            if not CounterRepository().can_send_more(settings.campaign.max_daily_outreach):
                break

            message = self.personalizer.generate_followup_message(prospect, "7day")

            result = self.outreach.send_followup(
                prospect, message, "7day", state.lead_id
            )

            if result["success"]:
                sent += 1
                self._update_sheets_followup(lead, "7-day", message)
            else:
                failed += 1

        summary = {
            "7day_total": len(due_leads),
            "7day_sent": sent,
            "7day_failed": failed,
            "7day_skipped": skipped,
        }
        logger.info(f"7-day follow-up summary: {summary}")
        return summary

    def process_all_followups(self) -> dict:
        """Process both 3-day and 7-day follow-ups."""
        result_3 = self.process_3day_followups()
        result_7 = self.process_7day_followups()
        return {**result_3, **result_7}

    def stop_followups_for_lead(self, lead_id: int) -> None:
        """Stop all follow-ups for a specific lead."""
        self.followup_repo.stop_followups(lead_id)
        logger.info(f"Follow-ups stopped for lead {lead_id}")

    def mark_do_not_contact(self, lead_id: int) -> None:
        """Mark a lead as Do Not Contact."""
        self.followup_repo.set_do_not_contact(lead_id)
        logger.info(f"Lead {lead_id} marked as Do Not Contact")

    def handle_reply(self, lead_id: int, category: str) -> None:
        """Handle a prospect's reply. Classify and take appropriate action."""
        self.followup_repo.update_response(lead_id, category)

        if category in ("not_interested", "already_has_solution"):
            self.followup_repo.set_do_not_contact(lead_id)
        elif category == "human_required":
            self.followup_repo.set_human_required(lead_id)
        elif category in ("wants_meeting", "wants_proposal", "wants_pricing"):
            self.followup_repo.set_human_required(lead_id)
            self.followup_repo.stop_followups(lead_id)
        elif category in ("interested", "wants_demo"):
            self.followup_repo.stop_followups(lead_id)

        logger.info(f"Lead {lead_id} reply handled: category={category}")

    def _should_stop(self, prospect: RawProspect, lead: DiscoveredLead) -> bool:
        """Check if we should stop following up with this lead."""
        # Stop conditions
        if lead.dedup_email and prospect.email == "":
            return True
        # Check if manually marked in Google Sheets (Do Not Contact)
        if sheets_client.is_configured:
            try:
                row = sheets_client.find_row_by_lead_id(str(lead.id))
                if row:
                    rows = sheets_client.read_all_rows()
                    for r in rows:
                        if r.get("Lead ID") == str(lead.id):
                            if r.get("Do Not Contact", "").upper() == "YES":
                                self.followup_repo.set_do_not_contact(lead.id)
                                return True
                            break
            except Exception:
                pass
        return False

    def _lead_to_prospect(self, lead: DiscoveredLead) -> 'RawProspect':
        """Convert a database lead to a RawProspect for message generation."""
        from app.sources.base import RawProspect
        return RawProspect(
            business_name=lead.business_name,
            business_category=lead.business_category,
            country=lead.country,
            city=lead.city,
            address=lead.address,
            phone=lead.phone,
            email=lead.email,
            website=lead.website,
            google_maps_url=lead.google_maps_url,
            source=lead.source,
            potential_problem=lead.potential_problem,
            recommended_service=lead.recommended_service,
            recommended_ai_solution=lead.recommended_ai_solution,
            lead_score=lead.lead_score,
        )

    def _update_sheets_followup(
        self, lead: DiscoveredLead, followup_type: str, message: str
    ) -> None:
        """Update Google Sheets with follow-up information."""
        if not sheets_client.is_configured:
            return
        try:
            now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            row = sheets_client.find_row_by_lead_id(str(lead.id))
            if row:
                col = f"Follow-up {followup_type}"
                status = f"Sent — {now}"
                updates = {
                    col: f"{status}: {message[:200]}",
                    "Follow-up Status": "Active",
                }
                sheets_client.update_lead_row(row, updates)
        except Exception as e:
            logger.error(f"Failed to update Sheets for follow-up: {e}")


# Needed for type hints
from app.sources.base import RawProspect
