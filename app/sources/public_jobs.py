"""
Public job/project boards source.
Searches legitimate public sources where businesses post AI/automation requirements.
Examples: Indeed, Glassdoor, public freelance platforms, government job boards.
"""

from __future__ import annotations

import logging
from typing import List

from app.config.settings import settings
from app.sources.base import LeadSource, RawProspect

logger = logging.getLogger(__name__)


class PublicJobSource(LeadSource):
    """Search public job boards and project listings for AI/automation requirements."""

    @property
    def name(self) -> str:
        return "public_jobs"

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
        """Search public job/project boards for relevant requirements."""
        if not self.is_configured:
            logger.warning("Search API not configured for public jobs source.")
            return []

        prospects: List[RawProspect] = []
        seen_urls: set = set()

        # Build queries targeting job/project boards
        job_queries = [
            f"AI chatbot developer needed {city} {country}",
            f"AI automation project {city} {country}",
            f"need AI agent developer {city} {country}",
            f"restaurant website development {city} {country}",
            f"dental clinic website {city} {country}",
            f"beauty salon automation {city} {country}",
            f"WhatsApp automation business {city} {country}",
        ]

        for query in job_queries[:4]:  # Limit queries to avoid excessive API calls
            results = self._search(query, max_results=max_results // len(job_queries))
            for p in results:
                url = p.source_url
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    prospects.append(p)

        logger.info(f"Public Jobs: found {len(prospects)} requirements")
        return prospects[:max_results]

    def _search(self, query: str, max_results: int = 5) -> List[RawProspect]:
        """Execute search via the configured search provider."""
        provider = settings.search.provider.lower()

        try:
            if provider == "tavily":
                return self._search_tavily(query, max_results)
            elif provider == "serpapi":
                return self._search_serpapi(query, max_results)
            elif provider == "bing":
                return self._search_bing(query, max_results)
            else:
                return self._search_tavily(query, max_results)
        except Exception as e:
            logger.error(f"Public jobs search failed: {e}")
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

                # Filter: only include results from job/project platforms
                if not self._is_job_platform(url):
                    continue

                freshness = self._assess_freshness(content)

                prospects.append(
                    RawProspect(
                        business_name=self._extract_entity(title),
                        source_url=url,
                        requirement_text=content[:300],
                        source="public_jobs",
                        freshness=freshness,
                        metadata={"title": title, "snippet": content},
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"Tavily public jobs search failed: {e}")
            return []

    def _search_serpapi(self, query: str, max_results: int) -> List[RawProspect]:
        try:
            import requests

            params = {
                "q": query,
                "api_key": settings.search.api_key,
                "num": max_results,
                "engine": "google",
                "tbs": "qdr:d",
            }
            resp = requests.get("https://serpapi.com/search", params=params, timeout=30)
            data = resp.json()

            prospects = []
            for result in data.get("organic_results", []):
                url = result.get("link", "")
                if not self._is_job_platform(url):
                    continue

                prospects.append(
                    RawProspect(
                        business_name=self._extract_entity(result.get("title", "")),
                        source_url=url,
                        requirement_text=result.get("snippet", "")[:300],
                        source="public_jobs",
                        freshness="probably_recent",
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"SerpAPI public jobs search failed: {e}")
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
                if not self._is_job_platform(url):
                    continue

                prospects.append(
                    RawProspect(
                        business_name=self._extract_entity(item.get("name", "")),
                        source_url=url,
                        requirement_text=item.get("snippet", "")[:300],
                        source="public_jobs",
                        freshness="probably_recent",
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"Bing public jobs search failed: {e}")
            return []

    @staticmethod
    def _is_job_platform(url: str) -> bool:
        """Check if URL belongs to a known job/project platform."""
        platforms = [
            "indeed.com", "glassdoor.com", "monster.com", "careerbuilder.com",
            "freelancer.com", "upwork.com", "fiverr.com", "peopleperhour.com",
            "guru.com", "toptal.com", "simplyhired.com", "ziprecruiter.com",
            "jooble.org", "naukri.com", "bayt.com", "gulf.com", "dubizzle.com",
        ]
        url_lower = url.lower()
        return any(platform in url_lower for platform in platforms)

    @staticmethod
    def _extract_entity(title: str) -> str:
        """Extract the posting entity from a job title."""
        for sep in [" - ", " | ", " at ", " @ ", " · "]:
            if sep in title:
                parts = title.split(sep)
                return parts[-1].strip()
        return title.strip()

    @staticmethod
    def _assess_freshness(text: str) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ["just posted", "just now", "today", "new"]):
            return "verified_recent"
        return "unknown"
