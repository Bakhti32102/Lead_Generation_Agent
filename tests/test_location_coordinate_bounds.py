"""
Regression tests for coordinate-based location verification.

Bug: LocationVerifier trusted the OSM source's city/country fields
(which come from the campaign input, not the element's actual location).
This allowed Melbourne, Florida prospects to pass location verification
for a Melbourne, Australia campaign because both fields matched.

Fix: Added _check_coordinate_bounds() as the first verification step,
comparing the prospect's actual lat/lon against the known bounding box
for the target city.  Prospects outside the bbox are rejected as
mismatch with high confidence.
"""

from __future__ import annotations

import pytest

from app.agents.location_verifier import LocationVerifier
from app.sources.base import RawProspect


def _make_prospect(
    name: str,
    lat: float,
    lon: float,
    city: str = "Melbourne",
    country: str = "Australia",
    phone: str = "",
    email: str = "",
    source: str = "openstreetmap",
) -> RawProspect:
    """Create a test prospect with coordinates."""
    return RawProspect(
        business_name=name,
        city=city,
        country=country,
        phone=phone,
        email=email,
        source=source,
        metadata={"lat": lat, "lon": lon},
    )


class TestMelbourneAustraliaVsFlorida:
    """Melbourne, AU must pass; Melbourne, FL must be rejected."""

    def test_melbourne_au_passes(self):
        """A business at Melbourne, AU coordinates passes location verification."""
        p = _make_prospect("Hello Day", lat=-37.813, lon=144.968)
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state in ("verified", "probably_verified"), (
            f"Expected verified, got {result.state}: {result.evidence_source}"
        )

    def test_melbourne_fl_rejected(self):
        """A business at Melbourne, FL coordinates is rejected."""
        p = _make_prospect("Forever Nails", lat=28.137, lon=-80.596)
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state == "mismatch", (
            f"Expected mismatch, got {result.state}: {result.evidence_source}"
        )

    def test_melbourne_fl_different_business_rejected(self):
        """Another Melbourne, FL business is also rejected."""
        p = _make_prospect("LA Tan", lat=28.036, lon=-80.641)
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state == "mismatch"

    def test_melbourne_fl_nail_salon_rejected(self):
        """C-D Nails in Melbourne, FL is rejected."""
        p = _make_prospect("C-D Nails", lat=28.079, lon=-80.623)
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state == "mismatch"

    def test_suburb_of_melbourne_au_passes(self):
        """A suburb slightly outside the core bbox but within buffer passes."""
        # ~30km south of Melbourne CBD — still in the metro area
        p = _make_prospect("Frankston Hair", lat=-38.14, lon=145.12)
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state in ("verified", "probably_verified")

    def test_completely_different_city_rejected(self):
        """A business in Sydney is rejected for a Melbourne campaign."""
        p = _make_prospect("Sydney Spa", lat=-33.87, lon=151.21, city="Melbourne", country="Australia")
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state == "mismatch"


class TestCoordinateBoundsChecking:
    """Test the coordinate bounds mechanism directly."""

    def test_missing_coordinates_skips_check(self):
        """Prospect with no coordinates falls through to other checks."""
        p = _make_prospect("Unknown Location", lat=0, lon=0)
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        # Should not be a coordinate mismatch — falls through to structured check
        assert result.evidence_source != "coordinates outside target city"

    def test_zero_coordinates_skips_check(self):
        """Default (0, 0) coordinates are treated as unset."""
        p = _make_prospect("Default Coords", lat=0, lon=0)
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert "coordinates outside" not in result.evidence_source

    def test_city_without_bounds_skips_check(self):
        """City not in _CITY_COORD_BOUNDS skips coordinate validation."""
        p = _make_prospect("Unknown City", lat=0, lon=0, city="Springfield")
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Springfield", target_country="USA")
        # Should not crash — just skips coordinate check
        assert result.state in ("verified", "probably_verified", "unknown")

    def test_lahore_pakistan_passes(self):
        """Lahore, Pakistan coordinates pass."""
        p = _make_prospect("Lahore Dental", lat=31.55, lon=74.35, city="Lahore", country="Pakistan")
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Lahore", target_country="Pakistan")
        assert result.state in ("verified", "probably_verified")

    def test_lahore_from_usa_rejected(self):
        """A business with Lahore coordinates but USA campaign is rejected."""
        p = _make_prospect("Fake Lahore", lat=31.55, lon=74.35, city="Lahore", country="Pakistan")
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Lahore", target_country="USA")
        # Country mismatch should reject
        assert result.state == "mismatch"


class TestRegressionExistingBehavior:
    """Ensure existing verification logic is not broken."""

    def test_osm_source_inherits_city_country(self):
        """OSM source should inject target city/country when prospect fields are empty."""
        p = RawProspect(
            business_name="Test",
            city="",
            country="",
            source="openstreetmap",
            metadata={"lat": -37.81, "lon": 144.96},
        )
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert p.city == "Melbourne"
        assert p.country == "Australia"
        assert result.state in ("verified", "probably_verified")

    def test_structured_city_country_match(self):
        """Explicit city+country match on prospect fields still works."""
        p = _make_prospect("Direct Match", lat=-37.81, lon=144.96,
                           city="Melbourne", country="Australia")
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state == "verified"

    def test_country_mismatch_rejected(self):
        """Country mismatch is still rejected."""
        p = _make_prospect("Wrong Country", lat=-37.81, lon=144.96,
                           city="Melbourne", country="USA")
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        assert result.state == "mismatch"

    def test_unknown_city_with_coords_in_bounds(self):
        """Unknown city with coords in Melbourne bounds passes."""
        p = _make_prospect("Suburb Shop", lat=-37.81, lon=144.96,
                           city="", country="")
        verifier = LocationVerifier()
        result = verifier.verify(p, target_city="Melbourne", target_country="Australia")
        # Coordinates are in bounds, no mismatch from coords
        assert result.state != "mismatch" or "coordinates" not in result.evidence_source
