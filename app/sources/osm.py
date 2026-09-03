"""
OpenStreetMap / Overpass API source.
Discovers local businesses using the free public Overpass API.
No API key or credentials required.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from app.sources.base import LeadSource, RawProspect
from app.utils.categories import normalize_category

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
    # Beauty / Spa — Service providers only
    # Use amenity=hairdresser and leisure=spa for service providers.
    # shop=beauty and shop=hairdresser include both service and retail;
    # post-filtering in LeadVerification rejects retail stores.
    "beauty parlor": [("shop", "beauty"), ("shop", "hairdresser"), ("amenity", "hairdresser")],
    "beauty parlour": [("shop", "beauty"), ("shop", "hairdresser"), ("amenity", "hairdresser")],
    "beauty salon": [("shop", "beauty"), ("shop", "hairdresser"), ("amenity", "hairdresser"), ("leisure", "spa")],
    "beauty": [("shop", "beauty"), ("amenity", "hairdresser")],
    "salon": [("shop", "beauty"), ("shop", "hairdresser"), ("amenity", "hairdresser"), ("leisure", "spa")],
    "salons": [("shop", "beauty"), ("shop", "hairdresser"), ("amenity", "hairdresser")],
    "hair salon": [("shop", "hairdresser"), ("amenity", "hairdresser")],
    "hairdresser": [("shop", "hairdresser"), ("amenity", "hairdresser")],
    "hairdressers": [("shop", "hairdresser"), ("amenity", "hairdresser")],
    "barber": [("shop", "hairdresser"), ("amenity", "hairdresser")],
    "barber shop": [("shop", "hairdresser"), ("amenity", "hairdresser")],
    "spa": [("shop", "beauty"), ("leisure", "spa"), ("amenity", "spa")],
    "makeup": [("shop", "beauty"), ("amenity", "hairdresser")],
    "makeup artist": [("shop", "beauty"), ("amenity", "hairdresser")],
    "bridal": [("shop", "beauty"), ("shop", "hairdresser")],
    "bridal studio": [("shop", "beauty"), ("shop", "hairdresser")],
    "institut de beaute": [("shop", "beauty"), ("amenity", "hairdresser")],
    "nail salon": [("shop", "beauty"), ("shop", "nails")],
    "nails": [("shop", "beauty"), ("shop", "nails")],
    "cosmetic": [("shop", "beauty"), ("amenity", "hairdresser")],
    "cosmetics": [("shop", "beauty"), ("amenity", "hairdresser")],
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
    # ── Pakistan ──
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
    # ── USA ──
    "new york": (40.50, -74.25, 40.90, -73.70),
    "los angeles": (33.70, -118.50, 34.35, -117.90),
    "chicago": (41.60, -87.90, 42.10, -87.50),
    "houston": (29.50, -95.75, 29.95, -95.10),
    "phoenix": (33.25, -112.30, 33.70, -111.70),
    "san diego": (32.50, -117.30, 33.15, -116.80),
    "dallas": (32.55, -97.10, 33.00, -96.60),
    "miami": (25.60, -80.40, 25.90, -80.00),
    "seattle": (47.45, -122.45, 47.75, -122.20),
    "boston": (42.25, -71.20, 42.45, -70.90),
    # ── UK ──
    "london": (51.30, -0.50, 51.70, 0.30),
    "manchester": (53.40, -2.35, 53.55, -2.15),
    "birmingham": (52.40, -1.95, 52.55, -1.75),
    "glasgow": (55.80, -4.40, 55.90, -4.15),
    "edinburgh": (55.90, -3.30, 56.00, -3.10),
    "leeds": (53.75, -1.65, 53.85, -1.45),
    "bristol": (51.40, -2.70, 51.50, -2.50),
    # ── Australia ──
    "melbourne": (-38.00, 144.70, -37.65, 145.10),
    "sydney": (-34.00, 151.00, -33.70, 151.40),
    "brisbane": (-27.60, 152.90, -27.35, 153.20),
    "perth": (-32.10, 115.60, -31.80, 115.95),
    "adelaide": (-35.05, 138.60, -34.80, 138.90),
    "gold coast": (-28.10, 153.35, -27.90, 153.55),
    "canberra": (-35.40, 149.00, -35.20, 149.30),
    # ── Canada ──
    "toronto": (43.55, -79.65, 43.85, -79.20),
    "vancouver": (49.15, -123.25, 49.35, -123.00),
    "montreal": (45.40, -73.75, 45.60, -73.45),
    "calgary": (50.95, -114.25, 51.15, -113.85),
    "ottawa": (45.30, -75.85, 45.45, -75.60),
    # ── Europe ──
    "paris": (48.80, 2.20, 48.95, 2.50),
    "berlin": (52.30, 13.10, 52.60, 13.60),
    "amsterdam": (52.30, 4.70, 52.45, 5.00),
    "dublin": (53.25, -6.40, 53.45, -6.10),
    "madrid": (40.30, -3.85, 40.55, -3.55),
    "rome": (41.80, 12.35, 42.05, 12.65),
    # ── Middle East ──
    "dubai": (25.00, 55.10, 25.40, 55.40),
    "abu dhabi": (24.30, 54.30, 24.60, 54.70),
    "doha": (25.20, 51.40, 25.40, 51.70),
    # ── Asia ──
    "singapore": (1.20, 103.60, 1.45, 104.00),
    "kuala lumpur": (3.05, 101.55, 3.30, 101.80),
    "bangkok": (13.60, 100.40, 13.95, 100.80),
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


def _build_tag_filters(tag_pairs: List[Tuple[str, str]]) -> List[str]:
    """Build Overpass tag filter strings — one per alternative tag pair.

    Each tag pair becomes an independent filter string such as
    ``["shop"="beauty"]``.  The caller must search for each filter
    as a *separate* alternative (OR semantics) and merge the results.

    Previously this function concatenated all clauses into a single
    string (e.g. ``["shop"="beauty"]["shop"="hairdresser"]``), which
    produced AND semantics and returned zero results for every
    multi-tag category because a single OSM element cannot satisfy
    conflicting tag values.

    Returns:
        A list of single-filter strings.  For a single tag pair the
        list contains one element; for multiple pairs it contains one
        element per pair.
    """
    return [f'["{key}"="{value}"]' for key, value in tag_pairs]


# Strict timeout for Overpass API requests (seconds).
# Prevents the background campaign thread from hanging on slow Overpass
# responses — if it takes longer than this, we fall back to Google Search.
OVERPASS_TIMEOUT = 12


def _overpass_post(query: str) -> Optional[Dict]:
    """Send a query to the Overpass API and return parsed JSON.

    Uses a strict 12-second timeout to avoid blocking the background
    campaign thread.  Raises ``requests.exceptions.Timeout`` on timeout
    and ``requests.exceptions.HTTPError`` on non-2xx responses so the
    caller can decide whether to fall back.
    """
    import requests

    resp = requests.post(
        "https://overpass-api.de/api/interpreter",
        data=query.encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        timeout=OVERPASS_TIMEOUT,
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
        tag_filters = _build_tag_filters(tag_pairs)

        logger.info(
            f"OpenStreetMap: resolved {len(tag_filters)} tag alternatives "
            f"for '{category}': {tag_pairs}"
        )

        # Strategy 1: area-based search (respects administrative boundaries)
        elements = self._search_by_area(city, country, tag_filters)

        # Strategy 2: bbox fallback (uses approximate coordinates)
        if not elements and city:
            elements = self._search_by_bbox(city, tag_filters)

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
        self, city: str, country: str, tag_filters: List[str]
    ) -> List[Dict]:
        """Search using Overpass area syntax (administrative boundaries).

        Executes one Overpass query per alternative tag filter and merges
        results, deduplicating by element ID.  This implements OR semantics
        so that e.g. a beauty parlour search finds elements tagged with
        shop=beauty OR shop=hairdresser OR amenity=hairdresser.
        """
        area_clause = ""
        if city:
            area_clause = f'area["name"="{city}"]["boundary"="administrative"]->.searchArea;'
        elif country:
            area_clause = f'area["name"="{country}"]["boundary"="administrative"]->.searchArea;'
        else:
            return []

        seen_ids: set = set()
        all_elements: List[Dict] = []

        for tag_filter in tag_filters:
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
                elements = data.get("elements", []) if data else []
                for elem in elements:
                    eid = elem.get("id")
                    if eid and eid not in seen_ids:
                        seen_ids.add(eid)
                        all_elements.append(elem)
            except Exception as e:
                logger.debug(f"OSM area search failed for filter {tag_filter}: {e}")

        return all_elements

    def _search_by_bbox(self, city: str, tag_filters: List[str]) -> List[Dict]:
        """Search using an approximate bounding box for the city.

        Executes one Overpass query per alternative tag filter and merges
        results, deduplicating by element ID.
        """
        bbox = CITY_BBOXES.get(city.lower().strip())
        if not bbox:
            logger.info(
                f"OSM: no bbox available for '{city}'. "
                "Add it to CITY_BBOXES for better results."
            )
            return []

        south, west, north, east = bbox
        seen_ids: set = set()
        all_elements: List[Dict] = []

        for tag_filter in tag_filters:
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
                elements = data.get("elements", []) if data else []
                for elem in elements:
                    eid = elem.get("id")
                    if eid and eid not in seen_ids:
                        seen_ids.add(eid)
                        all_elements.append(elem)
            except Exception as e:
                logger.debug(f"OSM bbox search failed for filter {tag_filter}: {e}")

        return all_elements

    # ------------------------------------------------------------------
    # Tag resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_tags(category: str) -> List[Tuple[str, str]]:
        """Map a business category string to OSM tag pairs."""
        # Normalize category typos before lookup
        normalized = normalize_category(category).lower().strip()
        if normalized in CATEGORY_TAG_MAP:
            return CATEGORY_TAG_MAP[normalized]
        # Also try the original lower-cased form
        lower = category.lower().strip()
        if lower in CATEGORY_TAG_MAP:
            return CATEGORY_TAG_MAP[lower]
        # Fallback: treat as amenity type
        return [("amenity", normalized)]

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
