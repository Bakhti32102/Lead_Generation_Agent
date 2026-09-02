"""
WhatsApp Business API integration.
Uses the official Meta Cloud API for WhatsApp Business.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from app.config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://graph.facebook.com/v25.0"


class WhatsAppClient:
    """Official WhatsApp Business API client."""

    def __init__(self):
        self.access_token = settings.whatsapp.access_token
        self.phone_number_id = settings.whatsapp.phone_number_id
        self.business_account_id = settings.whatsapp.business_account_id

    @property
    def is_configured(self) -> bool:
        return settings.whatsapp.is_configured

    def send_text(
        self,
        to_number: str,
        message: str,
    ) -> dict:
        """
        Send a text message via WhatsApp Business API.
        to_number: should include country code, e.g. "+923001234567"
        Returns {"success": bool, "message": str, "id": str}.
        """
        if not self.is_configured:
            return {
                "success": False,
                "message": "WhatsApp API not configured",
                "id": "",
            }

        if not to_number:
            return {
                "success": False,
                "message": "No phone number provided",
                "id": "",
            }

        try:
            url = f"{BASE_URL}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            payload = {
                "messaging_product": "whatsapp",
                "to": to_number.lstrip("+"),
                "type": "text",
                "text": {"body": message},
            }

            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            data = resp.json()

            if resp.status_code == 200 and "messages" in data:
                msg_id = data["messages"][0].get("id", "")
                logger.info(f"WhatsApp message sent to {to_number}, id={msg_id}")
                return {"success": True, "message": "Sent", "id": msg_id}
            else:
                error_msg = data.get("error", {}).get("message", resp.text)
                logger.error(f"WhatsApp send failed: {error_msg}")
                return {"success": False, "message": error_msg, "id": ""}

        except Exception as e:
            logger.error(f"WhatsApp send error: {e}")
            return {"success": False, "message": str(e), "id": ""}

    def send_template(
        self,
        to_number: str,
        template_name: str,
        language_code: str = "en",
        parameters: Optional[list] = None,
    ) -> dict:
        """Send a pre-approved WhatsApp template message."""
        if not self.is_configured:
            return {"success": False, "message": "WhatsApp API not configured", "id": ""}

        try:
            url = f"{BASE_URL}/{self.phone_number_id}/messages"
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }

            template = {
                "name": template_name,
                "language": {"code": language_code},
            }
            if parameters:
                template["components"] = [
                    {"type": "body", "parameters": [{"type": "text", "text": p} for p in parameters]}
                ]

            payload = {
                "messaging_product": "whatsapp",
                "to": to_number.lstrip("+"),
                "type": "template",
                "template": template,
            }

            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            data = resp.json()

            if resp.status_code == 200 and "messages" in data:
                msg_id = data["messages"][0].get("id", "")
                return {"success": True, "message": "Template sent", "id": msg_id}
            else:
                error_msg = data.get("error", {}).get("message", resp.text)
                return {"success": False, "message": error_msg, "id": ""}

        except Exception as e:
            logger.error(f"WhatsApp template send error: {e}")
            return {"success": False, "message": str(e), "id": ""}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
whatsapp_client = WhatsAppClient()
