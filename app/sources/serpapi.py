"""
SerpAPI Source.
Uses SerpAPI for Google Search, Google Maps, LinkedIn, and Job Board searches.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

import requests

from app.config.settings import settings
from app.sources.base import LeadSource, RawProspect

logger = logging.getLogger(__name__)


class SerpAPISource(LeadSource):
    """Search via SerpAPI for businesses and requirements."""

    @property
    def name(self) -> str:
        return "serpapi"

    @property
    def is_configured(self) -> bool:
        return bool(settings.search.api_key) and settings.search.provider.lower() == "serpapi"

    def search(
        self,
        country: str,
        city: str,
        category: str,
        max_results: int = 20,
        **kwargs,
    ) -> List[RawProspect]:
        """Search SerpAPI for businesses matching the target."""
        if not self.is_configured:
            logger.warning("SerpAPI not configured. Skipping.")
            return []

        search_type = kwargs.get("search_type", "google")
        all_prospects: List[RawProspect] = []

        try:
            if search_type == "google":
                all_prospects = self._search_google(country, city, category, max_results)
            elif search_type == "google_maps":
                all_prospects = self._search_google_maps(country, city, category, max_results)
            elif search_type == "linkedin":
                all_prospects = self._search_linkedin(country, city, category, max_results)
            elif search_type == "jobs":
                all_prospects = self._search_jobs(country, city, category, max_results)
            elif search_type == "all":
                all_prospects = self._search_all(country, city, category, max_results)
            else:
                logger.warning(f"Unknown SerpAPI search type: {search_type}")
        except Exception as e:
            logger.error(f"SerpAPI search failed: {e}")

        return all_prospects[:max_results]

    def _search_google(
        self, country: str, city: str, category: str, max_results: int
    ) -> List[RawProspect]:
        """Google Search via SerpAPI."""
        queries = [
            f"{category} in {city} {country} contact phone email website",
            f"{category} {city} {country} business directory",
        ]

        prospects: List[RawProspect] = []

        for query in queries[:1]:
            try:
                params = {
                    "q": query,
                    "api_key": settings.search.api_key,
                    "engine": "google",
                    "num": min(max_results, 20),
                    "gl": self._country_code(country),
                    "hl": "en",
                }

                resp = requests.get(
                    "https://serpapi.com/search",
                    params=params,
                    timeout=30,
                )
                data = resp.json()

                for result in data.get("organic_results", []):
                    title = result.get("title", "")
                    url = result.get("link", "")
                    snippet = result.get("snippet", "")
                    displayed_link = result.get("displayed_link", "")

                    email = self._extract_email(snippet + " " + displayed_link)
                    phone = self._extract_phone(snippet)
                    website = url if url and not any(
                        domain in url.lower()
                        for domain in ["facebook.com", "twitter.com", "instagram.com", "yelp.com"]
                    ) else ""

                    prospects.append(
                        RawProspect(
                            business_name=self._clean_name(title),
                            country=country,
                            city=city,
                            email=email,
                            phone=phone,
                            website=website,
                            source="serpapi_google",
                            source_url=url,
                            metadata={
                                "snippet": snippet,
                                "displayed_link": displayed_link,
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"SerpAPI Google search failed: {e}")

        return prospects

    def _search_google_maps(
        self, country: str, city: str, category: str, max_results: int
    ) -> List[RawProspect]:
        """Google Maps Search via SerpAPI."""
        query = f"{category} in {city}, {country}"
        prospects: List[RawProspect] = []

        try:
            params = {
                "q": query,
                "api_key": settings.search.api_key,
                "engine": "google_maps",
                "type": "search",
                "hl": "en",
            }

            resp = requests.get(
                "https://serpapi.com/search",
                params=params,
                timeout=30,
            )
            data = resp.json()

            for place in data.get("local_results", []):
                name = place.get("title", "")
                if not name:
                    continue

                address = place.get("address", "")
                phone = place.get("phone", "") or place.get("phone_unformatted", "")
                website = place.get("website", "")
                maps_url = place.get("place_id_search", "")
                rating = place.get("rating")
                reviews = place.get("reviews")
                type_ = place.get("type", "")
                thumbnail = place.get("thumbnail", "")

                prospects.append(
                    RawProspect(
                        business_name=name,
                        business_category=type_,
                        country=country,
                        city=city,
                        address=address,
                        phone=phone,
                        website=website,
                        google_maps_url=maps_url,
                        source="serpapi_maps",
                        source_url=maps_url,
                        metadata={
                            "rating": rating,
                            "reviews": reviews,
                            "thumbnail": thumbnail,
                        },
                    )
                )
        except Exception as e:
            logger.error(f"SerpAPI Google Maps search failed: {e}")

        return prospects

    def _search_linkedin(
        self, country: str, city: str, category: str, max_results: int
    ) -> List[RawProspect]:
        """LinkedIn Search via SerpAPI (uses Google with site:linkedin.com)."""
        keywords = [
            "need AI agent",
            "looking for AI developer",
            "need chatbot",
            "need AI automation",
            "need website development",
        ]

        prospects: List[RawProspect] = []
        seen_urls: set = set()

        for keyword in keywords[:3]:
            query = f"site:linkedin.com {keyword} {city} {country}"
            try:
                params = {
                    "q": query,
                    "api_key": settings.search.api_key,
                    "engine": "google",
                    "num": 10,
                    "tbs": "qdr:d",
                }

                resp = requests.get(
                    "https://serpapi.com/search",
                    params=params,
                    timeout=30,
                )
                data = resp.json()

                for result in data.get("organic_results", []):
                    url = result.get("link", "")
                    if "linkedin.com" not in url:
                        continue
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)

                    title = result.get("title", "")
                    snippet = result.get("snippet", "")

                    prospects.append(
                        RawProspect(
                            business_name=self._extract_company_from_title(title),
                            country=country,
                            city=city,
                            business_category=category,
                            source="serpapi_linkedin",
                            source_url=url,
                            requirement_text=snippet[:300],
                            freshness="probably_recent",
                            metadata={
                                "title": title,
                                "snippet": snippet,
                            },
                        )
                    )
            except Exception as e:
                logger.error(f"SerpAPI LinkedIn search failed: {e}")

        return prospects

    def _search_jobs(
        self, country: str, city: str, category: str, max_results: int
    ) -> List[RawProspect]:
        """Job Board Search via SerpAPI."""
        query = f"AI chatbot developer needed {city} {country}"
        prospects: List[RawProspect] = []

        try:
            params = {
                "q": query,
                "api_key": settings.search.api_key,
                "engine": "google",
                "num": max_results,
                "tbs": "qdr:d",
            }

            resp = requests.get(
                "https://serpapi.com/search",
                params=params,
                timeout=30,
            )
            data = resp.json()

            for result in data.get("organic_results", []):
                url = result.get("link", "")
                if not self._is_job_platform(url):
                    continue

                title = result.get("title", "")
                snippet = result.get("snippet", "")

                prospects.append(
                    RawProspect(
                        business_name=self._extract_company_from_title(title),
                        country=country,
                        city=city,
                        source="serpapi_jobs",
                        source_url=url,
                        requirement_text=snippet[:300],
                        freshness="probably_recent",
                        metadata={
                            "title": title,
                            "snippet": snippet,
                        },
                    )
                )
        except Exception as e:
            logger.error(f"SerpAPI jobs search failed: {e}")

        return prospects

    def _search_all(
        self, country: str, city: str, category: str, max_results: int
    ) -> List[RawProspect]:
        """Search all SerpAPI engines and merge results."""
        all_prospects: List[RawProspect] = []

        maps_results = self._search_google_maps(country, city, category, max_results)
        all_prospects.extend(maps_results)

        google_results = self._search_google(country, city, category, max_results)
        all_prospects.extend(google_results)

        linkedin_results = self._search_linkedin(country, city, category, max_results)
        all_prospects.extend(linkedin_results)

        job_results = self._search_jobs(country, city, category, max_results)
        all_prospects.extend(job_results)

        return all_prospects

    # ---- Helper Methods ----

    @staticmethod
    def _extract_email(text: str) -> str:
        """Extract email address from text."""
        match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        return match.group(0) if match else ""

    @staticmethod
    def _extract_phone(text: str) -> str:
        """Extract phone number from text."""
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
    def _clean_name(title: str) -> str:
        """Clean a business name extracted from search results."""
        for suffix in [" - Home", " | Official", " | Contact Us", " | About", " - Google Maps"]:
            if suffix.lower() in title.lower():
                title = title[: title.lower().index(suffix.lower())]
        return title.strip()

    @staticmethod
    def _extract_company_from_title(title: str) -> str:
        """Extract company name from LinkedIn post/job title."""
        for sep in [" - ", " | ", " at ", " @ "]:
            if sep in title:
                parts = title.split(sep)
                for part in reversed(parts):
                    part = part.strip()
                    if part.lower() not in ("linkedin", "linkedin.com"):
                        return part
        return title.strip()

    @staticmethod
    def _is_job_platform(url: str) -> bool:
        """Check if URL belongs to a known job platform."""
        platforms = [
            "indeed.com", "glassdoor.com", "monster.com", "careerbuilder.com",
            "freelancer.com", "upwork.com", "fiverr.com", "peopleperhour.com",
            "guru.com", "toptal.com", "simplyhired.com", "ziprecruiter.com",
            "jooble.org", "naukri.com", "bayt.com", "gulf.com", "dubizzle.com",
            "linkedin.com/jobs",
        ]
        return any(platform in url.lower() for platform in platforms)

    @staticmethod
    def _country_code(country: str) -> str:
        """Convert country name to ISO country code for SerpAPI."""
        codes = {
            "pakistan": "pk", "uae": "ae", "united arab emirates": "ae",
            "united kingdom": "gb", "uk": "gb", "united states": "us",
            "usa": "us", "india": "in", "canada": "ca", "australia": "au",
            "germany": "de", "france": "fr", "saudi arabia": "sa",
            "qatar": "qa", "oman": "om", "bahrain": "bh", "kuwait": "kw",
            "jordan": "jo", "egypt": "eg", "turkey": "tr", "malaysia": "my",
            "singapore": "sg", "thailand": "th", "philippines": "ph",
            "nigeria": "ng", "south africa": "za", "kenya": "ke",
        }
        return codes.get(country.lower().strip(), "us")
