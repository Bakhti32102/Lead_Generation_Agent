"""
Category typo normalization and shared category constants.

Auto-corrects common misspellings and typos so that categories like
"Dintest" → "Dentist" or "beautiparlor" → "Beauty Parlor" don't break
query generation or tag resolution.

Also exposes shared constants used by multiple modules:
- BEAUTY_SERVICE_CATEGORIES: service-based beauty categories (not retail)
- RETAIL_PATTERNS: regex patterns to detect retail/e-commerce businesses
"""

from __future__ import annotations

import difflib
import logging
import re
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ── Service-based beauty categories ─────────────────────────────────────
# Businesses that offer beauty services (salons, spas, etc.) as opposed
# to retail stores that sell beauty products.  Used by Google Search
# retail filtering and lead verification to distinguish service
# providers from product sellers.

BEAUTY_SERVICE_CATEGORIES: Set[str] = {
    "beauty salon",
    "beauty parlor",
    "beauty parlour",
    "hair salon",
    "hairdresser",
    "hairdressers",
    "barber",
    "barber shop",
    "spa",
    "day spa",
    "makeup artist",
    "makeup studio",
    "makeup center",
    "makeup",
    "bridal studio",
    "bridal salon",
    "bridal",
    "nail salon",
    "nails",
    "institut de beaute",
    "cosmetic clinic",
    "skin care clinic",
    "skincare clinic",
    "dermatology clinic",
    "med spa",
    "medspa",
    "aesthetic clinic",
    "aesthetics clinic",
}

# ── Retail / e-commerce detection patterns ──────────────────────────────
# Regex patterns (case-insensitive) matched against business names,
# URLs, and search snippets.  Used by Google Search source and lead
# verification to filter out product sellers and e-commerce stores.

RETAIL_PATTERNS: List[re.Pattern] = [
    re.compile(r"\bsephora\b", re.IGNORECASE),
    re.compile(r"\bmac cosmetics\b", re.IGNORECASE),
    re.compile(r"\bnyx\b", re.IGNORECASE),
    re.compile(r"\bulta\b", re.IGNORECASE),
    re.compile(r"\bbeauty supply\b", re.IGNORECASE),
    re.compile(r"\bcosmetics store\b", re.IGNORECASE),
    re.compile(r"\bonline store\b", re.IGNORECASE),
    re.compile(r"\bshop online\b", re.IGNORECASE),
    re.compile(r"\bwholesale\b", re.IGNORECASE),
    re.compile(r"\bdistributor\b", re.IGNORECASE),
    re.compile(r"\bsupplier\b", re.IGNORECASE),
    re.compile(r"\bretail\b", re.IGNORECASE),
    re.compile(r"\bsupermarket\b", re.IGNORECASE),
    re.compile(r"\bsuperstore\b", re.IGNORECASE),
    re.compile(r"\bmall\b", re.IGNORECASE),
    re.compile(r"\bonline shop\b", re.IGNORECASE),
    re.compile(r"\be-commerce\b", re.IGNORECASE),
    re.compile(r"\becommerce\b", re.IGNORECASE),
    re.compile(r"\bproduct catalog\b", re.IGNORECASE),
    re.compile(r"\bproduct range\b", re.IGNORECASE),
    re.compile(r"\bfree shipping\b", re.IGNORECASE),
    re.compile(r"\badd to cart\b", re.IGNORECASE),
    re.compile(r"\bbuy online\b", re.IGNORECASE),
    re.compile(r"\bshop now\b", re.IGNORECASE),
    re.compile(r"\bwholesale supplier\b", re.IGNORECASE),
    re.compile(r"\bbulk order\b", re.IGNORECASE),
    re.compile(r"\bbeauty products online\b", re.IGNORECASE),
    re.compile(r"\bcosmetics online\b", re.IGNORECASE),
]

# ── Exact typo → canonical mappings ──────────────────────────────────────
# These are all-case-insensitive; lookups are done on .lower() keys.

_EXACT_MAP: Dict[str, str] = {
    # Dentist / Dental
    "dintest": "Dentist",
    "dennist": "Dentist",
    "dantist": "Dentist",
    "dentest": "Dentist",
    "denstist": "Dentist",
    "dentits": "Dentist",
    "dental clinic": "Dentist",
    "dental clinics": "Dentist",
    "dental": "Dentist",

    # Beauty Parlor
    "beautiparlor": "Beauty Parlor",
    "beauty parlour": "Beauty Parlor",
    "beauty parlor": "Beauty Parlor",
    "beauty parlours": "Beauty Parlor",
    "beauty parlors": "Beauty Parlor",
    "beautyparlor": "Beauty Parlor",
    "beauty saloon": "Beauty Parlor",
    "beauty salon": "Beauty Parlor",
    "beauty salons": "Beauty Parlor",
    "beuty parlor": "Beauty Parlor",
    "beauty plorar": "Beauty Parlor",

    # Cosmetics
    "commetics": "Cosmetics",
    "cosmetics": "Cosmetics",
    "cosmetic": "Cosmetics",
    "cosmetiks": "Cosmetics",
    "cosmetik": "Cosmetics",
    "beauty products": "Cosmetics",
    "beauty store": "Cosmetics",

    # Restaurants
    "resturants": "Restaurants",
    "restaurants": "Restaurants",
    "restuarants": "Restaurants",
    "restraunts": "Restaurants",
    "resturant": "Restaurants",
    "restaurant": "Restaurants",

    # Travel & Tours
    "travel & tours": "Travel & Tours",
    "travel and tours": "Travel & Tours",
    "travel & tour": "Travel & Tours",
    "travel and tour": "Travel & Tours",
    "travels & tours": "Travel & Tours",
    "travel agencies": "Travel & Tours",
    "travel agency": "Travel & Tours",
    "travel tours": "Travel & Tours",
    "tour & travel": "Travel & Tours",
    "tours and travel": "Travel & Tours",

    # Clinic
    "clinics": "Clinic",
    "clinic": "Clinic",
    "medical clinic": "Clinic",
    "medical clinics": "Clinic",

    # Hotels
    "hotels": "Hotel",
    "hotel": "Hotel",
    "hostels": "Hotel",
    "hostel": "Hotel",

    # Gym
    "gyms": "Gym",
    "gym": "Gym",
    "fitness": "Gym",
    "fitness center": "Gym",
    "fitness centre": "Gym",

    # Makeup
    "makeup": "Makeup",
    "make up": "Makeup",
    "make-up": "Makeup",
    "makeup center": "Makeup",
    "makeup studio": "Makeup",

    # Bridal
    "bridal": "Bridal",
    "bridal studio": "Bridal",
    "bridal studios": "Bridal",
    "bridal salon": "Bridal",

    # Spa
    "spa": "Spa",
    "spas": "Spa",
    "day spa": "Spa",
    "beauty spa": "Spa",

    # Hair / Barber
    "hairdresser": "Hair Salon",
    "hairdressers": "Hair Salon",
    "hair salon": "Hair Salon",
    "barber": "Hair Salon",
    "barber shop": "Hair Salon",
    "barber shops": "Hair Salon",

    # Real Estate
    "real_estate": "Real Estate",
    "real estate": "Real Estate",
    "realty": "Real Estate",
    "properties": "Real Estate",
    "property": "Real Estate",
}

# Pre-compute lower-case lookup
_LOWER_MAP: Dict[str, str] = {k.lower(): v for k, v in _EXACT_MAP.items()}

# Canonical category names (for fuzzy matching against)
_CANONICAL_NAMES: List[str] = list({
    v for v in _EXACT_MAP.values()
})


def normalize_category(category: str, threshold: float = 0.55) -> str:
    """Normalize a category string, correcting typos and fuzzy-matching.

    Args:
        category: Raw category string (e.g. "Dintest", "beautiparlor").
        threshold: Minimum similarity ratio (0–1) for fuzzy fallback.

    Returns:
        The canonical category name. Returns the original string
        (title-cased) if no match is found.
    """
    if not category or not category.strip():
        return ""

    key = category.lower().strip()

    # 1. Exact match in typo map
    if key in _LOWER_MAP:
        return _LOWER_MAP[key]

    # 2. Fuzzy match against canonical names
    matches = difflib.get_close_matches(
        key, [n.lower() for n in _CANONICAL_NAMES], n=1, cutoff=threshold
    )
    if matches:
        # Find the original (title-cased) form
        for canonical in _CANONICAL_NAMES:
            if canonical.lower() == matches[0]:
                logger.info(
                    f"Fuzzy category match: '{category}' -> '{canonical}' "
                    f"(similarity={matches[0]})"
                )
                return canonical

    # 3. No match — return title-cased original
    return category.strip().title()
