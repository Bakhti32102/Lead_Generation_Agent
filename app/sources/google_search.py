"""
Google Search / generic search API source.
Supports Tavily, SerpAPI, Google Custom Search, and Bing Search.
Provider is selected via SEARCH_PROVIDER env var.
"""

from __future__ import annotations

import logging
import re
from typing import List
from urllib.parse import urlparse

from app.config.settings import settings
from app.sources.base import LeadSource, RawProspect

logger = logging.getLogger(__name__)


class GoogleSearchSource(LeadSource):
    """Search via configured search API for businesses and requirements."""

    @property
    def name(self) -> str:
        return "google_search"

    @property
    def is_configured(self) -> bool:
        return settings.search.is_configured

    # Countries where we use richer contact-focused queries
    FOREIGN_MARKETS = frozenset({
        "usa", "united states", "uk", "united kingdom", "australia",
        "canada", "uae", "dubai", "singapore", "new zealand",
        "germany", "france", "netherlands", "ireland",
    })

    def search(
        self,
        country: str,
        city: str,
        category: str,
        max_results: int = 20,
        **kwargs,
    ) -> List[RawProspect]:
        if not self.is_configured:
            logger.warning("Search API not configured. Skipping.")
            return []

        is_foreign = country.lower().strip() in self.FOREIGN_MARKETS

        # Build search queries — foreign markets get contact-rich queries
        # that naturally surface businesses with websites and digital footprints.
        if is_foreign:
            queries = [
                f"{category} in {city} {country} official website book appointment",
                f"{category} {city} {country} contact phone email booking online",
                f"best {category} {city} {country} website reviews",
            ]
        else:
            queries = [
                f"{category} in {city} {country} contact phone email website",
                f"{category} {city} {country} business directory",
            ]

        all_results: List[RawProspect] = []

        for query in queries:
            budget = max_results // len(queries)
            results = self._execute_search(query, max_results=budget)
            # Inject city/country into every prospect so downstream
            # verification and scoring have proper location context.
            for p in results:
                if not p.city:
                    p.city = city
                if not p.country:
                    p.country = country
            all_results.extend(results)

        # Dedup by domain
        seen_domains = set()
        unique = []
        for p in all_results:
            domain = self._extract_domain(p.website or p.source_url)
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                unique.append(p)
            elif not domain:
                unique.append(p)

        logger.info(f"Google Search: found {len(unique)} unique businesses")
        return unique[:max_results]

    def _execute_search(self, query: str, max_results: int = 10) -> List[RawProspect]:
        """Route to the configured search provider. Catches all exceptions."""
        provider = settings.search.provider.lower()

        try:
            if provider == "tavily":
                return self._search_tavily(query, max_results)
            elif provider == "serpapi":
                return self._search_serpapi(query, max_results)
            elif provider == "google_cse":
                return self._search_google_cse(query, max_results)
            elif provider == "bing":
                return self._search_bing(query, max_results)
            else:
                logger.warning(f"Unknown search provider: {provider}")
                return []
        except Exception as e:
            logger.error(f"Search failed ({provider}): {e}")
            return []

    def _search_tavily(self, query: str, max_results: int) -> List[RawProspect]:
        """Search using Tavily API."""
        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=settings.search.api_key)
            response = client.search(query=query, max_results=max_results)

            prospects = []
            for result in response.get("results", []):
                title = result.get("title", "")
                url = result.get("url", "")
                snippet = result.get("content", "")

                # Extract contact info from snippet
                email = self._extract_email(snippet)
                phone = self._extract_phone(snippet)
                domain = self._extract_domain(url)

                prospects.append(
                    RawProspect(
                        business_name=self._clean_name(title),
                        country="",
                        city="",
                        email=email,
                        phone=phone,
                        website=url if domain else "",
                        source="google_search",
                        source_url=url,
                        metadata={"snippet": snippet},
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return []

    def _search_serpapi(self, query: str, max_results: int) -> List[RawProspect]:
        """Search using SerpAPI."""
        try:
            import requests

            params = {
                "q": query,
                "api_key": settings.search.api_key,
                "num": max_results,
                "engine": "google",
            }
            resp = requests.get(
                "https://serpapi.com/search", params=params, timeout=30
            )
            data = resp.json()

            prospects = []
            for result in data.get("organic_results", []):
                title = result.get("title", "")
                url = result.get("link", "")
                snippet = result.get("snippet", "")
                email = self._extract_email(snippet)
                phone = self._extract_phone(snippet)

                prospects.append(
                    RawProspect(
                        business_name=self._clean_name(title),
                        email=email,
                        phone=phone,
                        website=url,
                        source="google_search",
                        source_url=url,
                        metadata={"snippet": snippet},
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"SerpAPI search failed: {e}")
            return []

    def _search_google_cse(self, query: str, max_results: int) -> List[RawProspect]:
        """Search using Google Custom Search Engine."""
        try:
            import requests

            cse_id = settings.search.api_key  # Reuse for CSE ID
            params = {
                "q": query,
                "cx": cse_id,
                "key": settings.search.api_key,
                "num": min(max_results, 10),
            }
            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params=params,
                timeout=30,
            )
            data = resp.json()

            prospects = []
            for item in data.get("items", []):
                title = item.get("title", "")
                url = item.get("link", "")
                snippet = item.get("snippet", "")

                prospects.append(
                    RawProspect(
                        business_name=self._clean_name(title),
                        website=url,
                        source="google_search",
                        source_url=url,
                        metadata={"snippet": snippet},
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"Google CSE search failed: {e}")
            return []

    def _search_bing(self, query: str, max_results: int) -> List[RawProspect]:
        """Search using Bing Search API."""
        try:
            import requests

            headers = {"Ocp-Apim-Subscription-Key": settings.search.api_key}
            params = {"q": query, "count": max_results}
            resp = requests.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers=headers,
                params=params,
                timeout=30,
            )
            data = resp.json()

            prospects = []
            for result in data.get("webPages", {}).get("value", []):
                title = result.get("name", "")
                url = result.get("url", "")
                snippet = result.get("snippet", "")

                prospects.append(
                    RawProspect(
                        business_name=self._clean_name(title),
                        website=url,
                        source="google_search",
                        source_url=url,
                        metadata={"snippet": snippet},
                    )
                )
            return prospects

        except Exception as e:
            logger.error(f"Bing search failed: {e}")
            return []

    # ---- Text extraction helpers ----

    @staticmethod
    def _extract_email(text: str) -> str:
        """Extract email address from text."""
        match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        return match.group(0) if match else ""

    @staticmethod
    def _extract_phone(text: str) -> str:
        """Extract phone number from text (international formats)."""
        patterns = [
            r"\+\d{1,3}[-.\s]?\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}",
            r"\d{3,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}",
        ]
        for pat in patterns:
            match = re.search(pat, text)
            if match:
                return match.group(0)
        return ""

    @staticmethod
    def _extract_domain(url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower().lstrip("www.")
        except Exception:
            return ""

    @staticmethod
    def _clean_name(title: str) -> str:
        """Clean a business name extracted from search results."""
        # Remove common suffixes
        for suffix in [" - Home", " | Official", " | Contact Us", " | About"]:
            if suffix.lower() in title.lower():
                title = title[: title.lower().index(suffix.lower())]
        return title.strip()
