"""
Escalation Agent.
Handles human escalation for complex cases, pricing questions,
meeting requests, complaints, and sensitive issues.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config.settings import settings
from app.integrations.email import email_client

logger = logging.getLogger(__name__)


class EscalationAgent:
    """Manages escalation of cases requiring human intervention."""

    def escalate(
        self,
        business_name: str,
        reason: str,
        details: str = "",
        contact_info: str = "",
    ) -> bool:
        """
        Escalate a case to the human operator.
        Sends a notification via the configured method.
        Returns True if notification was sent.
        """
        notification_method = settings.notification.method

        if notification_method == "email":
            return self._escalate_email(business_name, reason, details, contact_info)
        else:
            logger.warning(f"Unknown notification method: {notification_method}")
            return False

    def _escalate_email(
        self,
        business_name: str,
        reason: str,
        details: str = "",
        contact_info: str = "",
    ) -> bool:
        """Send escalation notification via email."""
        if not settings.notification.email:
            logger.warning("No notification email configured.")
            return False

        subject = f"[ACTION REQUIRED] Lead Escalation: {business_name}"

        body = f"""Lead Escalation Notification

Business: {business_name}
Reason: {reason}
Contact: {contact_info}

Details:
{details}

---
This is an automated escalation from the Lead Generation Agent.
Please review and take appropriate action.
"""

        result = email_client.send(
            to_email=settings.notification.email,
            subject=subject,
            body_text=body,
        )

        if result["success"]:
            logger.info(f"Escalation email sent for {business_name}")
            return True
        else:
            logger.error(f"Escalation email failed: {result['message']}")
            return False

    def should_escalate(self, response_category: str) -> bool:
        """Determine if a response category requires escalation."""
        escalation_categories = {
            "wants_meeting",
            "wants_proposal",
            "wants_pricing",
            "technical_question",
            "human_required",
        }
        return response_category in escalation_categories
