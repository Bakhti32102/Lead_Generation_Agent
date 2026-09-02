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
        all_prospects: List[RawProspect] = []

        source_map: Dict[str, tuple] = {
            "google_maps": (GoogleMapsSource, search_google_maps),
            "openstreetmap": (OpenStreetMapSource, True),  # Always enabled — free, no API key
            "google_search": (GoogleSearchSource, search_google),
            "linkedin": (LinkedInSource, search_linkedin and search_recent_requirements),
            "public_jobs": (PublicJobSource, search_recent_requirements),
            "serpapi": (SerpAPISource, search_google),  # SerpAPI used for additional Google/Maps/LinkedIn search
        }

        for source_name, (source_class, enabled) in source_map.items():
            if not enabled:
                continue

            source = source_class()
            if not source.is_configured:
                logger.info(f"Source '{source_name}' not configured. Skipping.")
                continue

            logger.info(f"Searching {source_name} for {category} in {city}, {country}...")
            try:
                # SerpAPI can search multiple engines
                if source_name == "serpapi":
                    results = source.search(
                        country=country,
                        city=city,
                        category=category,
                        max_results=max_results // 3,  # Split budget
                        search_type="google_maps",
                    )
                    # Also search LinkedIn via SerpAPI if LinkedIn is enabled
                    if search_linkedin and search_recent_requirements:
                        linkedin_results = source.search(
                            country=country,
                            city=city,
                            category=category,
                            max_results=max_results // 4,
                            search_type="linkedin",
                        )
                        results.extend(linkedin_results)
                else:
                    results = source.search(
                        country=country,
                        city=city,
                        category=category,
                        max_results=max_results // 2 if source_name != "openstreetmap" else max_results,
                    )

                all_prospects.extend(results)
                logger.info(f"  -> {source_name}: found {len(results)} prospects")
            except Exception as e:
                logger.error(f"  -> {source_name} failed: {e}")

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
