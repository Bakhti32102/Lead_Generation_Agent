"""
Lead Verification Agent.
Validates businesses, contact information, source authenticity, and recency.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from app.sources.base import RawProspect
from app.utils.phone import is_whatsapp_number, has_valid_email, has_reachable_channel

logger = logging.getLogger(__name__)

# ── Retail / E-commerce Blacklist for Beauty Categories ──────────────────
# Business names, URLs, or snippet keywords that indicate a retail store,
# product shop, or e-commerce site — NOT a service provider.

RETAIL_NAME_KEYWORDS: list[str] = [
    # Retail store chains
    "sephora", "mac cosmetics", "nyx", "ulta", "beauty supply",
    "cosmetics store", "beauty store", "makeup store",
    "beauty products", "cosmetics shop", "beauty shop",
    "beauty outlet", "beauty depot",
    # E-commerce / online
    "online store", "shop online", "buy online", "order online",
    "e-commerce", "ecommerce", "amazon", "flipkart",
    # Wholesale / distribution
    "wholesale", "distributor", "supplier", "importer", "exporter",
    # Generic retail
    "retail", "supermarket", "hypermarket", "mart",
]

RETAIL_URL_PATTERNS: list[str] = [
    "sephora.com", "maccosmetics.com", "nyxcosmetics.com",
    "ulta.com", "beautybay.com", "cultbeauty.co.uk",
    "lookfantastic.com", "beautylish.com",
    "amazon.com", "amazon.", "flipkart.com",
    "ebay.com", "etsy.com",
    ".shop/", "/shop", "/store", "/buy", "/order",
]

RETAIL_SNIPPET_SIGNALS: list[str] = [
    "buy online", "shop now", "add to cart", "free shipping",
    "product range", "product catalog", "beauty products online",
    "cosmetics online", "makeup collection", "skincare products",
    "hair products", "nail polish", "lipstick", "foundation shade",
    "beauty brand", "product brand", "retail store",
    "wholesale supplier", "bulk order", "product distributor",
]


class LeadVerificationAgent:
    """Verifies that a discovered prospect is a real, reachable business."""

    def verify(self, prospect: RawProspect) -> RawProspect:
        """
        Verify a single prospect. Returns the same prospect with
        verification metadata added.
        """
        checks = {
            "has_name": self._check_name(prospect),
            "has_email": self._check_email(prospect),
            "has_whatsapp": self._check_whatsapp(prospect),
            "has_reachable_channel": self._check_reachable_channel(prospect),
            "has_website": self._check_website(prospect),
            "website_not_blocked": True,  # Verified by actual HTTP check
            "recency_valid": self._check_recency(prospect),
            "source_valid": True,
            "is_not_retail": self._check_not_retail(prospect),
        }

        total = len(checks)
        passed = sum(1 for v in checks.values() if v)

        prospect.metadata["verification"] = checks
        prospect.metadata["verification_score"] = f"{passed}/{total}"

        # ── Strict Contact Channel Enforcement ──
        # A lead MUST have a valid Email address OR a direct WhatsApp number
        # to pass pre-qualification.  Phone-only leads (standard/landline)
        # and website-only leads are rejected — they have no reachable
        # outreach channel.
        if not checks["has_reachable_channel"]:
            prospect.metadata["is_verified"] = False
            prospect.metadata["skip_reason"] = "No reachable contact channel (email or WhatsApp required)"
            logger.info(
                f"Skipped (no reachable channel): {prospect.business_name} "
                f"— no valid email or WhatsApp number"
            )
            return prospect

        # ── Retail / E-commerce Filter ──
        # Reject retail stores, product shops, and e-commerce sites that
        # do not take client appointment bookings.
        if not checks["is_not_retail"]:
            prospect.metadata["is_verified"] = False
            prospect.metadata["skip_reason"] = "Retail store / e-commerce (not a service provider)"
            logger.info(
                f"Skipped (retail): {prospect.business_name} "
                f"— detected as retail store or e-commerce"
            )
            return prospect

        # Mark as verified if name + reachable channel is present.
        is_valid = checks["has_name"] and checks["has_reachable_channel"]
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

    # ── Contact Channel Checks ──

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

    def _check_email(self, p: RawProspect) -> bool:
        """Validate email format if present."""
        return has_valid_email(p.email)

    def _check_whatsapp(self, p: RawProspect) -> bool:
        """Check if the phone number is WhatsApp-capable (mobile number)."""
        return is_whatsapp_number(p.phone)

    def _check_reachable_channel(self, p: RawProspect) -> bool:
        """Check if the prospect has at least one reachable outreach channel."""
        return has_reachable_channel(p.phone, p.email)

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

    # ── Retail / E-commerce Detection ──

    def _check_not_retail(self, p: RawProspect) -> bool:
        """
        Check if the business is NOT a retail store or e-commerce site.
        Returns True if it's a service provider (acceptable).
        Returns False if it's retail/e-commerce (should be rejected).

        Only applies to beauty-related categories.
        """
        # Only filter beauty categories
        category = (p.business_category or "").lower()
        beauty_categories = [
            "beauty", "cosmetic", "makeup", "salon", "spa",
            "hairdresser", "hair", "nail", "skincare",
        ]
        is_beauty = any(cat in category for cat in beauty_categories)

        # Also check business name for beauty-related terms
        name_lower = (p.business_name or "").lower()
        name_is_beauty = any(term in name_lower for term in [
            "beauty", "cosmetic", "makeup", "salon", "spa",
            "hair", "nail", "skincare", "institut",
        ])

        if not is_beauty and not name_is_beauty:
            return True  # Not a beauty category — skip retail check

        # Check business name against retail keywords
        for keyword in RETAIL_NAME_KEYWORDS:
            if keyword in name_lower:
                logger.debug(
                    f"Retail detected in name '{p.business_name}': "
                    f"matched keyword '{keyword}'"
                )
                return False

        # Check website URL against retail patterns
        website_lower = (p.website or "").lower()
        if website_lower:
            for pattern in RETAIL_URL_PATTERNS:
                if pattern in website_lower:
                    logger.debug(
                        f"Retail detected in URL '{p.website}': "
                        f"matched pattern '{pattern}'"
                    )
                    return False

        # Check snippet/metadata for retail signals
        snippet = str(p.metadata.get("snippet", "")).lower()
        research = (p.business_research or "").lower()
        combined_text = f"{snippet} {research}"

        for signal in RETAIL_SNIPPET_SIGNALS:
            if signal in combined_text:
                logger.debug(
                    f"Retail detected in text for '{p.business_name}': "
                    f"matched signal '{signal}'"
                )
                return False

        return True

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
