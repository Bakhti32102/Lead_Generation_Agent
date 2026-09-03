"""
Lead Discovery Agent.
Orchestrates all configured search sources, merges results, and deduplicates.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.config.settings import settings
from app.database import LeadRepository
from app.sources.base import LeadSource, RawProspect
from app.utils.categories import normalize_category
from app.sources.google_search import GoogleSearchSource
from app.sources.google_maps import GoogleMapsSource
from app.sources.linkedin import LinkedInSource
from app.sources.public_jobs import PublicJobSource
from app.sources.serpapi import SerpAPISource
from app.sources.osm import OpenStreetMapSource

logger = logging.getLogger(__name__)


class LeadDiscoveryAgent:
    """Discovers prospects using all configured search sources."""

    def __init__(self):
        self.repo = LeadRepository()
        self.sources: List[LeadSource] = [
            GoogleMapsSource(),
            OpenStreetMapSource(),
            GoogleSearchSource(),
            LinkedInSource(),
            PublicJobSource(),
            SerpAPISource(),
        ]

    def discover(
        self,
        country: str,
        city: str,
        category: str,
        max_results: int = 30,
        search_google_maps: bool = True,
        search_google: bool = True,
        search_linkedin: bool = True,
        search_recent_requirements: bool = True,
    ) -> List[RawProspect]:
        """
        Search all configured sources and return merged, deduplicated prospects.
        Respects the daily target location — never expands beyond the given
        country/city/category.
        """
        # Normalize category to fix typos (e.g. "Dintest" -> "Dentist")
        category = normalize_category(category)

        all_prospects: List[RawProspect] = []

        # Foreign markets get more budget to web search (Tavily) since
        # OSM data is sparser outside Pakistan.  Domestic campaigns lean
        # heavier on OSM where coverage is strong.
        FOREIGN_MARKETS = frozenset({
            "usa", "united states", "uk", "united kingdom", "australia",
            "canada", "uae", "dubai", "singapore", "new zealand",
            "germany", "france", "netherlands", "ireland",
        })
        is_foreign = country.lower().strip() in FOREIGN_MARKETS

        source_map: Dict[str, tuple] = {
            "google_maps": (GoogleMapsSource, search_google_maps),
            "openstreetmap": (OpenStreetMapSource, True),  # Always enabled — free, no API key
            "google_search": (GoogleSearchSource, search_google),
            "linkedin": (LinkedInSource, search_linkedin and search_recent_requirements),
            "public_jobs": (PublicJobSource, search_recent_requirements),
            "serpapi": (SerpAPISource, search_google),
        }

        osm_prospect_count = 0  # Track OSM results for fallback decision

        for source_name, (source_class, enabled) in source_map.items():
            if not enabled:
                logger.info(f"[Discovery] Source '{source_name}' disabled by config. Skipping.")
                continue

            source = source_class()
            if not source.is_configured:
                logger.warning(f"[Discovery] Source '{source_name}' not configured — missing API key or credentials. Skipping.")
                continue

            logger.info(f"[Discovery] Searching {source_name} for '{category}' in {city}, {country}...")
            try:
                # Budget allocation: foreign markets give more to web search
                if source_name == "serpapi":
                    results = source.search(
                        country=country, city=city, category=category,
                        max_results=max_results // 3,
                        search_type="google_maps",
                    )
                    if search_linkedin and search_recent_requirements:
                        linkedin_results = source.search(
                            country=country, city=city, category=category,
                            max_results=max_results // 4,
                            search_type="linkedin",
                        )
                        results.extend(linkin_results)
                elif source_name == "google_search":
                    # Foreign: give web search 60% of budget
                    # Domestic: give it 40%
                    budget = int(max_results * (0.6 if is_foreign else 0.4))
                    results = source.search(
                        country=country, city=city, category=category,
                        max_results=budget,
                    )
                elif source_name == "openstreetmap":
                    # Foreign: reduce OSM budget (sparser data)
                    # Domestic: full budget
                    budget = max_results if not is_foreign else max_results // 2
                    results = source.search(
                        country=country, city=city, category=category,
                        max_results=budget,
                    )
                    osm_prospect_count = len(results)
                else:
                    results = source.search(
                        country=country, city=city, category=category,
                        max_results=max_results // 2,
                    )

                all_prospects.extend(results)
                logger.info(f"[Discovery]   -> {source_name}: found {len(results)} prospects")
            except Exception as e:
                logger.error(f"[Discovery]   -> {source_name} FAILED: {type(e).__name__}: {e}")

        # ── Automatic Google Search fallback for OSM ──
        # If OpenStreetMap returned 0 raw prospects (empty results or timeout),
        # automatically execute Google Search for the same category/location
        # to ensure we still have a chance of finding leads. The fallback
        # prospects go through the same dedup, retail filter, and verification
        # pipeline as all other sources.
        if osm_prospect_count == 0:
            logger.warning(
                f"[Discovery] OSM returned 0 prospects for '{category}' in {city}, {country}. "
                "Executing Google Search fallback..."
            )
            try:
                fallback_source = GoogleSearchSource()
                if fallback_source.is_configured:
                    fallback_budget = int(max_results * (0.6 if is_foreign else 0.4))
                    logger.info(
                        f"[Discovery] Google Search fallback: provider={settings.search.provider}, "
                        f"budget={fallback_budget}, query='{category} in {city}, {country}'"
                    )
                    fallback_results = fallback_source.search(
                        country=country, city=city, category=category,
                        max_results=fallback_budget,
                    )
                    all_prospects.extend(fallback_results)
                    logger.info(
                        f"[Discovery] Google Search fallback complete: {len(fallback_results)} prospects found"
                    )
                else:
                    logger.error(
                        f"[Discovery] Google Search fallback SKIPPED: "
                        f"SEARCH_API_KEY not configured (provider={settings.search.provider}). "
                        f"Set SEARCH_API_KEY env var to enable fallback."
                    )
            except Exception as e:
                logger.error(
                    f"[Discovery] Google Search fallback FAILED: {type(e).__name__}: {e}\n"
                    f"  Provider: {settings.search.provider}\n"
                    f"  API key present: {bool(settings.search.api_key)}\n"
                    f"  This means zero leads were recovered from OSM AND Google Search."
                )

        # Merge and deduplicate
        merged = self._deduplicate(all_prospects)
        logger.info(
            f"Discovery complete: {len(all_prospects)} raw -> {len(merged)} unique prospects"
        )
        return merged[:max_results]

    def _deduplicate(self, prospects: List[RawProspect]) -> List[RawProspect]:
        """
        Remove duplicates based on:
        - Website domain
        - Email
        - Phone
        - Google Maps URL
        - Business name + city (fuzzy)
        """
        seen_websites: set = set()
        seen_emails: set = set()
        seen_phones: set = set()
        seen_maps: set = set()
        seen_names: set = set()

        unique: List[RawProspect] = []

        for p in prospects:
            # Validate business name first
            if not p.validate_name():
                reason = p.metadata.get('name_rejection_reason', 'invalid')
                logger.info(f"Rejected prospect with invalid name: '{p.business_name[:50]}' ({reason})")
                continue

            # Skip if already in database
            existing = self.repo.is_duplicate(
                website=p.website,
                email=p.email,
                phone=p.phone,
                maps_url=p.google_maps_url,
                name=p.business_name,
            )
            if existing is not None:
                continue

            # Dedup within this batch
            website_key = self._normalize_website(p.website)
            email_key = p.email.lower().strip()
            phone_key = self._normalize_phone(p.phone)
            maps_key = p.google_maps_url.strip()
            name_key = f"{p.business_name.lower().strip()}|{p.city.lower().strip()}"

            if website_key and website_key in seen_websites:
                continue
            if email_key and email_key in seen_emails:
                continue
            if phone_key and phone_key in seen_phones:
                continue
            if maps_key and maps_key in seen_maps:
                continue
            if name_key in seen_names:
                continue

            # Add to unique set
            if website_key:
                seen_websites.add(website_key)
            if email_key:
                seen_emails.add(email_key)
            if phone_key:
                seen_phones.add(phone_key)
            if maps_key:
                seen_maps.add(maps_key)
            if p.business_name:
                seen_names.add(name_key)

            unique.append(p)

        return unique

    @staticmethod
    def _normalize_website(url: str) -> str:
        """Normalize website URL for dedup comparison."""
        if not url:
            return ""
        url = url.lower().strip()
        for prefix in ["https://", "http://", "www."]:
            if url.startswith(prefix):
                url = url[len(prefix):]
        url = url.rstrip("/")
        return url

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        """Normalize phone number for dedup comparison."""
        if not phone:
            return ""
        # Keep only digits
        digits = "".join(c for c in phone if c.isdigit())
        return digits
