"""
LinkedIn source.
Searches for recent AI/automation requirements using legitimate public/indexed results.
Does NOT bypass login, CAPTCHA, anti-bot, or platform restrictions.
"""

from __future__ import annotations

import logging
import re
from typing import List

from app.config.settings import settings
from app.sources.base import LeadSource, RawProspect

logger = logging.getLogger(__name__)

# AI/automation-related search terms
REQUIREMENT_KEYWORDS = [
    "need AI agent",
    "looking for AI developer",
    "need AI automation",
    "need chatbot",
    "need AI chatbot",
    "need WhatsApp automation",
    "need appointment automation",
    "need customer support automation",
    "need AI receptionist",
    "need lead generation automation",
    "need AI integration",
    "need business automation",
    "need website development",
    "looking for chatbot developer",
    "hiring AI developer",
    "need custom AI solution",
]


class LinkedInSource(LeadSource):
    """
    Search for recent AI/automation requirements on LinkedIn.
    Uses search-engine-indexed public results rather than scraping LinkedIn directly.
    """

    @property
    def name(self) -> str:
        return "linkedin"

    @property
    def is_configured(self) -> bool:
        return settings.search.is_configured

    def search(
        self,
        country: str,
        city: str,
        category: str,
        max_results: int = 10,
        **kwargs,
    ) -> List[RawProspect]:
        """Search LinkedIn for recent AI/automation requirements."""
        if not self.is_configured:
            logger.warning("Search API not configured for LinkedIn source.")
            return []

        prospects: List[RawProspect] = []
        seen_urls: set = set()

        # Build LinkedIn-specific queries using location + requirement keywords
        location_terms = [city, country]
        location_str = f"{' '.join(location_terms)}"

        # Select the most relevant keywords (limit to avoid too many API calls)
        selected_keywords = REQUIREMENT_KEYWORDS[:5]

        for keyword in selected_keywords:
            query = f"site:linkedin.com {keyword} {location_str}"
            results = self._search_with_provider(query, max_results=max_results // len(selected_keywords))

            for p in results:
                url = p.source_url
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    p.source = "linkedin"
                    p.business_category = category
                    p.country = country
                    p.city = city
                    prospects.append(p)

        logger.info(f"LinkedIn: found {len(prospects)} requirements for {location_str}")
        return prospects[:max_results]

    def _search_with_provider(self, query: str, max_results: int = 5) -> List[RawProspect]:
        """Execute search via configured provider."""
        provider = settings.search.provider.lower()

        try:
            if provider == "tavily":
                return self._search_tavily(query, max_results)
            elif provider == "serpapi":
                return self._search_serpapi(query, max_results)
            elif provider == "bing":
                return self._search_bing(query, max_results)
            else:
                # Fallback: try tavily
                return self._search_tavily(query, max_results)
        except Exception as e:
            logger.error(f"LinkedIn search failed: {e}")
            return []

    def _search_tavily(self, query: str, max_results: int) -> List[RawProspect]:
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=settings.search.api_key)
            response = client.search(query=query, max_results=max_results)

            prospects = []
            for result in response.get("results", []):
                title = result.get("title", "")
                url = result.get("url", "")
                content = result.get("content", "")

                if "linkedin.com" not in url:
                    continue

                freshness = self._assess_freshness(content)

                prospects.append(
                    RawProspect(
                        business_name=self._extract_company_from_title(title),
                        source_url=url,
                        posted_date=self._extract_date_hint(content),
                        requirement_text=content[:300],
                        freshness=freshness,
                        metadata={
                            "title": title,
                            "snippet": content,
                        },
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"Tavily LinkedIn search failed: {e}")
            return []

    def _search_serpapi(self, query: str, max_results: int) -> List[RawProspect]:
        try:
            import requests

            params = {
                "q": query,
                "api_key": settings.search.api_key,
                "num": max_results,
                "engine": "google",
                "tbs": "qdr:d",  # last day
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
            data = resp.json()

            prospects = []
            for result in data.get("organic_results", []):
                url = result.get("link", "")
                if "linkedin.com" not in url:
                    continue

                prospects.append(
                    RawProspect(
                        business_name=self._extract_company_from_title(result.get("title", "")),
                        source_url=url,
                        requirement_text=result.get("snippet", "")[:300],
                        freshness="probably_recent",
                        metadata={"title": result.get("title", "")},
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"SerpAPI LinkedIn search failed: {e}")
            return []

    def _search_bing(self, query: str, max_results: int) -> List[RawProspect]:
        try:
            import requests

            headers = {"Ocp-Apim-Subscription-Key": settings.search.api_key}
            params = {"q": query, "count": max_results, "freshness": "Day"}
            resp = requests.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers=headers,
                params=params,
                timeout=30,
            )
            data = resp.json()

            prospects = []
            for item in data.get("webPages", {}).get("value", []):
                url = item.get("url", "")
                if "linkedin.com" not in url:
                    continue

                prospects.append(
                    RawProspect(
                        business_name=self._extract_company_from_title(item.get("name", "")),
                        source_url=url,
                        requirement_text=item.get("snippet", "")[:300],
                        freshness="probably_recent",
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"Bing LinkedIn search failed: {e}")
            return []

    @staticmethod
    def _extract_company_from_title(title: str) -> str:
        """Extract company name from LinkedIn post/job title."""
        # Common pattern: "Job Title - Company | LinkedIn"
        for sep in [" - ", " | ", " at ", " @ "]:
            if sep in title:
                parts = title.split(sep)
                # Take the part most likely to be company name
                for part in reversed(parts):
                    part = part.strip()
                    if part.lower() not in ("linkedin", "linkedin.com"):
                        return part
        return title.strip()

    @staticmethod
    def _assess_freshness(text: str) -> str:
        """Assess how recent a post likely is based on text content."""
        text_lower = text.lower()
        recent_indicators = [
            "just posted", "just now", "minutes ago", "hours ago",
            "today", "yesterday", "new", "urgent", "immediately",
        ]
        for indicator in recent_indicators:
            if indicator in text_lower:
                return "verified_recent"
        return "unknown"

    @staticmethod
    def _extract_date_hint(text: str) -> str:
        """Try to extract a date hint from the text."""
        # Look for common date patterns
        patterns = [
            r"\d{1,2}\s+(?:hours?|minutes?|days?)\s+ago",
            r"(?:just|recently)\s+(?:posted|published)",
        ]
        for pat in patterns:
            match = re.search(pat, text.lower())
            if match:
                return match.group(0)
        return ""
