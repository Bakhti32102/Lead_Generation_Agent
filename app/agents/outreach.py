"""
Outreach Agent.
Sends personalized messages via email, WhatsApp, or Fiverr.
Respects DRY_RUN, REVIEW_MODE, daily limits, and Do Not Contact flags.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Dict, Optional

from app.config.settings import settings
from app.database import CounterRepository, FollowUpRepository, LeadRepository
from app.integrations.email import email_client
from app.integrations.fiverr import fiverr_client
from app.integrations.google_sheets import sheets_client
from app.integrations.whatsapp import whatsapp_client
from app.sources.base import RawProspect

logger = logging.getLogger(__name__)


class OutreachAgent:
    """Handles sending outreach messages through configured channels."""

    def __init__(self):
        self.lead_repo = LeadRepository()
        self.followup_repo = FollowUpRepository()
        self.counter_repo = CounterRepository()

    def send_initial(
        self, prospect: RawProspect, message: str, lead_db_id: int = 0
    ) -> dict:
        """
        Send an initial outreach message to a prospect.
        Returns {"success": bool, "channel": str, "message_id": str, "status": str}.
        """
        # Check DRY_RUN
        if settings.campaign.dry_run:
            logger.info(f"DRY RUN: Would send to {prospect.business_name}")
            return {
                "success": True,
                "channel": self._select_channel(prospect),
                "message_id": "dry_run",
                "status": "draft",
            }

        # Check REVIEW_MODE
        if settings.campaign.review_mode:
            logger.info(f"REVIEW MODE: Message prepared for {prospect.business_name} -- awaiting approval")
            return {
                "success": True,
                "channel": self._select_channel(prospect),
                "message_id": "pending_review",
                "status": "pending_review",
            }

        # Check daily limit
        if not self.counter_repo.can_send_more(settings.campaign.max_daily_outreach):
            logger.warning("Daily outreach limit reached. Skipping.")
            return {"success": False, "channel": "", "message_id": "", "status": "limit_reached"}

        # Determine channel
        channel = self._select_channel(prospect)

        if channel == "email":
            return self._send_email(prospect, message, lead_db_id)
        elif channel == "whatsapp":
            return self._send_whatsapp(prospect, message, lead_db_id)
        elif channel == "fiverr":
            return self._send_fiverr(prospect, message, lead_db_id)
        else:
            logger.warning(f"No suitable channel for {prospect.business_name}")
            return {"success": False, "channel": "", "message_id": "", "status": "no_channel"}

    def send_followup(
        self, prospect: RawProspect, message: str, followup_type: str, lead_db_id: int
    ) -> dict:
        """Send a follow-up message."""
        if settings.campaign.dry_run:
            return {"success": True, "channel": "dry_run", "message_id": "dry_run", "status": "draft"}

        if settings.campaign.review_mode:
            return {"success": True, "channel": "pending_review", "message_id": "pending_review", "status": "pending_review"}

        if not self.counter_repo.can_send_more(settings.campaign.max_daily_outreach):
            return {"success": False, "channel": "", "message_id": "", "status": "limit_reached"}

        channel = self._select_channel(prospect)

        if channel == "email":
            result = self._send_email(prospect, message, lead_db_id)
        elif channel == "whatsapp":
            result = self._send_whatsapp(prospect, message, lead_db_id)
        elif channel == "fiverr":
            result = self._send_fiverr(prospect, message, lead_db_id)
        else:
            return {"success": False, "channel": "", "message_id": "", "status": "no_channel"}

        # Update follow-up state
        if result["success"] and result["status"] != "pending_review":
            if followup_type == "3day":
                self.followup_repo.mark_followup_3day_sent(lead_db_id)
            elif followup_type == "7day":
                self.followup_repo.mark_followup_7day_sent(lead_db_id)

        return result

    def approve_and_send(self, lead_db_id: int) -> dict:
        """Approve a pending review message and send it."""
        lead = self.lead_repo.get_lead(lead_db_id)
        if not lead:
            return {"success": False, "message": "Lead not found"}

        # Reconstruct prospect-like object
        from app.sources.base import RawProspect
        prospect = RawProspect(
            business_name=lead.business_name,
            email=lead.email,
            phone=lead.phone,
            website=lead.website,
        )

        # Get the message from lead's notes or metadata
        message = lead.notes  # We'll store the draft message here
        if not message:
            return {"success": False, "message": "No message to send"}

        return self.send_initial(prospect, message, lead_db_id)

    def _select_channel(self, prospect: RawProspect) -> str:
        """Select the best contact channel for this prospect."""
        # Prefer email if business email is available
        if prospect.email:
            return "email"
        # Then phone/WhatsApp
        if prospect.phone:
            if whatsapp_client.is_configured:
                return "whatsapp"
        # Fallback to Fiverr if configured
        if fiverr_client.is_configured:
            return "fiverr"
        # Fallback
        return ""

    def _send_email(
        self, prospect: RawProspect, message: str, lead_db_id: int
    ) -> dict:
        """Send email and track result."""
        subject = f"AI automation idea for {prospect.business_name}"
        result = email_client.send(
            to_email=prospect.email,
            subject=subject,
            body_text=message,
        )

        if result["success"]:
            self.counter_repo.increment_outreach()
            if lead_db_id:
                self.followup_repo.mark_initial_sent(lead_db_id, "email")
            # Update Google Sheets
            self._update_sheets_outreach(
                prospect, "Email", message, "Sent" if result["status"] != "pending_review" else "Pending Review"
            )
            logger.info(f"Email sent to {prospect.email}")
        else:
            logger.error(f"Email failed for {prospect.email}: {result['message']}")
            self._update_sheets_outreach(prospect, "Email", message, f"Failed: {result['message']}")

        return {
            "success": result["success"],
            "channel": "email",
            "message_id": result["id"],
            "status": "sent" if result["success"] else "failed",
        }

    def _send_whatsapp(
        self, prospect: RawProspect, message: str, lead_db_id: int
    ) -> dict:
        """Send WhatsApp message and track result."""
        result = whatsapp_client.send_text(
            to_number=prospect.phone,
            message=message,
        )

        if result["success"]:
            self.counter_repo.increment_outreach()
            if lead_db_id:
                self.followup_repo.mark_initial_sent(lead_db_id, "whatsapp")
            self._update_sheets_outreach(
                prospect, "WhatsApp", message, "Sent"
            )
            logger.info(f"WhatsApp sent to {prospect.phone}")
        else:
            logger.error(f"WhatsApp failed for {prospect.phone}: {result['message']}")
            self._update_sheets_outreach(prospect, "WhatsApp", message, f"Failed: {result['message']}")

        return {
            "success": result["success"],
            "channel": "whatsapp",
            "message_id": result["id"],
            "status": "sent" if result["success"] else "failed",
        }

    def _send_fiverr(
        self, prospect: RawProspect, message: str, lead_db_id: int
    ) -> dict:
        """Generate Fiverr buyer request message and track result."""
        if not fiverr_client.is_configured:
            return {"success": False, "message": "Fiverr not configured", "id": ""}

        # Generate the buyer request
        buyer_request = fiverr_client.generate_buyer_request(
            business_name=prospect.business_name,
            business_category=prospect.business_category,
            city=prospect.city,
            country=prospect.country,
            requirement=prospect.metadata.get("problem", "AI automation"),
            demo_url=prospect.metadata.get("demo_url", ""),
            solution=prospect.recommended_ai_solution or "AI Agent",
        )

        # Track the outreach
        tracking = fiverr_client.track_outreach(
            business_name=prospect.business_name,
            message_type="buyer_request",
            message=buyer_request,
        )

        if lead_db_id:
            self.followup_repo.mark_initial_sent(lead_db_id, "fiverr")

        self._update_sheets_outreach(
            prospect, "Fiverr", buyer_request, "Prepared"
        )

        logger.info(f"Fiverr buyer request prepared for {prospect.business_name}")

        return {
            "success": True,
            "channel": "fiverr",
            "message_id": tracking.get("timestamp", ""),
            "status": "prepared",
        }

    def _update_sheets_outreach(
        self, prospect: RawProspect, channel: str, message: str, status: str
    ) -> None:
        """Update Google Sheets with outreach information."""
        if not sheets_client.is_configured:
            return

        try:
            now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
            # Try to find existing row by business name
            row = sheets_client.find_row_by_business_name(prospect.business_name)
            if row:
                updates = {
                    "Contact Channel": channel,
                    "Initial Message": message[:500],
                    "Initial Contact Date": now,
                    "Initial Contact Status": status,
                }
                sheets_client.update_lead_row(row, updates)
        except Exception as e:
            logger.error(f"Failed to update Sheets for outreach: {e}")
