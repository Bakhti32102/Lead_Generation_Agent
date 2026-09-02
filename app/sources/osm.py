"""
OpenStreetMap / Overpass API source.
Discovers local businesses using the free public Overpass API.
No API key or credentials required.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.sources.base import LeadSource, RawProspect

logger = logging.getLogger(__name__)

# ---------- Category → OSM tag mapping ----------

CATEGORY_TAG_MAP: Dict[str, List[Tuple[str, str]]] = {
    # Medical / Dental
    "dental clinics": [("amenity", "dentist")],
    "dentist": [("amenity", "dentist")],
    "dental": [("amenity", "dentist")],
    "clinic": [("amenity", "clinic"), ("amenity", "doctors")],
    "clinics": [("amenity", "clinic"), ("amenity", "doctors")],
    "medical": [("amenity", "clinic"), ("amenity", "doctors"), ("amenity", "hospital")],
    "hospital": [("amenity", "hospital")],
    "hospitals": [("amenity", "hospital")],
    "pharmacy": [("amenity", "pharmacy")],
    "doctor": [("amenity", "doctors")],
    "doctors": [("amenity", "doctors")],
    # Beauty / Spa
    "beauty parlor": [("shop", "beauty")],
    "beauty parlour": [("shop", "beauty")],
    "beauty": [("shop", "beauty")],
    "salon": [("shop", "beauty"), ("shop", "hairdresser")],
    "salons": [("shop", "beauty"), ("shop", "hairdresser")],
    "hairdresser": [("shop", "hairdresser")],
    "spa": [("shop", "beauty"), ("leisure", "spa")],
    "makeup": [("shop", "beauty")],
    "cosmetic": [("shop", "beauty"), ("shop", "cosmetics")],
    "cosmetics": [("shop", "cosmetics")],
    # Food & Drink
    "restaurant": [("amenity", "restaurant")],
    "restaurants": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "cafes": [("amenity", "cafe")],
    "food": [("amenity", "restaurant"), ("amenity", "fast_food")],
    "fast_food": [("amenity", "fast_food")],
    # Fitness
    "gym": [("leisure", "fitness_centre")],
    "gyms": [("leisure", "fitness_centre")],
    "fitness": [("leisure", "fitness_centre")],
    # General business
    "hotel": [("tourism", "hotel")],
    "hotels": [("tourism", "hotel")],
    "real_estate": [("office", "estate_agent")],
    "real estate": [("office", "estate_agent")],
    "travel": [("office", "travel_agent")],
}

# ---------- City → approximate bbox (lat, lon) ----------
# Used as fallback when the area-based Overpass search returns nothing.

CITY_BBOXES: Dict[str, Tuple[float, float, float, float]] = {
    "lahore": (31.30, 74.05, 31.65, 74.55),
    "karachi": (24.75, 66.90, 25.10, 67.30),
    "islamabad": (33.55, 72.95, 33.85, 73.30),
    "rawalpindi": (33.45, 73.00, 33.65, 73.20),
    "faisalabad": (31.30, 72.95, 31.55, 73.25),
    "multan": (30.10, 71.40, 30.30, 71.65),
    "peshawar": (33.95, 71.45, 34.10, 71.70),
    "quetta": (30.10, 66.90, 30.30, 67.10),
    "sialkot": (32.45, 74.45, 32.55, 74.60),
    "gujranwala": (32.10, 74.10, 32.25, 74.30),
    # Common international cities
    "new york": (40.50, -74.25, 40.90, -73.70),
    "london": (51.30, -0.50, 51.70, 0.30),
    "dubai": (25.00, 55.10, 25.40, 55.40),
}

USER_AGENT = "LeadGenerationAgent/1.0 (AI-Lead-Gen-Project)"


def _build_address(tag: Dict[str, Any]) -> str:
    """Build a human-readable address from OSM addr:* tags."""
    parts = []
    for key in [
        "addr:housenumber",
        "addr:street",
        "addr:suburb",
        "addr:neighbourhood",
        "addr:district",
        "addr:city",
        "addr:state",
        "addr:postcode",
    ]:
        val = tag.get(key, "").strip()
        if val:
            parts.append(val)
    return ", ".join(parts)


def _build_tag_filter(tag_pairs: List[Tuple[str, str]]) -> str:
    """Build Overpass tag filter string like: ["amenity"="dentist"]"""
    clauses = []
    for key, value in tag_pairs:
        clauses.append(f'["{key}"="{value}"]')
    return "".join(clauses)


def _overpass_post(query: str) -> Optional[Dict]:
    """Send a query to the Overpass API and return parsed JSON."""
    import requests

    resp = requests.post(
        "https://overpass-api.de/api/interpreter",
        data=query.encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        timeout=40,
    )
    resp.raise_for_status()
    return resp.json()


class OpenStreetMapSource(LeadSource):
    """Search OpenStreetMap via the public Overpass API for local businesses."""

    @property
    def name(self) -> str:
        return "openstreetmap"

    @property
    def is_configured(self) -> bool:
        # Overpass API is public and free — always available
        return True

    # ------------------------------------------------------------------
    # Public search entry point
    # ------------------------------------------------------------------

    def search(
        self,
        country: str,
        city: str,
        category: str,
        max_results: int = 20,
        **kwargs,
    ) -> List[RawProspect]:
        if not city and not country:
            logger.warning("OSM source requires at least a city or country. Skipping.")
            return []

        logger.info(
            f"OpenStreetMap: searching for '{category}' in {city}, {country}..."
        )

        tag_pairs = self._resolve_tags(category)
        tag_filter = _build_tag_filter(tag_pairs)

        # Strategy 1: area-based search (respects administrative boundaries)
        elements = self._search_by_area(city, country, tag_filter)

        # Strategy 2: bbox fallback (uses approximate coordinates)
        if not elements and city:
            elements = self._search_by_bbox(city, tag_filter)

        logger.info(f"OpenStreetMap: got {len(elements)} raw elements")

        prospects: List[RawProspect] = []
        for element in elements[:max_results]:
            prospect = self._parse_element(element, country, city, category)
            if prospect:
                prospects.append(prospect)

        logger.info(
            f"OpenStreetMap: converted {len(prospects)} elements to prospects"
        )
        return prospects

    # ------------------------------------------------------------------
    # Search strategies
    # ------------------------------------------------------------------

    def _search_by_area(
        self, city: str, country: str, tag_filter: str
    ) -> List[Dict]:
        """Search using Overpass area syntax (administrative boundaries)."""
        area_clause = ""
        if city:
            area_clause = f'area["name"="{city}"]["boundary"="administrative"]->.searchArea;'
        elif country:
            area_clause = f'area["name"="{country}"]["boundary"="administrative"]->.searchArea;'
        else:
            return []

        query = f"""
[out:json][timeout:25];
{area_clause}
(
  node{tag_filter}(area.searchArea);
  way{tag_filter}(area.searchArea);
);
out center body;
"""
        try:
            data = _overpass_post(query)
            return data.get("elements", []) if data else []
        except Exception as e:
            logger.debug(f"OSM area search failed: {e}")
            return []

    def _search_by_bbox(self, city: str, tag_filter: str) -> List[Dict]:
        """Search using an approximate bounding box for the city."""
        bbox = CITY_BBOXES.get(city.lower().strip())
        if not bbox:
            logger.info(
                f"OSM: no bbox available for '{city}'. "
                "Add it to CITY_BBOXES for better results."
            )
            return []

        south, west, north, east = bbox
        query = f"""
[out:json][timeout:25];
(
  node{tag_filter}({south},{west},{north},{east});
  way{tag_filter}({south},{west},{north},{east});
);
out center body;
"""
        try:
            data = _overpass_post(query)
            return data.get("elements", []) if data else []
        except Exception as e:
            logger.debug(f"OSM bbox search failed: {e}")
            return []

    # ------------------------------------------------------------------
    # Tag resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_tags(category: str) -> List[Tuple[str, str]]:
        """Map a business category string to OSM tag pairs."""
        lower = category.lower().strip()
        if lower in CATEGORY_TAG_MAP:
            return CATEGORY_TAG_MAP[lower]
        # Fallback: treat as amenity type
        return [("amenity", lower)]

    # ------------------------------------------------------------------
    # Element → RawProspect
    # ------------------------------------------------------------------

    def _parse_element(
        self,
        element: Dict[str, Any],
        country: str,
        city: str,
        category: str,
    ) -> Optional[RawProspect]:
        tags = element.get("tags", {})
        name = tags.get("name", "").strip()
        if not name:
            return None

        # Coordinates
        lat = element.get("lat") or element.get("center", {}).get("lat", 0)
        lon = element.get("lon") or element.get("center", {}).get("lon", 0)
        element_type = element.get("type", "node")
        element_id = element.get("id", "")

        source_url = f"https://www.openstreetmap.org/{element_type}/{element_id}"
        address = _build_address(tags)
        phone = tags.get("phone", "") or tags.get("contact:phone", "")
        website = tags.get("website", "") or tags.get("contact:website", "")
        email = tags.get("email", "") or tags.get("contact:email", "")

        osm_category = (
            tags.get("amenity", "")
            or tags.get("shop", "")
            or tags.get("leisure", "")
            or tags.get("tourism", "")
            or tags.get("office", "")
            or category
        )

        return RawProspect(
            business_name=name,
            business_category=osm_category,
            country=country,
            city=city,
            address=address,
            phone=phone,
            email=email,
            website=website,
            source="openstreetmap",
            source_url=source_url,
            metadata={
                "osm_element_type": element_type,
                "osm_element_id": element_id,
                "lat": lat,
                "lon": lon,
                "osm_addr_tags": {
                    k: v for k, v in tags.items() if k.startswith("addr:")
                },
            },
        )
