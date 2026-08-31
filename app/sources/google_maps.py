"""
Google Maps / Places API source.
Discovers local businesses using the official Google Places API.
"""

from __future__ import annotations

import logging
from typing import List

from app.config.settings import settings
from app.sources.base import LeadSource, RawProspect

logger = logging.getLogger(__name__)


class GoogleMapsSource(LeadSource):
    """Search Google Maps/Places for local businesses."""

    @property
    def name(self) -> str:
        return "google_maps"

    @property
    def is_configured(self) -> bool:
        return settings.google_maps.is_configured

    def search(
        self,
        country: str,
        city: str,
        category: str,
        max_results: int = 20,
        **kwargs,
    ) -> List[RawProspect]:
        if not self.is_configured:
            logger.warning("Google Maps API key not configured. Skipping.")
            return []

        import requests

        api_key = settings.google_maps.api_key
        prospects: List[RawProspect] = []

        # Build the search query
        query = f"{category} in {city}, {country}"
        url = "https://maps.googleapis.com/maps/api/place/textsearch/json"

        params = {
            "query": query,
            "key": api_key,
            "type": "establishment",
        }

        try:
            resp = requests.get(url, params=params, timeout=30)
            data = resp.json()

            if data.get("status") != "OK":
                logger.warning(f"Google Maps API status: {data.get('status')}")
                # Try alternative: use place_id search if available
                return []

            results = data.get("results", [])

            for place in results[:max_results]:
                prospect = self._parse_place(place, country, city, category)
                if prospect:
                    prospects.append(prospect)

            # If we have more pages and need more results, get next page
            next_token = data.get("next_page_token")
            while len(prospects) < max_results and next_token:
                import time
                time.sleep(2)  # Required delay for next_page_token

                next_resp = requests.get(
                    url,
                    params={"pagetoken": next_token, "key": api_key},
                    timeout=30,
                )
                next_data = next_resp.json()
                if next_data.get("status") != "OK":
                    break

                for place in next_data.get("results", [])[: max_results - len(prospects)]:
                    prospect = self._parse_place(place, country, city, category)
                    if prospect:
                        prospects.append(prospect)

                next_token = next_data.get("next_page_token")

            logger.info(f"Google Maps: found {len(prospects)} businesses for '{query}'")
            return prospects

        except Exception as e:
            logger.error(f"Google Maps search failed: {e}")
            return []

    def _parse_place(
        self, place: dict, country: str, city: str, category: str
    ) -> RawProspect:
        """Parse a Google Places result into a RawProspect."""
        name = place.get("name", "")
        if not name:
            return None

        # Get details
        formatted_address = place.get("formatted_address", "")
        rating = place.get("rating")
        place_id = place.get("place_id", "")
        maps_url = f"https://maps.google.com/?cid={place.get('cid', '')}" if place.get("cid") else ""
        if not maps_url and place_id:
            maps_url = f"https://maps.google.com/place?place_id={place_id}"

        # Try to get phone and website via Place Details
        phone = ""
        website = ""
        if place_id and settings.google_maps.api_key:
            details = self._get_place_details(place_id)
            if details:
                phone = details.get("phone", "")
                website = details.get("website", "")

        categories = place.get("types", [])
        primary_type = place.get("types", [category])[0] if place.get("types") else category

        return RawProspect(
            business_name=name,
            business_category=primary_type,
            country=country,
            city=city,
            address=formatted_address,
            phone=phone,
            website=website,
            google_maps_url=maps_url,
            source="google_maps",
            source_url=maps_url,
            metadata={
                "rating": rating,
                "place_id": place_id,
                "types": categories,
            },
        )

    def _get_place_details(self, place_id: str) -> dict:
        """Fetch additional details for a place (phone, website)."""
        if not self.is_configured:
            return {}

        import requests

        api_key = settings.google_maps.api_key
        url = "https://maps.googleapis.com/maps/api/place/details/json"
        params = {
            "place_id": place_id,
            "fields": "formatted_phone_number,website,url",
            "key": api_key,
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            data = resp.json()
            if data.get("status") == "OK":
                result = data.get("result", {})
                return {
                    "phone": result.get("formatted_phone_number", ""),
                    "website": result.get("website", ""),
                }
        except Exception as e:
            logger.debug(f"Place details fetch failed for {place_id}: {e}")

        return {}
