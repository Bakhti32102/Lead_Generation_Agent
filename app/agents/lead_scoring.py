"""
Lead Scoring Agent.
Implements a 100-point scoring system to rank prospects.
Only leads above the configured threshold should be contacted.

Scoring weights (total = 100):
  relevant_category:      15
  location_match:         10  (structured fields or textual evidence)
  location_verification:   5  (textual evidence confirms city/country)
  recent_requirement:     20
  automation_opportunity: 15
  has_website:             5
  has_email:              10
  has_phone:              10
  has_demo:                5
  strong_evidence:         5
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.config.settings import settings
from app.sources.base import RawProspect

logger = logging.getLogger(__name__)


class LeadScoringAgent:
    """
    Scores prospects on a 0-100 scale based on multiple factors.
    Uses LocationVerifier for textual evidence location checking.
    """

    # Scoring weights — sum to 100 for standard leads.
    # Bounded sources (OSM, Maps) get +15 source_quality on top,
    # capped at 100 total.
    WEIGHTS: Dict[str, int] = {
        "relevant_category": 15,
        "location_match": 10,
        "location_verification": 5,
        "recent_requirement": 15,
        "automation_opportunity": 15,
        "has_website": 5,
        "has_email": 10,
        "has_phone": 10,
        "has_demo": 5,
        "strong_evidence": 5,
        "source_quality": 15,  # Bounded sources (OSM, Maps) bonus
    }

    def __init__(self, target_category: str = "", target_country: str = "", target_city: str = ""):
        self.target_category = target_category.lower()
        self.target_country = target_country.lower()
        self.target_city = target_city.lower()

    def verify_locations(self, prospects: List[RawProspect]) -> List[RawProspect]:
        """
        Run location verification on a batch of prospects BEFORE scoring.
        Populates prospect.metadata["location_verification"] with the result.
        Returns the same list (modified in place).
        """
        from app.agents.location_verifier import LocationVerifier
        verifier = LocationVerifier()

        for p in prospects:
            result = verifier.verify(p, self.target_city, self.target_country)
            p.metadata["location_verification"] = result

            if result.state == "mismatch":
                logger.info(
                    f"Location MISMATCH for '{p.business_name}': "
                    f"found {result.found_city}/{result.found_country}, "
                    f"target {result.target_city}/{result.target_country} "
                    f"({result.evidence_source})"
                )
            elif result.state in ("verified", "probably_verified"):
                logger.debug(
                    f"Location {result.state} for '{p.business_name}': "
                    f"{result.evidence_source} (confidence: {result.confidence:.2f})"
                )

        return prospects

    def score(self, prospect: RawProspect) -> int:
        """Calculate a 0-100 score for a prospect."""
        score = 0

        # 1. Relevant business category (+15)
        if self._category_match(prospect):
            score += self.WEIGHTS["relevant_category"]

        # 2. Location match (+10)
        # Use structured fields OR textual evidence
        if self._location_match(prospect):
            score += self.WEIGHTS["location_match"]

        # 3. Location verification bonus (+5)
        # Awarded when textual evidence confirms target city/country
        loc_verify = prospect.metadata.get("location_verification")
        if loc_verify and loc_verify.state in ("verified", "probably_verified"):
            if loc_verify.confidence >= 0.6:
                score += self.WEIGHTS["location_verification"]

        # 4. Recent requirement / business listing (+20)
        # Sources that provide ongoing business listings (OSM, Google Maps,
        # search results) don't have posting dates but the businesses are
        # actively listed — award baseline credit so they aren't unfairly
        # penalized compared to job-posting sources.
        BUSINESS_LISTING_SOURCES = ("openstreetmap", "google_maps", "google_search")
        if prospect.source in ("linkedin", "public_jobs"):
            freshness = getattr(prospect, "freshness", "") or prospect.metadata.get("freshness", "unknown")
            if freshness == "verified_recent":
                score += 25
            elif freshness == "probably_recent":
                score += 15
            elif freshness == "unknown":
                score += 5  # Partial credit
        elif prospect.source in BUSINESS_LISTING_SOURCES:
            # Business listings are inherently current — award baseline credit
            score += 10

        # 5. Automation opportunity (+15)
        problems = prospect.metadata.get("problems_list", [])
        if problems and len(problems) >= 2:
            score += 15
        elif problems:
            score += 8

        # 6. Business website available (+5)
        if prospect.website:
            score += self.WEIGHTS["has_website"]

        # 7. Business email available (+10)
        if prospect.email:
            score += self.WEIGHTS["has_email"]

        # 8. Business WhatsApp / Phone available (+10)
        has_whatsapp = prospect.metadata.get("has_whatsapp", False)
        if has_whatsapp or prospect.phone:
            score += self.WEIGHTS["has_phone"]

        # 9. Relevant demo available (+5)
        if prospect.metadata.get("demo_url"):
            score += self.WEIGHTS["has_demo"]

        # 10. Strong business evidence (+5)
        if self._has_strong_evidence(prospect):
            score += self.WEIGHTS["strong_evidence"]

        # 11. Source quality bonus (+15)
        # Bounded/geographically-constrained sources (OSM, Google Maps)
        # guarantee the business exists at the target location because
        # the search itself was limited to that area.
        BOUNDED_SOURCES = ("openstreetmap", "google_maps")
        if prospect.source in BOUNDED_SOURCES:
            score += self.WEIGHTS["source_quality"]

        # Cap at 100
        return min(score, 100)

    def score_batch(self, prospects: List[RawProspect]) -> List[RawProspect]:
        """Score a batch and sort by score descending.
        First runs location verification on all prospects."""
        # Step 0: Run location verification
        self.verify_locations(prospects)

        # Step 1: Reject mismatches immediately
        qualified = []
        rejected_count = 0
        for p in prospects:
            loc_verify = p.metadata.get("location_verification")
            if loc_verify and loc_verify.state == "mismatch":
                p.lead_score = 0
                p.is_qualified = False
                rejected_count += 1
                logger.info(
                    f"REJECTED (location mismatch): {p.business_name} — "
                    f"{loc_verify.evidence_source}"
                )
            else:
                qualified.append(p)

        # Step 2: Score the remaining
        for p in qualified:
            p.lead_score = self.score(p)
            p.is_qualified = p.lead_score >= settings.campaign.lead_score_threshold

        # Combine: mismatched at bottom, then sorted by score
        all_prospects = qualified + [p for p in prospects if p not in qualified]
        all_prospects.sort(key=lambda x: x.lead_score, reverse=True)

        total_qualified = sum(1 for p in all_prospects if p.is_qualified)
        logger.info(
            f"Scoring complete: {len(prospects)} scored, "
            f"{rejected_count} rejected (location mismatch), "
            f"{total_qualified} qualified (threshold: {settings.campaign.lead_score_threshold})"
        )
        return all_prospects

    def select_top_leads(
        self, prospects: List[RawProspect], max_count: int
    ) -> List[RawProspect]:
        """Select the top N qualified leads."""
        qualified = [p for p in prospects if p.is_qualified]
        selected = qualified[:max_count]
        logger.info(
            f"Selected {len(selected)} leads from {len(qualified)} qualified "
            f"(requested: {max_count})"
        )
        return selected

    def _category_match(self, p: RawProspect) -> bool:
        """Check if the prospect's category matches the target category."""
        if not self.target_category:
            return True
        cat = (p.business_category or "").lower()
        # Check for keyword overlap
        target_words = set(self.target_category.split())
        cat_words = set(cat.split())
        return bool(target_words & cat_words) or self.target_category in cat or cat in self.target_category

    def _location_match(self, p: RawProspect) -> bool:
        """
        Check if the prospect's location matches the target.
        Uses structured fields first, falls back to textual evidence
        from location_verification if structured fields are empty.
        """
        country = (p.country or "").lower().strip()
        city = (p.city or "").lower().strip()

        # Check structured fields
        structured_country = bool(country)
        structured_city = bool(city)

        if structured_country and structured_city:
            # Both structured — use standard matching
            country_match = self.target_country in country or country in self.target_country
            city_match = self.target_city in city or city in self.target_city
            return country_match and city_match

        if structured_country and not structured_city:
            # Country only
            country_match = self.target_country in country or country in self.target_country
            if not country_match:
                return False
            # City missing — check textual evidence
            loc_verify = p.metadata.get("location_verification")
            if loc_verify and loc_verify.state in ("verified", "probably_verified"):
                return True
            # No textual evidence for city — don't give location points
            return False

        if structured_city and not structured_country:
            # City only
            city_match = self.target_city in city or city in self.target_city
            if not city_match:
                return False
            # Country missing — check textual evidence
            loc_verify = p.metadata.get("location_verification")
            if loc_verify and loc_verify.state in ("verified", "probably_verified"):
                return True
            return False

        # Both empty — rely entirely on textual evidence
        loc_verify = p.metadata.get("location_verification")
        if loc_verify and loc_verify.state in ("verified", "probably_verified"):
            return True

        return False

    def _has_strong_evidence(self, p: RawProspect) -> bool:
        """Check if the business has strong evidence (multiple verified data points)."""
        evidence_count = sum([
            bool(p.website),
            bool(p.email),
            bool(p.phone),
            bool(p.address),
            bool(p.google_maps_url),
            p.source == "google_maps",  # Google Maps is a strong evidence source
        ])
        return evidence_count >= 3
