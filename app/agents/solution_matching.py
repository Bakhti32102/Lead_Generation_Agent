"""
Solution Matching Agent.
Selects the most relevant service(s) and demo(s) for each prospect.
Does NOT recommend all three services automatically.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from app.config.settings import PROJECT_ROOT
from app.sources.base import RawProspect

logger = logging.getLogger(__name__)


class AgentDemo:
    """Represents an existing AI agent demo."""

    def __init__(self, name: str, category: str, description: str, demo_url: str):
        self.name = name
        self.category = category
        self.description = description
        self.demo_url = demo_url

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "category": self.category,
            "description": self.description,
            "demo_url": self.demo_url,
        }


class SolutionMatchingAgent:
    """Matches the best service and demo to each prospect."""

    # Service recommendation rules based on business characteristics
    SERVICE_RULES = {
        # (has_website, has_booking, has_chatbot, category_type) → recommended services
        "no_website": {
            "services": ["Website", "AI Chatbot"],
            "primary": "Website",
        },
        "outdated_website": {
            "services": ["Website"],
            "primary": "Website",
        },
        "has_website_no_booking": {
            "services": ["AI Chatbot", "AI Agent"],
            "primary": "AI Chatbot",
        },
        "has_booking_no_chatbot": {
            "services": ["AI Chatbot"],
            "primary": "AI Chatbot",
        },
        "nothing": {
            "services": ["Website", "AI Agent", "AI Chatbot"],
            "primary": "AI Chatbot",
        },
        "default": {
            "services": ["AI Chatbot"],
            "primary": "AI Chatbot",
        },
    }

    def __init__(self):
        self.demos = self._load_demos()

    def _load_demos(self) -> List[AgentDemo]:
        """Load agent demos from agents.json."""
        agents_file = PROJECT_ROOT / "agents.json"
        if not agents_file.exists():
            logger.warning("agents.json not found. No demos available.")
            return []

        try:
            with open(agents_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [
                AgentDemo(
                    name=d["name"],
                    category=d["category"],
                    description=d.get("description", ""),
                    demo_url=d.get("demo_url", ""),
                )
                for d in data
            ]
        except Exception as e:
            logger.error(f"Failed to load agents.json: {e}")
            return []

    def match(self, prospect: RawProspect) -> RawProspect:
        """
        Determine the best service recommendation and matching demo
        for this prospect.
        """
        # Step 1: Determine which service(s) to recommend
        recommended = self._determine_service(prospect)

        # Step 2: Select the best matching demo
        demo = self._select_demo(prospect, recommended["primary"])

        # Step 3: Update prospect
        prospect.recommended_service = ", ".join(recommended["services"])
        if demo and demo.demo_url:
            prospect.metadata["demo_name"] = demo.name
            prospect.metadata["demo_url"] = demo.demo_url
            prospect.metadata["demo_description"] = demo.description
        else:
            prospect.metadata["demo_name"] = ""
            prospect.metadata["demo_url"] = ""
            prospect.metadata["demo_description"] = ""

        return prospect

    def _determine_service(self, prospect: RawProspect) -> dict:
        """Decide which services to recommend based on the business's current state."""
        analysis = prospect.metadata.get("website_analysis", {})
        if not isinstance(analysis, dict):
            analysis = {}

        has_website = bool(prospect.website)
        website_quality = analysis.get("website_quality", "unknown")
        has_booking = analysis.get("has_booking", False)
        has_chatbot = analysis.get("has_chatbot", False)

        if not has_website:
            return self.SERVICE_RULES["no_website"]
        elif website_quality in ("poor", "outdated"):
            return self.SERVICE_RULES["outdated_website"]
        elif has_website and not has_booking and not has_chatbot:
            return self.SERVICE_RULES["has_website_no_booking"]
        elif has_booking and not has_chatbot:
            return self.SERVICE_RULES["has_booking_no_chatbot"]
        else:
            return self.SERVICE_RULES["default"]

    def _select_demo(
        self, prospect: RawProspect, primary_service: str
    ) -> Optional[AgentDemo]:
        """Select the most relevant demo based on business type."""
        if not self.demos:
            return None

        category_lower = (prospect.business_category or "").lower()
        city_lower = (prospect.city or "").lower()

        # Category-based matching
        category_map = {
            "clinic": ["clinic", "medical", "health"],
            "dental": ["dental", "dentist"],
            "restaurant": ["restaurant", "cafe", "food"],
            "beauty": ["beauty", "salon", "parlor", "makeup", "spa"],
            "cosmetic": ["cosmetic", "skincare"],
            "lead generation": ["lead generation", "marketing"],
            "general": ["general", "support"],
        }

        # Find the matching category keyword
        matched_key = "general"
        for key, keywords in category_map.items():
            for kw in keywords:
                if kw in category_lower:
                    matched_key = key
                    break

        # Score each demo
        best_demo = None
        best_score = -1

        for demo in self.demos:
            score = 0
            demo_cat = demo.category.lower()

            # Category match
            if matched_key in demo_cat or demo_cat in matched_key:
                score += 10
            elif matched_key == "general":
                score += 3

            # If no demo URL, lower priority
            if not demo.demo_url:
                score -= 5

            if score > best_score:
                best_score = score
                best_demo = demo

        return best_demo
