"""
Phone number utilities.
Detects whether a phone number is a mobile (WhatsApp-capable) number
versus a landline that cannot receive WhatsApp messages.
"""

from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Country-specific mobile prefixes
# ---------------------------------------------------------------------------
# Maps country code (digits) to lists of mobile prefixes (after country code).
# Sources: ITU numbering plans, common carrier ranges.

_MOBILE_PREFIXES: dict[str, list[str]] = {
    # Pakistan: +92 3XX (11 digits total, 30x-39x are mobile)
    "92": ["30", "31", "32", "33", "34", "35", "36", "37", "38", "39"],
    # UAE: +971 5X (10 digits total, 50-59 are mobile)
    "971": ["50", "51", "52", "53", "54", "55", "56", "57", "58", "59"],
    # UK: +44 7XXX (12 digits total, 7 is mobile)
    "44": ["7"],
    # India: +91 9XXXX / 8XXXX / 7XXXX (10 digits, mobile)
    "91": ["9", "8", "7"],
    # USA/Canada: +1 (11 digits) — most numbers are mobile-capable
    "1": [],  # Treated as mobile by default (no clean landline/mobile split)
    # Saudi Arabia: +966 5X (mobile)
    "966": ["5"],
    # Qatar: +974 (mobile prefixes)
    "974": ["3", "5", "6", "7"],
    # Bahrain: +973 (mobile prefixes)
    "973": ["3", "6"],
    # Kuwait: +965 (mobile prefixes)
    "965": ["5", "6", "7", "8", "9"],
    # Oman: +968 (mobile prefixes)
    "968": ["9"],
    # Jordan: +962 (mobile prefixes)
    "962": ["7", "8"],
    # Egypt: +20 (mobile prefixes)
    "20": ["10", "11", "12", "15"],
    # Turkey: +90 (mobile)
    "90": ["5"],
    # Germany: +49 (mobile)
    "49": ["15", "16", "17"],
    # France: +33 (mobile)
    "33": ["6", "7"],
    # Australia: +61 (mobile)
    "61": ["4", "5"],
    # Singapore: +65
    "65": [],  # Most numbers are mobile
    # Malaysia: +60 (mobile)
    "60": ["1"],
    # Nigeria: +234 (mobile)
    "234": ["70", "80", "81", "90", "91"],
    # South Africa: +27 (mobile)
    "27": ["6", "7", "8"],
    # Kenya: +254 (mobile)
    "254": ["7"],
}

# Landline area codes that should NOT be treated as WhatsApp-capable.
# These are common landline prefixes by country.
_LANDLINE_PREFIXES: dict[str, list[str]] = {
    # Pakistan: 0XX landline codes (e.g., 042 = Lahore, 021 = Karachi)
    "92": ["02", "04", "05", "06"],
    # UK: 01X, 02X are landlines
    "44": ["1", "2"],
    # USA/Canada: area codes don't cleanly split mobile/landline
    # Germany: landlines start with 0
    "49": ["0"],
    # France: landlines start with 01-05
    "33": ["1", "2", "3", "4", "5"],
}


def _strip_country_code(phone: str) -> tuple[str, str]:
    """
    Strip the international dialing prefix and country code from a phone number.

    Returns (country_code_digits, national_number).
    Example: "+923001234567" → ("92", "3001234567")
    """
    cleaned = re.sub(r"[^\d+]", "", phone)

    # Handle + prefix
    if cleaned.startswith("+"):
        digits = cleaned[1:]
    elif cleaned.startswith("00"):
        digits = cleaned[2:]
    else:
        # No explicit country code — return as-is
        return ("", cleaned)

    # Try to match known country codes (longest first)
    sorted_codes = sorted(_MOBILE_PREFIXES.keys(), key=len, reverse=True)
    for code in sorted_codes:
        if digits.startswith(code):
            national = digits[len(code):]
            return (code, national)

    return ("", digits)


def is_whatsapp_number(phone: str) -> bool:
    """
    Heuristic check: does this phone number look like a WhatsApp-capable
    mobile number (not a landline)?

    Returns True if the number appears to be a mobile/WhatsApp number.
    Returns False for landlines, invalid numbers, or unknown formats.
    """
    if not phone or not phone.strip():
        return False

    phone = phone.strip()

    # Reject obviously invalid numbers
    digits_only = re.sub(r"[^\d]", "", phone)
    if len(digits_only) < 7:
        return False

    country_code, national = _strip_country_code(phone)

    if not country_code:
        # No country code detected — use digit-length heuristic
        # 7-8 digits: could be local landline
        # 10-11 digits: likely mobile with country code embedded
        if len(digits_only) >= 10:
            return True  # Likely mobile
        return False  # Too short to be confident

    # Check known mobile prefixes
    mobile_prefixes = _MOBILE_PREFIXES.get(country_code, [])

    # Special case: USA/Canada — treat all as mobile (no clean split)
    if country_code == "1":
        return len(national) == 10

    # Special case: Singapore — most numbers are mobile
    if country_code == "65":
        return len(national) == 8

    if not mobile_prefixes:
        # Unknown country — fall back to digit-length heuristic
        return len(national) >= 8

    # Check if national number starts with any mobile prefix
    for prefix in mobile_prefixes:
        if national.startswith(prefix):
            return True

    return False


def has_valid_email(email: str) -> bool:
    """Validate email format."""
    if not email or not email.strip():
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email.strip()))


def has_reachable_channel(phone: str, email: str) -> bool:
    """
    Check if a prospect has at least one reachable outreach channel:
    - Valid email address, OR
    - WhatsApp-capable mobile number
    """
    if has_valid_email(email):
        return True
    if is_whatsapp_number(phone):
        return True
    return False
