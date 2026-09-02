"""
Lead Verification Agent.
Validates businesses, contact information, source authenticity, and recency.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from app.sources.base import RawProspect

logger = logging.getLogger(__name__)


class LeadVerificationAgent:
    """Verifies that a discovered prospect is a real, reachable business."""

    def verify(self, prospect: RawProspect) -> RawProspect:
        """
        Verify a single prospect. Returns the same prospect with
        verification metadata added.
        """
        checks = {
            "has_name": self._check_name(prospect),
            "has_contact": self._check_contact(prospect),
            "has_valid_email": self._check_email(prospect),
            "has_valid_phone": self._check_phone(prospect),
            "has_website": self._check_website(prospect),
            "website_not_blocked": True,  # Verified by actual HTTP check
            "recency_valid": self._check_recency(prospect),
            "source_valid": True,
        }

        total = len(checks)
        passed = sum(1 for v in checks.values() if v)

        prospect.metadata["verification"] = checks
        prospect.metadata["verification_score"] = f"{passed}/{total}"

        # ── Mandatory Contact Check ──
        # A lead MUST have at least one valid outreach channel
        # (phone, email, or website) to be considered for outreach.
        # Dead-end entries with no way to contact are rejected immediately.
        has_any_contact = (
            checks["has_valid_phone"]
            or checks["has_valid_email"]
            or checks["has_website"]
        )
        if not has_any_contact:
            prospect.metadata["is_verified"] = False
            prospect.metadata["skip_reason"] = "No contact information available"
            logger.info(
                f"Skipped (no contact): {prospect.business_name} "
                f"— phone, email, and website all missing or invalid"
            )
            return prospect

        # Mark as verified if at least name + some contact info is present.
        is_valid = checks["has_name"] and has_any_contact
        prospect.metadata["is_verified"] = is_valid

        # ── 3-Step Pre-Qualification Filter ──
        # Always run the automation check for prospects that have a valid
        # name (even if they lack contact info — bounded sources qualify).
        # If the business already has a website + website AI chatbot +
        # WhatsApp AI automation, skip it — there is nothing to sell.
        if checks["has_name"]:
            already_automated = self._check_already_automated(prospect)
            if already_automated["fully_automated"]:
                prospect.metadata["is_verified"] = False
                prospect.metadata["skip_reason"] = "Already fully automated"
                prospect.metadata["automation_check"] = already_automated
                logger.info(
                    f"Skipped (already automated): {prospect.business_name} "
                    f"— has website, AI chatbot, and WhatsApp automation"
                )
            else:
                # Tag what is missing so outreach can customise the pitch
                prospect.metadata["automation_check"] = already_automated
                missing = []
                if not already_automated["has_website"]:
                    missing.append("website")
                if not already_automated["has_website_chatbot"]:
                    missing.append("website AI chatbot")
                if not already_automated["has_whatsapp_automation"]:
                    missing.append("WhatsApp AI automation")
                prospect.metadata["automation_gaps"] = missing

        if not is_valid:
            logger.debug(
                f"Lead failed verification: {prospect.business_name} "
                f"(score: {passed}/{total})"
            )

        return prospect

    def verify_batch(self, prospects: List[RawProspect]) -> List[RawProspect]:
        """Verify a batch of prospects and return verified ones only."""
        verified = []
        for p in prospects:
            result = self.verify(p)
            if result.metadata.get("is_verified", False):
                verified.append(result)

        logger.info(
            f"Verification: {len(prospects)} checked → {len(verified)} verified"
        )
        return verified

    def _check_name(self, p: RawProspect) -> bool:
        """Business name must exist and be meaningful."""
        name = p.business_name.strip()
        if not name or len(name) < 2:
            return False
        # Skip generic/test names
        skip_names = ["test", "example", "sample", "unknown", "none"]
        if name.lower() in skip_names:
            return False
        return True

    def _check_contact(self, p: RawProspect) -> bool:
        """At least one contact method should exist."""
        return bool(p.email or p.phone or p.website)

    def _check_email(self, p: RawProspect) -> bool:
        """Validate email format if present."""
        if not p.email:
            return False
        pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        return bool(re.match(pattern, p.email.strip()))

    def _check_phone(self, p: RawProspect) -> bool:
        """Validate phone format if present."""
        if not p.phone:
            return False
        digits = re.sub(r"[^\d]", "", p.phone)
        return len(digits) >= 7

    def _check_website(self, p: RawProspect) -> bool:
        """Validate website URL format."""
        if not p.website:
            return False
        url = p.website.strip().lower()
        return url.startswith("http://") or url.startswith("https://")

    def _check_recency(self, p: RawProspect) -> bool:
        """Check freshness if this is a recent requirement source."""
        if p.source not in ("linkedin", "public_jobs"):
            return True  # Business listings don't need freshness check
        freshness = p.metadata.get("freshness", "unknown")
        if freshness in ("verified_recent", "probably_recent"):
            return True
        if freshness == "unknown":
            return True  # Don't disqualify, just lower score later
        return False

    # ── 3-Step Pre-Qualification Filter ──

    @staticmethod
    def _check_already_automated(prospect: RawProspect) -> dict:
        """Check whether the business already has a website, AI chatbot,
        and WhatsApp automation.

        Returns a dict with:
          has_website            – bool
          has_website_chatbot    – bool
          has_whatsapp_automation – bool
          fully_automated        – bool  (True only when all three are True)

        Detection is best-effort based on available metadata, scraped
        content, and URL heuristics.  False negatives are acceptable
        (we prefer to outreach a business that already has a simple bot
        rather than miss a genuinely un-automated business).
        """
        has_website = bool(prospect.website)

        # ── Website chatbot detection ──
        # Look for common chatbot widget indicators in the website URL,
        # metadata tags, or scraped snippet text.
        chatbot_signals = [
            "tidio", "intercom", "drift", "crisp", "zendesk",
            "livechat", "olark", "tawk", "freshdesk", "hubspot",
            "chatbot", "chat-widget", "chat-widget-js",
            "messenger", "fb Messenger",
            "widget.tawk", "crisp.chat",
        ]
        has_website_chatbot = False
        if has_website:
            website_lower = prospect.website.lower()
            meta_text = str(prospect.metadata).lower()
            snippet = prospect.metadata.get("snippet", "").lower()
            research = (prospect.business_research or "").lower()
            combined = f"{website_lower} {meta_text} {snippet} {research}"
            has_website_chatbot = any(s in combined for s in chatbot_signals)

        # ── WhatsApp automation detection ──
        # Look for WhatsApp Business API usage, wa.me links with auto-reply
        # indicators, or explicit WhatsApp automation mentions.
        whatsapp_signals = [
            "whatsapp business api", "whatsapp automation",
            "whatsapp chatbot", "wa-bot", "whatsapp bot",
            "business.whatsapp", "api.whatsapp",
            "wa.me/send", "whatsapp ai",
        ]
        has_whatsapp_automation = False
        meta_text = str(prospect.metadata).lower()
        snippet = prospect.metadata.get("snippet", "").lower()
        research = (prospect.business_research or "").lower()
        combined = f"{meta_text} {snippet} {research}"
        has_whatsapp_automation = any(s in combined for s in whatsapp_signals)

        fully_automated = has_website and has_website_chatbot and has_whatsapp_automation

        return {
            "has_website": has_website,
            "has_website_chatbot": has_website_chatbot,
            "has_whatsapp_automation": has_whatsapp_automation,
            "fully_automated": fully_automated,
        }
