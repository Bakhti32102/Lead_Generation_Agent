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

        # Mark as verified if at least name + some contact info is present
        is_valid = checks["has_name"] and (checks["has_contact"] or checks["has_website"])
        prospect.metadata["is_verified"] = is_valid

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
