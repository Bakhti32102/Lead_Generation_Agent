"""
Business Research Agent.
Visits and analyzes business websites to understand the business,
identify automation opportunities, and gather intelligence.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.config.settings import settings
from app.integrations.llm import LLMClient, get_llm
from app.sources.base import RawProspect

logger = logging.getLogger(__name__)


class BusinessResearchAgent:
    """Researches a business's website and online presence to build intelligence."""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or get_llm()

    def research(self, prospect: RawProspect) -> RawProspect:
        """
        Research a business prospect. Analyzes their website if available.
        Updates the prospect with research findings in metadata.
        """
        website = prospect.website.strip()

        if website:
            webpage_text = self._fetch_website_text(website)
            if webpage_text:
                analysis = self._analyze_with_llm(prospect, webpage_text)
                prospect.metadata["website_analysis"] = analysis
                prospect.business_research = analysis.get("summary", "")
                prospect.metadata["has_booking"] = analysis.get("has_booking", False)
                prospect.metadata["has_chatbot"] = analysis.get("has_chatbot", False)
                prospect.metadata["has_whatsapp"] = analysis.get("has_whatsapp", False)
                prospect.metadata["has_contact_form"] = analysis.get("has_contact_form", False)
                prospect.metadata["website_quality"] = analysis.get("quality", "unknown")
            else:
                prospect.metadata["website_analysis"] = {"error": "Could not fetch website"}
                prospect.business_research = "Website unavailable or could not be fetched."
        else:
            prospect.business_research = "No website available."
            prospect.metadata["website_analysis"] = {"error": "No website"}

        return prospect

    def _fetch_website_text(self, url: str) -> str:
        """Fetch the readable text content from a website."""
        try:
            import requests

            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; BusinessResearch/1.0)"
            }
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
            if resp.status_code != 200:
                logger.warning(f"Website fetch failed ({resp.status_code}): {url}")
                return ""

            html = resp.text
            # Simple HTML-to-text extraction
            text = self._html_to_text(html)
            return text[:5000]  # Limit to manageable size for LLM

        except Exception as e:
            logger.error(f"Website fetch error for {url}: {e}")
            return ""

    def _html_to_text(self, html: str) -> str:
        """Basic HTML to text conversion."""
        # Remove script and style tags
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML comments
        html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
        # Remove tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Clean whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Decode HTML entities
        import html as html_mod
        text = html_mod.unescape(text)
        return text

    def _analyze_with_llm(self, prospect: RawProspect, webpage_text: str) -> dict:
        """Use LLM to analyze the business website content."""
        if not self.llm.is_configured:
            return self._basic_analysis(webpage_text)

        system_prompt = """You are a business analyst. Analyze the website content of a business
and return a JSON object with these fields:
- summary: 2-3 sentence summary of what the business does
- services: list of main services/products offered
- has_booking: boolean — do they have online booking/appointment?
- has_chatbot: boolean — do they have a chatbot?
- has_whatsapp: boolean — do they use WhatsApp?
- has_contact_form: boolean — do they have a contact form?
- has_online_ordering: boolean — do they offer online ordering?
- website_quality: "good" / "average" / "poor" / "outdated"
- target_customers: who their customers are
- repetitive_questions: list of common customer questions they likely face
- automation_opportunities: list of workflows that could be automated

Return ONLY valid JSON. No markdown. No explanation."""

        user_prompt = f"""Business: {prospect.business_name}
Category: {prospect.business_category or 'Unknown'}
Location: {prospect.city}, {prospect.country}

Website content:
{webpage_text[:4000]}"""

        try:
            result = self.llm.generate_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                max_tokens=1500,
            )
            return result if isinstance(result, dict) else {"summary": str(result)}
        except Exception as e:
            logger.error(f"LLM analysis failed: {e}")
            return self._basic_analysis(webpage_text)

    def _basic_analysis(self, text: str) -> dict:
        """Basic keyword-based analysis when LLM is unavailable."""
        text_lower = text.lower()

        return {
            "summary": text[:200],
            "has_booking": any(w in text_lower for w in ["book", "appointment", "schedule", "booking"]),
            "has_chatbot": any(w in text_lower for w in ["chat", "chatbot", "ai assistant"]),
            "has_whatsapp": "whatsapp" in text_lower,
            "has_contact_form": any(w in text_lower for w in ["contact form", "send message", "inquiry"]),
            "has_online_ordering": any(w in text_lower for w in ["order", "cart", "buy now"]),
            "website_quality": "unknown",
            "target_customers": "",
            "repetitive_questions": [],
            "automation_opportunities": [],
        }
