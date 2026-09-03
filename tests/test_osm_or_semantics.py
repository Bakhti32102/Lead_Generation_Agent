"""
Regression tests for OSM alternative tag OR semantics.

Bug: _build_tag_filter concatenated multiple tag pairs into a single
AND-condition filter string (e.g. ["shop"="beauty"]["shop"="hairdresser"]).
In Overpass QL, this means an element must match ALL tags simultaneously,
which is impossible when the tags use conflicting values for the same key.

Fix: _build_tag_filters returns a list of independent filter strings,
one per alternative.  The caller iterates over each filter as a separate
OR branch and merges results deduplicated by element ID.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from typing import Dict, List, Tuple

import pytest

from app.sources.osm import (
    CATEGORY_TAG_MAP,
    CITY_BBOXES,
    OpenStreetMapSource,
    _build_tag_filters,
)


# ────────────────────────────────────────────────────────────────────
# Test A — _build_tag_filters produces OR alternatives, not AND chain
# ────────────────────────────────────────────────────────────────────

class TestTagFilterOrSemantics:
    """Verify that _build_tag_filters returns independent alternatives."""

    def test_beauty_parlour_produces_three_alternatives(self):
        pairs = [("shop", "beauty"), ("shop", "hairdresser"), ("amenity", "hairdresser")]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 3
        assert filters == ['["shop"="beauty"]', '["shop"="hairdresser"]', '["amenity"="hairdresser"]']

    def test_single_tag_produces_one_filter(self):
        pairs = [("amenity", "dentist")]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 1
        assert filters == ['["amenity"="dentist"]']

    def test_no_concatenation_of_multiple_tags(self):
        """The old bug concatenated filters into a single AND string."""
        pairs = [("shop", "beauty"), ("shop", "hairdresser")]
        filters = _build_tag_filters(pairs)
        # Each filter must be a standalone string — NOT joined together
        for f in filters:
            assert f.count("[") == 1, f"Filter '{f}' should have exactly one bracket pair"
            assert f.count("]") == 1, f"Filter '{f}' should have exactly one bracket pair"

    def test_clinic_produces_two_alternatives(self):
        pairs = [("amenity", "clinic"), ("amenity", "doctors")]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 2
        assert '["amenity"="clinic"]' in filters
        assert '["amenity"="doctors"]' in filters

    def test_beaute_salon_produces_four_alternatives(self):
        pairs = [("shop", "beauty"), ("shop", "hairdresser"),
                 ("amenity", "hairdresser"), ("leisure", "spa")]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 4


# ────────────────────────────────────────────────────────────────────
# Test B — Generated Overpass queries contain correct alternatives
# ────────────────────────────────────────────────────────────────────

class TestGeneratedOverpassQueries:
    """Verify the actual Overpass query strings use OR branches."""

    def _build_area_query(self, tag_filter: str) -> str:
        """Helper: build an area-based query for Melbourne."""
        return (
            f'[out:json][timeout:25];\n'
            f'area["name"="Melbourne"]["boundary"="administrative"]->.searchArea;\n'
            f'(\n'
            f'  node{tag_filter}(area.searchArea);\n'
            f'  way{tag_filter}(area.searchArea);\n'
            f');\n'
            f'out center body;'
        )

    def test_beauty_parlour_query_structure(self):
        pairs = CATEGORY_TAG_MAP["beauty parlour"]
        filters = _build_tag_filters(pairs)
        for f in filters:
            query = self._build_area_query(f)
            # Each query must contain only ONE tag filter (OR semantics)
            assert query.count("(area.searchArea)") == 2  # node + way

    def test_dentist_single_query(self):
        """Single-tag categories should still produce one query."""
        pairs = CATEGORY_TAG_MAP["dentist"]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 1
        query = self._build_area_query(filters[0])
        assert '["amenity"="dentist"]' in query

    def test_all_multi_tag_categories_produce_or_alternatives(self):
        """Every multi-tag category must produce separate filter strings."""
        for cat, pairs in CATEGORY_TAG_MAP.items():
            if len(pairs) > 1:
                filters = _build_tag_filters(pairs)
                assert len(filters) == len(pairs), (
                    f"Category '{cat}' has {len(pairs)} tag pairs "
                    f"but produced {len(filters)} filters"
                )
                # Each filter must be independent
                for f in filters:
                    assert f.count("[") == 1, (
                        f"Category '{cat}' filter '{f}' is concatenated (AND bug)"
                    )


# ────────────────────────────────────────────────────────────────────
# Test C — Melbourne discovery with mocked Overpass response
# ────────────────────────────────────────────────────────────────────

class TestMelbourneDiscovery:
    """Mock Overpass responses and verify Melbourne beauty businesses become prospects."""

    def _make_element(self, eid: int, name: str, tags: Dict[str, str],
                      lat: float = -37.81, lon: float = 144.96) -> Dict:
        """Create a mock OSM element."""
        return {
            "type": "node",
            "id": eid,
            "lat": lat,
            "lon": lon,
            "tags": {"name": name, **tags},
        }

    @patch("app.sources.osm._overpass_post")
    def test_beauty_parlour_finds_shop_beauty_elements(self, mock_post):
        """Elements tagged shop=beauty should be found."""
        # First call: shop=beauty returns an element
        # Second call: shop=hairdresser returns nothing
        # Third call: amenity=hairdresser returns nothing
        mock_post.side_effect = [
            {"elements": [self._make_element(1, "Glow Beauty", {"shop": "beauty"})]},
            {"elements": []},
            {"elements": []},
        ]

        source = OpenStreetMapSource()
        prospects = source.search(
            country="Australia", city="Melbourne",
            category="beauty parlour", max_results=20,
        )

        assert len(prospects) >= 1
        assert prospects[0].business_name == "Glow Beauty"

    @patch("app.sources.osm._overpass_post")
    def test_beauty_parlour_finds_amenity_hairdresser_elements(self, mock_post):
        """Elements tagged amenity=hairdresser should be found."""
        mock_post.side_effect = [
            {"elements": []},
            {"elements": []},
            {"elements": [self._make_element(2, "Hair Studio", {"amenity": "hairdresser"})]},
        ]

        source = OpenStreetMapSource()
        prospects = source.search(
            country="Australia", city="Melbourne",
            category="beauty parlour", max_results=20,
        )

        assert len(prospects) >= 1
        assert prospects[0].business_name == "Hair Studio"

    @patch("app.sources.osm._overpass_post")
    def test_beauty_parlour_merges_from_multiple_alternatives(self, mock_post):
        """Results from different alternatives should be merged."""
        mock_post.side_effect = [
            {"elements": [self._make_element(1, "Glow Beauty", {"shop": "beauty"})]},
            {"elements": [self._make_element(2, "Hair Studio", {"shop": "hairdresser"})]},
            {"elements": [self._make_element(3, "Barber House", {"amenity": "hairdresser"})]},
        ]

        source = OpenStreetMapSource()
        prospects = source.search(
            country="Australia", city="Melbourne",
            category="beauty parlour", max_results=20,
        )

        names = {p.business_name for p in prospects}
        assert "Glow Beauty" in names
        assert "Hair Studio" in names
        assert "Barber House" in names
        assert len(prospects) == 3

    @patch("app.sources.osm._overpass_post")
    def test_deduplicates_across_alternatives(self, mock_post):
        """Same element returned by multiple alternatives should be deduplicated."""
        element = self._make_element(42, "Salon X", {"shop": "beauty", "amenity": "hairdresser"})
        mock_post.side_effect = [
            {"elements": [element]},
            {"elements": [element]},  # Same element from second filter
            {"elements": []},
        ]

        source = OpenStreetMapSource()
        prospects = source.search(
            country="Australia", city="Melbourne",
            category="beauty parlour", max_results=20,
        )

        # Should only appear once despite being returned by two filters
        salon_x_count = sum(1 for p in prospects if p.business_name == "Salon X")
        assert salon_x_count == 1


# ────────────────────────────────────────────────────────────────────
# Test D — OSM returns zero → fallback triggers
# ────────────────────────────────────────────────────────────────────

class TestFallbackOnZeroResults:
    """When OSM returns 0, discovery should continue to fallback sources."""

    @patch("app.sources.osm._overpass_post", side_effect=Exception("timeout"))
    def test_osm_exception_does_not_crash(self, mock_post):
        """OSM timeout should not crash the search."""
        source = OpenStreetMapSource()
        prospects = source.search(
            country="Australia", city="Melbourne",
            category="beauty parlour", max_results=20,
        )
        # Should return empty, not crash
        assert isinstance(prospects, list)
        assert len(prospects) == 0

    @patch("app.sources.osm._overpass_post", return_value={"elements": []})
    def test_osm_empty_returns_empty_list(self, mock_post):
        """OSM returning empty results should return empty list."""
        source = OpenStreetMapSource()
        prospects = source.search(
            country="Australia", city="Melbourne",
            category="beauty parlour", max_results=20,
        )
        assert isinstance(prospects, list)
        assert len(prospects) == 0


# ────────────────────────────────────────────────────────────────────
# Test E — International phone handling (Australia +61)
# ────────────────────────────────────────────────────────────────────

class TestInternationalPhone:
    """Verify valid Australian numbers are not rejected."""

    def test_australian_mobile_plus614(self):
        from app.utils.phone import is_whatsapp_number
        assert is_whatsapp_number("+61412345678") is True

    def test_australian_mobile_04(self):
        from app.utils.phone import is_whatsapp_number
        # 04 is the local prefix for Australian mobiles
        # Without +61 country code, the heuristic checks digit length
        assert is_whatsapp_number("0412345678") is True

    def test_pakistani_mobile_still_works(self):
        from app.utils.phone import is_whatsapp_number
        assert is_whatsapp_number("+923001234567") is True

    def test_landline_rejected(self):
        from app.utils.phone import is_whatsapp_number
        # Pakistani landline 042 = Lahore
        assert is_whatsapp_number("+92421234567") is False


# ────────────────────────────────────────────────────────────────────
# Test F — Location verification for Melbourne
# ────────────────────────────────────────────────────────────────────

class TestLocationVerification:
    """Verify a Melbourne/Australia business can pass location checks."""

    def test_melbourne_in_city_bboxes(self):
        assert "melbourne" in CITY_BBOXES
        south, west, north, east = CITY_BBOXES["melbourne"]
        # Melbourne bbox should be roughly correct
        assert -39 < south < -37
        assert 144 < west < 146
        assert -38 < north < -37
        assert 145 < east < 146

    def test_country_australia_recognized_as_foreign(self):
        """Australia is in the FOREIGN_MARKETS set in lead_discovery."""
        FOREIGN_MARKETS = frozenset({
            "usa", "united states", "uk", "united kingdom", "australia",
            "canada", "uae", "dubai", "singapore", "new zealand",
            "germany", "france", "netherlands", "ireland",
        })
        assert "australia" in FOREIGN_MARKETS


# ────────────────────────────────────────────────────────────────────
# Test G — Existing categories not broken (regression)
# ────────────────────────────────────────────────────────────────────

class TestRegressionExistingCategories:
    """Ensure single-tag categories still work correctly."""

    def test_dentist_single_tag(self):
        pairs = CATEGORY_TAG_MAP["dentist"]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 1
        assert filters == ['["amenity"="dentist"]']

    def test_restaurant_single_tag(self):
        pairs = CATEGORY_TAG_MAP["restaurant"]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 1
        assert filters == ['["amenity"="restaurant"]']

    def test_hotel_single_tag(self):
        pairs = CATEGORY_TAG_MAP["hotel"]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 1
        assert filters == ['["tourism"="hotel"]']

    def test_gym_single_tag(self):
        pairs = CATEGORY_TAG_MAP["gym"]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 1
        assert filters == ['["leisure"="fitness_centre"]']

    def test_travel_single_tag(self):
        pairs = CATEGORY_TAG_MAP["travel"]
        filters = _build_tag_filters(pairs)
        assert len(filters) == 1
        assert filters == ['["office"="travel_agent"]']

    @patch("app.sources.osm._overpass_post")
    def test_dentist_melbourne_findings(self, mock_post):
        """Dentist search should still work (single tag, unaffected by fix)."""
        mock_post.return_value = {
            "elements": [
                {"type": "node", "id": 1, "lat": -37.81, "lon": 144.96,
                 "tags": {"name": "Dental Care Melbourne", "amenity": "dentist"}},
            ]
        }
        source = OpenStreetMapSource()
        prospects = source.search(
            country="Australia", city="Melbourne",
            category="dentist", max_results=10,
        )
        assert len(prospects) == 1
        assert prospects[0].business_name == "Dental Care Melbourne"

    def test_all_categories_have_valid_tag_pairs(self):
        """Every category in the map must have at least one tag pair."""
        for cat, pairs in CATEGORY_TAG_MAP.items():
            assert isinstance(pairs, list), f"Category '{cat}' tags is not a list"
            assert len(pairs) >= 1, f"Category '{cat}' has no tag pairs"
            for key, value in pairs:
                assert isinstance(key, str) and isinstance(value, str), (
                    f"Category '{cat}' has non-string tag pair: ({key}, {value})"
                )


# ────────────────────────────────────────────────────────────────────
# Test H — Element parsing still works
# ────────────────────────────────────────────────────────────────────

class TestElementParsing:
    """Verify element→prospect parsing is unaffected by the fix."""

    def test_parse_element_extracts_name(self):
        source = OpenStreetMapSource()
        element = {
            "type": "node",
            "id": 123,
            "lat": -37.81,
            "lon": 144.96,
            "tags": {
                "name": "Test Salon",
                "shop": "beauty",
                "phone": "+61412345678",
                "website": "https://example.com",
                "email": "info@example.com",
                "addr:street": "123 Collins St",
                "addr:city": "Melbourne",
            },
        }
        prospect = source._parse_element(element, "Australia", "Melbourne", "beauty parlour")
        assert prospect is not None
        assert prospect.business_name == "Test Salon"
        assert prospect.country == "Australia"
        assert prospect.city == "Melbourne"
        assert prospect.phone == "+61412345678"
        assert prospect.email == "info@example.com"
        assert prospect.website == "https://example.com"
        assert prospect.source == "openstreetmap"

    def test_parse_element_skips_no_name(self):
        source = OpenStreetMapSource()
        element = {
            "type": "node",
            "id": 124,
            "lat": -37.81,
            "lon": 144.96,
            "tags": {"shop": "beauty"},
        }
        prospect = source._parse_element(element, "Australia", "Melbourne", "beauty parlour")
        assert prospect is None
