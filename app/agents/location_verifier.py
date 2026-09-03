"""
Location Verification Agent.
Uses textual evidence (snippet, URL, title, address, business_research)
to verify whether a business belongs to the target city/country.

Never invents location information. Only extracts what is present in the data.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.sources.base import RawProspect

logger = logging.getLogger(__name__)


@dataclass
class LocationVerification:
    """Result of location verification."""
    state: str  # "verified" | "probably_verified" | "unknown" | "mismatch"
    target_city: str
    target_country: str
    found_city: str
    found_country: str
    evidence_source: str  # which field provided the evidence
    confidence: float  # 0.0 to 1.0


class LocationVerifier:
    """Verifies whether a prospect belongs to the target city/country
    using textual evidence from multiple data sources."""

    # Common city aliases/synonyms for fuzzy matching
    CITY_ALIASES = {
        "lahore": ["lahore", "lhr"],
        "karachi": ["karachi", "khi"],
        "islamabad": ["islamabad", "isb"],
        "dubai": ["dubai", "dxb"],
        "abu dhabi": ["abu dhabi", "auh"],
        "mumbai": ["mumbai", "bombay"],
        "delhi": ["delhi", "new delhi", "ncy"],
        "bangalore": ["bangalore", "bengaluru", "blr"],
        "london": ["london", "ldn"],
        "new york": ["new york", "nyc", "ny"],
    }

    # Country name patterns (lowercase) → country code
    COUNTRY_PATTERNS = {
        "pakistan": ["pakistan", ".pk", "pk"],
        "uae": ["uae", "united arab emirates", "dubai", ".ae"],
        "india": ["india", ".in"],
        "uk": ["united kingdom", "uk", ".co.uk", "england", "london"],
        "usa": ["united states", "usa", ".com", "us"],
        "saudi arabia": ["saudi arabia", ".sa", "ksa"],
    }

    # Sources that perform bounded/geographically-constrained searches.
    # Prospects from these sources inherit the target city/country as
    # implicit evidence because the search itself was limited to that area.
    BOUNDED_SOURCES = frozenset({"openstreetmap", "google_maps"})

    def verify(self, prospect: RawProspect, target_city: str, target_country: str) -> LocationVerification:
        """
        Verify location using all available evidence.
        Never invents information — only extracts from existing data.

        Checks are applied in priority order:
        1. Coordinate bounds — reject if lat/lon is far from the target city
        2. Structured fields — city/country match on prospect metadata
        3. Textual evidence — snippet, URL, address analysis

        For bounded sources (OpenStreetMap, Google Maps) that searched within
        a specific city boundary, the source itself serves as implicit
        location evidence — no explicit city name in the address is required.
        However, Overpass area searches can return elements from other cities
        that share the same name (e.g. Melbourne, Florida for a Melbourne,
        Australia search), so coordinate bounds are the first line of defense.
        """
        target_city_lower = target_city.lower().strip()
        target_country_lower = target_country.lower().strip()

        # For bounded sources, inject target city/country as implicit
        # evidence when the prospect's own fields are empty.
        source = (prospect.source or "").lower()
        if source in self.BOUNDED_SOURCES:
            if not prospect.city and target_city_lower:
                prospect.city = target_city.title()
                prospect.metadata["city_inherited_from_source"] = True
            if not prospect.country and target_country_lower:
                prospect.country = target_country.title()
                prospect.metadata["country_inherited_from_source"] = True

        # ── Step 1: Coordinate bounds check (highest priority) ──
        # Reject prospects whose actual coordinates are far from the target
        # city.  This catches false positives from Overpass area searches
        # that return elements from cities sharing the same name (e.g.
        # Melbourne, FL for a Melbourne, AU search).
        coord_result = self._check_coordinate_bounds(prospect, target_city_lower, target_country_lower)
        if coord_result and coord_result.state == "mismatch":
            return coord_result

        # ── Step 2: Structured fields check ──
        structured_result = self._check_structured_fields(prospect, target_city_lower, target_country_lower)
        if structured_result and structured_result.state in ("verified", "mismatch"):
            return structured_result

        # Gather textual evidence from all available sources
        text_evidence = self._gather_text_evidence(prospect)
        text_result = self._check_text_evidence(text_evidence, target_city_lower, target_country_lower)

        # Combine results
        return self._combine_results(structured_result, text_result, target_city_lower, target_country_lower)

    def _check_structured_fields(
        self, prospect: RawProspect, target_city: str, target_country: str
    ) -> Optional[LocationVerification]:
        """Check structured country/city fields on the prospect."""
        city = (prospect.city or "").lower().strip()
        country = (prospect.country or "").lower().strip()

        # Both empty → no structured evidence
        if not city and not country:
            return None

        # Check city match
        city_match = False
        city_mismatch = False
        if city:
            if target_city in city or city in target_city:
                city_match = True
            elif self._fuzzy_city_match(city, target_city):
                city_match = True
            elif target_city:  # Target exists but doesn't match
                city_mismatch = True

        # Check country match
        country_match = False
        country_mismatch = False
        if country:
            if target_country in country or country in target_country:
                country_match = True
            elif self._country_code_match(country, target_country):
                country_match = True
            elif target_country:  # Target exists but doesn't match
                country_mismatch = True

        # Determine state
        if city_mismatch or country_mismatch:
            # Active contradiction
            evidence = f"structured: city='{prospect.city}', country='{prospect.country}'"
            return LocationVerification(
                state="mismatch",
                target_city=target_city,
                target_country=target_country,
                found_city=prospect.city,
                found_country=prospect.country,
                evidence_source=evidence,
                confidence=0.9,
            )

        if city_match and country_match:
            # Both match — strong verification
            evidence = f"structured: city='{prospect.city}', country='{prospect.country}'"
            return LocationVerification(
                state="verified",
                target_city=target_city,
                target_country=target_country,
                found_city=prospect.city,
                found_country=prospect.country,
                evidence_source=evidence,
                confidence=0.95,
            )

        if city_match or country_match:
            # Only one field matches — partial verification
            evidence = f"structured: city='{prospect.city}', country='{prospect.country}'"
            found_city = prospect.city if city_match else ""
            found_country = prospect.country if country_match else ""
            return LocationVerification(
                state="probably_verified",
                target_city=target_city,
                target_country=target_country,
                found_city=found_city,
                found_country=found_country,
                evidence_source=evidence,
                confidence=0.8,
            )

        return None

    # ------------------------------------------------------------------
    # Coordinate bounds validation
    # ------------------------------------------------------------------

    # Approximate bounding boxes for known cities (south, west, north, east).
    # Used to reject prospects whose coordinates are clearly outside the
    # target city.  Only cities with known OSM bbox data are included.
    _CITY_COORD_BOUNDS: dict[str, tuple[float, float, float, float]] = {
        # ── Pakistan ──
        "lahore": (31.30, 74.05, 31.65, 74.55),
        "karachi": (24.75, 66.90, 25.10, 67.30),
        "islamabad": (33.55, 72.95, 33.85, 73.30),
        # ── Australia ──
        "melbourne": (-38.00, 144.70, -37.65, 145.10),
        "sydney": (-34.00, 151.00, -33.70, 151.40),
        "brisbane": (-27.60, 152.90, -27.35, 153.20),
        "perth": (-32.10, 115.60, -31.80, 115.95),
        "adelaide": (-35.05, 138.60, -34.80, 138.90),
        # ── USA ──
        "new york": (40.50, -74.25, 40.90, -73.70),
        "los angeles": (33.70, -118.50, 34.35, -117.90),
        "chicago": (41.60, -87.90, 42.10, -87.50),
        # ── UK ──
        "london": (51.30, -0.50, 51.70, 0.30),
        "manchester": (53.40, -2.35, 53.55, -2.15),
        # ── Middle East ──
        "dubai": (25.00, 55.10, 25.40, 55.40),
    }

    # Maximum allowed distance (in degrees) from the city bbox edge.
    # A 0.5-degree buffer (~55 km) accommodates suburbs and nearby towns
    # that are legitimately part of the metropolitan area.
    _COORD_BUFFER_DEGREES: float = 0.5

    def _check_coordinate_bounds(
        self,
        prospect: RawProspect,
        target_city: str,
        target_country: str,
    ) -> LocationVerification | None:
        """Reject prospects whose coordinates are clearly outside the target city.

        Returns a ``mismatch`` verification if the prospect's lat/lon falls
        outside the known bounding box for the target city (with a generous
        buffer for suburbs).  Returns ``None`` if coordinates are missing,
        not numeric, or the city has no known bounds.
        """
        lat = prospect.metadata.get("lat")
        lon = prospect.metadata.get("lon")

        # Skip if coordinates are missing or zero (unset)
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            return None
        if lat == 0 and lon == 0:
            return None

        bounds = self._CITY_COORD_BOUNDS.get(target_city)
        if not bounds:
            # No bounds defined for this city — cannot validate
            return None

        south, west, north, east = bounds
        buf = self._COORD_BUFFER_DEGREES

        if lat < (south - buf) or lat > (north + buf):
            return LocationVerification(
                state="mismatch",
                target_city=target_city,
                target_country=target_country,
                found_city="",
                found_country="",
                evidence_source=(
                    f"coordinates outside target city: "
                    f"lat={lat:.4f} not in [{south - buf:.2f}, {north + buf:.2f}]"
                ),
                confidence=0.98,
            )

        if lon < (west - buf) or lon > (east + buf):
            return LocationVerification(
                state="mismatch",
                target_city=target_city,
                target_country=target_country,
                found_city="",
                found_country="",
                evidence_source=(
                    f"coordinates outside target city: "
                    f"lon={lon:.4f} not in [{west - buf:.2f}, {east + buf:.2f}]"
                ),
                confidence=0.98,
            )

        return None

    def _gather_text_evidence(self, prospect: RawProspect) -> str:
        """Gather all textual evidence from the prospect for location checking."""
        parts = []

        # Snippet (from search results)
        snippet = prospect.metadata.get("snippet", "")
        if snippet:
            parts.append(snippet)

        # Source URL (may contain city/country in domain or path)
        if prospect.source_url:
            parts.append(prospect.source_url)

        # Website URL
        if prospect.website:
            parts.append(prospect.website)

        # Business name (may contain city name)
        if prospect.business_name:
            parts.append(prospect.business_name)

        # Address
        if prospect.address:
            parts.append(prospect.address)

        # Business research (from LLM analysis)
        if prospect.business_research:
            parts.append(prospect.business_research[:500])

        return " ".join(parts)

    def _check_text_evidence(
        self, text: str, target_city: str, target_country: str
    ) -> Optional[LocationVerification]:
        """Check textual evidence for city/country mentions."""
        if not text:
            return None

        text_lower = text.lower()

        # Check for city mention
        city_found = False
        city_evidence = ""
        found_city = ""

        # Direct city name match
        if target_city and target_city in text_lower:
            city_found = True
            city_evidence = f"text contains '{target_city}'"
            found_city = target_city

        # Fuzzy city match
        if not city_found and target_city:
            aliases = self.CITY_ALIASES.get(target_city, [])
            for alias in aliases:
                if alias in text_lower:
                    city_found = True
                    city_evidence = f"text contains alias '{alias}'"
                    found_city = target_city
                    break

        # Country check
        country_found = False
        country_evidence = ""
        found_country = ""

        if target_country and target_country in text_lower:
            country_found = True
            country_evidence = f"text contains '{target_country}'"
            found_country = target_country

        # Country code/pattern match
        if not country_found and target_country:
            patterns = self.COUNTRY_PATTERNS.get(target_country, [])
            for pattern in patterns:
                if pattern in text_lower:
                    country_found = True
                    country_evidence = f"text contains pattern '{pattern}'"
                    found_country = target_country
                    break

        # Mismatch detection: check for OTHER cities/countries
        mismatch_city = self._detect_other_city(text_lower, target_city)
        mismatch_country = self._detect_other_country(text_lower, target_country)

        if mismatch_city or mismatch_country:
            return LocationVerification(
                state="mismatch",
                target_city=target_city,
                target_country=target_country,
                found_city=mismatch_city or "",
                found_country=mismatch_country or "",
                evidence_source=f"text mentions different location: city={mismatch_city}, country={mismatch_country}",
                confidence=0.8,
            )

        if city_found and country_found:
            return LocationVerification(
                state="verified",
                target_city=target_city,
                target_country=target_country,
                found_city=found_city,
                found_country=found_country,
                evidence_source=f"{city_evidence}; {country_evidence}",
                confidence=0.85,
            )

        if city_found:
            return LocationVerification(
                state="probably_verified",
                target_city=target_city,
                target_country=target_country,
                found_city=found_city,
                found_country="",
                evidence_source=city_evidence,
                confidence=0.7,
            )

        if country_found:
            return LocationVerification(
                state="probably_verified",
                target_city=target_city,
                target_country=target_country,
                found_city="",
                found_country=found_country,
                evidence_source=country_evidence,
                confidence=0.6,
            )

        return None

    def _combine_results(
        self,
        structured: Optional[LocationVerification],
        textual: Optional[LocationVerification],
        target_city: str,
        target_country: str,
    ) -> LocationVerification:
        """Combine structured and textual verification results.
        
        Priority: mismatch always wins (from either source).
        Both verified → verified.
        Partial match + textual confirms → promoted.
        Partial match + textual contradicts → mismatch.
        """
        # If either says mismatch, trust it
        if structured and structured.state == "mismatch":
            return structured
        if textual and textual.state == "mismatch":
            # Textual mismatch should override structured partial match
            return textual

        # If both verified → verified
        if (structured and structured.state == "verified") and (textual and textual.state == "verified"):
            return LocationVerification(
                state="verified",
                target_city=target_city,
                target_country=target_country,
                found_city=structured.found_city or textual.found_city,
                found_country=structured.found_country or textual.found_country,
                evidence_source=f"structured({structured.evidence_source}); text({textual.evidence_source})",
                confidence=min(structured.confidence, textual.confidence) + 0.05,
            )

        # Structured verified (both fields) + no textual evidence → verified
        if structured and structured.state == "verified":
            return structured

        # Structured probably_verified (one field) + textual confirms → promote to verified
        if structured and structured.state == "probably_verified":
            if textual and textual.state in ("verified", "probably_verified"):
                return LocationVerification(
                    state="verified",
                    target_city=target_city,
                    target_country=target_country,
                    found_city=structured.found_city or textual.found_city,
                    found_country=structured.found_country or textual.found_country,
                    evidence_source=f"structured({structured.evidence_source}); text({textual.evidence_source})",
                    confidence=max(structured.confidence, textual.confidence),
                )
            return structured

        # Textual verified + no structured → probably_verified
        if textual and textual.state == "verified":
            return textual

        # Textual probably_verified + no structured → probably_verified
        if textual and textual.state == "probably_verified":
            return textual

        # Both unknown → no evidence
        return LocationVerification(
            state="unknown",
            target_city=target_city,
            target_country=target_country,
            found_city="",
            found_country="",
            evidence_source="no location evidence found",
            confidence=0.0,
        )

    def _fuzzy_city_match(self, city1: str, city2: str) -> bool:
        """Fuzzy city matching using aliases and common misspellings."""
        # Check aliases
        for canonical, aliases in self.CITY_ALIASES.items():
            if canonical in city1 or city1 in canonical:
                if any(a in city2 or city2 in a for a in aliases):
                    return True
            if canonical in city2 or city2 in canonical:
                if any(a in city1 or city1 in a for a in aliases):
                    return True

        # Simple substring
        if len(city1) >= 3 and len(city2) >= 3:
            if city1 in city2 or city2 in city1:
                return True

        return False

    def _country_code_match(self, country_field: str, target_country: str) -> bool:
        """Check if a country field matches the target using common codes."""
        for canonical, patterns in self.COUNTRY_PATTERNS.items():
            if target_country in canonical or canonical in target_country:
                return any(p in country_field for p in patterns)
        return False

    def _detect_other_city(self, text: str, target_city: str) -> Optional[str]:
        """Detect if text mentions a DIFFERENT city (mismatch)."""
        for city, aliases in self.CITY_ALIASES.items():
            if city == target_city:
                continue
            for alias in aliases:
                # Use word boundary to avoid false positives
                if re.search(r'\b' + re.escape(alias) + r'\b', text):
                    return city
        return None

    def _detect_other_country(self, text: str, target_country: str) -> Optional[str]:
        """Detect if text mentions a DIFFERENT country (mismatch)."""
        for country, patterns in self.COUNTRY_PATTERNS.items():
            if country == target_country:
                continue
            # Don't flag .com as USA mismatch (too generic)
            if country == "usa":
                continue
            for pattern in patterns:
                if len(pattern) >= 3 and re.search(r'\b' + re.escape(pattern) + r'\b', text):
                    return country
        return None
