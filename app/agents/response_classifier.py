"""
Response Classifier Agent.
Classifies prospect replies into actionable categories.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.integrations.llm import LLMClient, get_llm

logger = logging.getLogger(__name__)

RESPONSE_CATEGORIES = {
    "interested": "Prospect shows interest in the service",
    "wants_demo": "Prospect wants to see a demo",
    "wants_pricing": "Prospect asks about pricing",
    "wants_proposal": "Prospect wants a formal proposal",
    "wants_meeting": "Prospect wants to schedule a meeting",
    "needs_more_info": "Prospect needs more information before deciding",
    "not_interested": "Prospect is not interested",
    "already_has_solution": "Prospect already has a similar solution",
    "technical_question": "Prospect has a technical question",
    "human_required": "Requires human intervention",
}


class ResponseClassifierAgent:
    """Classifies incoming prospect replies."""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or get_llm()

    def classify(self, reply_text: str) -> str:
        """
        Classify a prospect's reply into a category.
        Returns one of the RESPONSE_CATEGORIES keys.
        """
        if not reply_text:
            return "needs_more_info"

        if self.llm.is_configured:
            return self._classify_with_llm(reply_text)
        else:
            return self._classify_keywords(reply_text)

    def _classify_with_llm(self, text: str) -> str:
        """Use LLM for classification."""
        categories = "\n".join(f"- {k}: {v}" for k, v in RESPONSE_CATEGORIES.items())

        system_prompt = f"""Classify this business reply into exactly one category.

Categories:
{categories}

Rules:
- Return ONLY the category key (e.g., "interested", "wants_pricing")
- No explanation, no extra text
- If unclear, choose the closest match"""

        try:
            result = self.llm.generate(
                system_prompt=system_prompt,
                user_prompt=f"Reply: {text[:500]}",
                temperature=0.1,
                max_tokens=50,
            )
            result = result.strip().lower()
            if result in RESPONSE_CATEGORIES:
                return result
            # Try partial match
            for key in RESPONSE_CATEGORIES:
                if key in result:
                    return key
            return "needs_more_info"
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return self._classify_keywords(text)

    def _classify_keywords(self, text: str) -> str:
        """Simple keyword-based classification."""
        text_lower = text.lower()

        # ── Negative indicators FIRST (must come before positive) ──
        if any(w in text_lower for w in ["not interested", "no thank", "no thanks", "stop contacting", "remove me"]):
            return "not_interested"
        if any(w in text_lower for w in ["already have", "already using", "existing solution"]):
            return "already_has_solution"

        # ── Specific positive indicators ──
        if any(w in text_lower for w in ["demo", "show me", "can you show", "see how it works", "example"]):
            return "wants_demo"
        if any(w in text_lower for w in ["price", "pricing", "cost", "how much", "quote"]):
            return "wants_pricing"
        if any(w in text_lower for w in ["proposal", "detailed plan", "breakdown"]):
            return "wants_proposal"
        if any(w in text_lower for w in ["meeting", "call", "schedule", "talk", "discuss"]):
            return "wants_meeting"

        # ── Technical ──
        if any(w in text_lower for w in ["api", "integration", "technology", "how does it work", "what model", "llm", "gpt", "openai", "anthropic", "rag", "embeddings"]):
            return "technical_question"

        # ── General positive (broadest match, last) ──
        if any(w in text_lower for w in ["yes", "interested", "interesting", "tell me more", "sounds good", "i want to know more", "want to learn"]):
            return "interested"

        # ── Information request ──
        if any(w in text_lower for w in ["more info", "details", "information", "learn more"]):
            return "needs_more_info"

        return "needs_more_info"
