"""
Email integration.
Supports: Gmail API, Resend, SendGrid, SMTP.
Provider is selected via EMAIL_PROVIDER env var.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class EmailClient:
    """Unified email sending interface."""

    def __init__(self):
        self.provider = settings.email.provider
        self.api_key = settings.email.api_key
        self.from_address = settings.email.from_address

    @property
    def is_configured(self) -> bool:
        return settings.email.is_configured

    def send(
        self,
        to_email: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
    ) -> dict:
        """
        Send an email. Returns {"success": bool, "message": str, "id": str}.
        """
        if not self.is_configured:
            return {"success": False, "message": "Email API not configured", "id": ""}

        if not to_email:
            return {"success": False, "message": "No recipient email provided", "id": ""}

        try:
            if self.provider == "resend":
                return self._send_resend(to_email, subject, body_text, body_html)
            elif self.provider == "gmail":
                return self._send_gmail_api(to_email, subject, body_text, body_html)
            elif self.provider == "sendgrid":
                return self._send_sendgrid(to_email, subject, body_text, body_html)
            elif self.provider == "smtp":
                return self._send_smtp(to_email, subject, body_text)
            else:
                return {"success": False, "message": f"Unknown email provider: {self.provider}", "id": ""}
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return {"success": False, "message": str(e), "id": ""}

    def _send_resend(
        self, to_email: str, subject: str, body_text: str, body_html: Optional[str]
    ) -> dict:
        """Send via Resend API."""
        import resend
        resend.api_key = self.api_key

        params = {
            "from": self.from_address,
            "to": [to_email],
            "subject": subject,
            "text": body_text,
        }
        if body_html:
            params["html"] = body_html

        result = resend.Emails.send(params)
        email_id = result.get("id", "")
        logger.info(f"Resend email sent to {to_email}, id={email_id}")
        return {"success": True, "message": "Sent via Resend", "id": email_id}

    def _send_gmail_api(
        self, to_email: str, subject: str, body_text: str, body_html: Optional[str]
    ) -> dict:
        """Send via Gmail API using OAuth2 credentials."""
        from base64 import urlsafe_b64encode
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        from googleapiclient.discovery import build

        creds = self._get_gmail_oauth_credentials()
        service = build("gmail", "v1", credentials=creds)

        msg = MIMEMultipart("alternative")
        msg["to"] = to_email
        msg["from"] = self.from_address
        msg["subject"] = subject
        msg.attach(MIMEText(body_text, "plain"))
        if body_html:
            msg.attach(MIMEText(body_html, "html"))

        raw = urlsafe_b64encode(msg.as_bytes()).decode()
        result = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        email_id = result.get("id", "")
        logger.info(f"Gmail API email sent to {to_email}, id={email_id}")
        return {"success": True, "message": "Sent via Gmail API", "id": email_id}

    def _get_gmail_oauth_credentials(self):
        """Get OAuth2 credentials for Gmail API. Auto-refreshes expired tokens."""
        import json
        from pathlib import Path

        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request

        # Gmail token file — separate from Google Sheets token (different scopes)
        gmail_token_path = Path(settings.google_sheets.token_path).parent / "gmail_token.json"

        if not gmail_token_path.exists():
            raise FileNotFoundError(
                f"Gmail OAuth token not found: {gmail_token_path}\n"
                f"Run: python -m app.auth_gmail"
            )

        creds = Credentials.from_authorized_user_file(
            str(gmail_token_path),
            scopes=["https://www.googleapis.com/auth/gmail.send"],
        )

        # Auto-refresh if expired
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Save refreshed token
            with open(gmail_token_path, "w") as f:
                json.dump({
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": list(creds.scopes or []),
                }, f)
            logger.info("Gmail OAuth token refreshed.")

        return creds

    def _send_sendgrid(
        self, to_email: str, subject: str, body_text: str, body_html: Optional[str]
    ) -> dict:
        """Send via SendGrid API."""
        import requests

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        content = [{"type": "text/plain", "value": body_text}]
        if body_html:
            content.append({"type": "text/html", "value": body_html})

        payload = {
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": self.from_address},
            "subject": subject,
            "content": content,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        success = resp.status_code in (200, 202)
        email_id = resp.headers.get("X-Message-Id", "") if success else ""
        logger.info(f"SendGrid email to {to_email}: status={resp.status_code}")
        return {
            "success": success,
            "message": f"Status {resp.status_code}",
            "id": email_id,
        }

    def _send_smtp(self, to_email: str, subject: str, body_text: str) -> dict:
        """Send via SMTP (requires EMAIL_SMTP_HOST, EMAIL_SMTP_PORT, EMAIL_SMTP_USER, EMAIL_SMTP_PASS)."""
        import os
        import smtplib
        from email.mime.text import MIMEText as MimeText

        host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
        port = int(os.getenv("EMAIL_SMTP_PORT", "587"))
        user = os.getenv("EMAIL_SMTP_USER", self.from_address)
        password = os.getenv("EMAIL_SMTP_PASS", self.api_key)

        msg = MimeText(body_text, "plain")
        msg["Subject"] = subject
        msg["From"] = self.from_address
        msg["To"] = to_email

        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(self.from_address, [to_email], msg.as_string())

        logger.info(f"SMTP email sent to {to_email}")
        return {"success": True, "message": "Sent via SMTP", "id": ""}


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
email_client = EmailClient()
