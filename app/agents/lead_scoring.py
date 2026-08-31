"""
Lead Scoring Agent.
Implements a 100-point scoring system to rank prospects.
Only leads above the configured threshold should be contacted.
"""

from __future__ import annotations

import logging
from typing import List

from app.config.settings import settings
from app.sources.base import RawProspect

logger = logging.getLogger(__name__)


class LeadScoringAgent:
    """
    Scores prospects on a 0-100 scale based on multiple factors.
    """

    # Scoring weights
    WEIGHTS = {
        "relevant_category": 15,
        "location_match": 10,
        "recent_requirement": 25,
        "automation_opportunity": 15,
        "has_website": 5,
        "has_email": 10,
        "has_phone": 10,
        "relevant_demo": 5,
        "strong_evidence": 5,  # verified business evidence
    }

    def __init__(self, target_category: str = "", target_country: str = "", target_city: str = ""):
        self.target_category = target_category.lower()
        self.target_country = target_country.lower()
        self.target_city = target_city.lower()

    def score(self, prospect: RawProspect) -> int:
        """Calculate a 0-100 score for a prospect."""
        score = 0

        # 1. Relevant business category (+15)
        if self._category_match(prospect):
            score += self.WEIGHTS["relevant_category"]

        # 2. Target city/country match (+10)
        if self._location_match(prospect):
            score += self.WEIGHTS["location_match"]

        # 3. Recent requirement (+25)
        if prospect.source in ("linkedin", "public_jobs"):
            freshness = getattr(prospect, 'freshness', '') or prospect.metadata.get('freshness', 'unknown')
            if freshness == "verified_recent":
                score += 25
            elif freshness == "probably_recent":
                score += 15
            elif freshness == "unknown":
                score += 5  # Partial credit

        # 4. Clear automation opportunity (+20)
        problems = prospect.metadata.get("problems_list", [])
        if problems and len(problems) >= 2:
            score += 20
        elif problems:
            score += 10

        # 5. Business website available (+5)
        if prospect.website:
            score += 5

        # 6. Business email available (+10)
        if prospect.email:
            score += 10

        # 7. Business WhatsApp / Phone available (+10)
        has_whatsapp = prospect.metadata.get("has_whatsapp", False)
        if has_whatsapp or prospect.phone:
            score += 10

        # 8. Relevant demo available (+5)
        if prospect.metadata.get("demo_url"):
            score += 5

        # 9. Strong business evidence (+10)
        if self._has_strong_evidence(prospect):
            score += 10

        # Cap at 100
        return min(score, 100)

    def score_batch(self, prospects: List[RawProspect]) -> List[RawProspect]:
        """Score a batch and sort by score descending."""
        for p in prospects:
            p.lead_score = self.score(p)
            p.is_qualified = p.lead_score >= settings.campaign.lead_score_threshold

        # Sort by score descending
        prospects.sort(key=lambda x: x.lead_score, reverse=True)

        qualified = sum(1 for p in prospects if p.is_qualified)
        logger.info(
            f"Scoring complete: {len(prospects)} scored, "
            f"{qualified} qualified (threshold: {settings.campaign.lead_score_threshold})"
        )
        return prospects

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
        """Check if the prospect's location matches the target."""
        country = (p.country or "").lower()
        city = (p.city or "").lower()

        country_match = not self.target_country or self.target_country in country or country in self.target_country
        city_match = not self.target_city or self.target_city in city or city in self.target_city

        return country_match and city_match

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
