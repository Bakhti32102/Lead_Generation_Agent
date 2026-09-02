"""
Business Name Validator.
Cleans and validates business names extracted from search results.
Rejects social media post text, URLs, extremely long scraped content,
and other non-business-name data.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Maximum allowed business name length
MAX_NAME_LENGTH = 100

# Minimum meaningful name length
MIN_NAME_LENGTH = 2

# Patterns that indicate non-business-name content
SOCIAL_MEDIA_PATTERNS = [
    r'\d+[KkMm]?\s*(views?|reactions?|likes?|comments?|shares?)',
    r'^(welcome|follow|subscribe|like|share|comment)',
    r'#\w+',  # hashtags
    r'@\w+',  # mentions
    r'https?://',  # URLs
    r'www\.',
]

# Patterns indicating scraped content / descriptions
DESCRIPTION_PATTERNS = [
    r'(say goodbye|achieve|transform|discover|experience)',
    r'(cutting[- ]edge|state[- ]of[- ]the[- ]art|innovative|advanced)',
    r'(click here|learn more|find out|read more)',
    r'(schedule a consultation|book now|contact us)',
    r'(for further information|for more details)',
]

# Common business name suffixes to preserve (not remove)
VALID_SUFFIXES = [
    'clinic', 'hospital', 'center', 'centre', 'lab', 'studio',
    'salon', 'spa', 'gym', 'restaurant', 'cafe', 'pharmacy',
    'dental', 'medical', 'care', 'health', 'beauty', 'wellness',
]


def validate_business_name(name: str) -> tuple[str, str]:
    """
    Validate and clean a business name.
    
    Returns:
        (cleaned_name, reason) where reason is empty if valid,
        or a description of why the name was rejected/cleaned.
    """
    if not name:
        return "", "empty_name"
    
    original = name.strip()
    name = original
    
    # 0. Strip leading @mention (social media handle)
    if name.startswith('@'):
        # Remove @handle and keep the rest
        parts = name.split(None, 1)
        if len(parts) > 1:
            name = parts[1].strip()
        else:
            return "", "mention_only"

    # 1. Check for empty/whitespace-only
    if len(name) < MIN_NAME_LENGTH:
        return "", "too_short"
    
    # 2. Check for URL-only names
    if re.match(r'^https?://', name, re.IGNORECASE):
        return "", "url_as_name"
    
    if re.match(r'^www\.', name, re.IGNORECASE):
        return "", "url_as_name"
    
    # 3. Check for social media post patterns (high-confidence rejection)
    for pattern in SOCIAL_MEDIA_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            # Try to extract the actual business name from the text
            extracted = _extract_business_from_social_text(name)
            if extracted and len(extracted) >= MIN_NAME_LENGTH:
                logger.debug(f"Extracted business name from social text: '{extracted}' (was: '{name[:50]}...')")
                return extracted, "extracted_from_social_text"
            return "", "social_media_text"
    
    # 4. Check for description/promotional text patterns
    description_score = 0
    for pattern in DESCRIPTION_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            description_score += 1
    
    if description_score >= 2:
        # Multiple description patterns = likely scraped content
        extracted = _extract_business_from_description(name)
        if extracted and len(extracted) >= MIN_NAME_LENGTH:
            logger.debug(f"Extracted business name from description: '{extracted}'")
            return extracted, "extracted_from_description"
        return "", "description_text"
    
    # 5. Check for HTML/noisy text
    if '<' in name and '>' in name:
        # Strip HTML tags and re-validate
        cleaned = re.sub(r'<[^>]+>', ' ', name).strip()
        if len(cleaned) >= MIN_NAME_LENGTH:
            name = cleaned
        else:
            return "", "html_content"
    
    # 6. Check for extremely long names (likely scraped content)
    if len(name) > MAX_NAME_LENGTH:
        # Try to extract a reasonable business name
        extracted = _extract_business_from_long_text(name)
        if extracted and len(extracted) >= MIN_NAME_LENGTH:
            logger.debug(f"Extracted business name from long text: '{extracted}' (was {len(original)} chars)")
            return extracted, "extracted_from_long_text"
        # Last resort: truncate intelligently
        truncated = _intelligent_truncate(name)
        if truncated:
            return truncated, "truncated_from_long_text"
        return "", "too_long_unextractable"
    
    # 7. Check for non-business patterns (numbers-heavy, random strings)
    if _is_random_string(name):
        return "", "random_string"
    
    # 8. Clean up common issues
    name = _final_cleanup(name)
    
    if len(name) < MIN_NAME_LENGTH:
        return "", "cleanup_resulted_in_empty"
    
    return name, ""


def _extract_business_from_social_text(text: str) -> Optional[str]:
    """Try to extract a business name from social media post text."""
    # Look for patterns like "Business Name - Category" or "Business Name | Location"
    separators = [' - ', ' | ', ' @ ', ': ', ' -- ']
    for sep in separators:
        if sep in text:
            candidate = text.split(sep)[0].strip()
            if _looks_like_business_name(candidate):
                return candidate[:MAX_NAME_LENGTH]
    
    # Look for text before first sentence boundary
    for boundary in ['. ', '! ', '? ', '\n']:
        if boundary in text:
            candidate = text.split(boundary)[0].strip()
            if _looks_like_business_name(candidate):
                return candidate[:MAX_NAME_LENGTH]
    
    # Try first N words if they look like a name
    words = text.split()[:6]
    candidate = ' '.join(words)
    if _looks_like_business_name(candidate):
        return candidate[:MAX_NAME_LENGTH]
    
    return None


def _extract_business_from_description(text: str) -> Optional[str]:
    """Try to extract a business name from descriptive text."""
    # Similar to social text extraction
    separators = [' - ', ' | ', ': ']
    for sep in separators:
        if sep in text:
            candidate = text.split(sep)[0].strip()
            if _looks_like_business_name(candidate):
                return candidate[:MAX_NAME_LENGTH]
    
    # First sentence might be the name
    match = re.match(r'^([A-Z][^.!?\n]{2,60})', text)
    if match:
        candidate = match.group(1).strip()
        if _looks_like_business_name(candidate):
            return candidate[:MAX_NAME_LENGTH]
    
    return None


def _extract_business_from_long_text(text: str) -> Optional[str]:
    """Extract business name from very long scraped text."""
    # Try structured patterns first
    separators = [' - ', ' | ', ': ', ' -- ', ' /// ']
    for sep in separators:
        if sep in text:
            candidate = text.split(sep)[0].strip()
            if _looks_like_business_name(candidate):
                return candidate[:MAX_NAME_LENGTH]
    
    # Try first meaningful phrase
    match = re.match(r'^([A-Z][A-Za-z0-9\s&\'-]{2,80})', text)
    if match:
        candidate = match.group(1).strip()
        if _looks_like_business_name(candidate):
            return candidate[:MAX_NAME_LENGTH]
    
    return None


def _looks_like_business_name(text: str) -> bool:
    """Check if text looks like a plausible business name."""
    if not text or len(text) < MIN_NAME_LENGTH:
        return False
    
    # Reject if too many special characters
    special_ratio = sum(1 for c in text if not c.isalnum() and c not in ' &\'-.,') / len(text)
    if special_ratio > 0.3:
        return False
    
    # Reject if mostly numbers
    digit_ratio = sum(1 for c in text if c.isdigit()) / len(text)
    if digit_ratio > 0.5:
        return False
    
    # Reject if contains social media patterns
    for pattern in SOCIAL_MEDIA_PATTERNS[:3]:  # views, reactions, likes
        if re.search(pattern, text, re.IGNORECASE):
            return False
    
    # Reject if too many description words
    desc_words = ['the', 'our', 'your', 'with', 'for', 'and', 'or', 'but', 'this', 'that']
    words = text.lower().split()
    if len(words) > 3:
        desc_count = sum(1 for w in words if w in desc_words)
        if desc_count / len(words) > 0.4:
            return False
    
    return True


def _intelligent_truncate(text: str) -> Optional[str]:
    """Intelligently truncate long text to extract a name."""
    # Try to find a reasonable break point
    for length in [80, 60, 40]:
        candidate = text[:length].strip()
        # Find last space to avoid cutting words
        last_space = candidate.rfind(' ')
        if last_space > 20:
            candidate = candidate[:last_space]
        if _looks_like_business_name(candidate):
            return candidate
    return None


def _is_random_string(text: str) -> bool:
    """Check if text is a random/meaningless string."""
    # Very short strings with mixed case and numbers
    if len(text) < 5:
        return False
    
    # Check for random hash-like patterns
    if re.match(r'^[a-f0-9]{8,}$', text.lower()):
        return True
    
    # Check for UUID-like patterns
    if re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-', text.lower()):
        return True
    
    return False


def _final_cleanup(name: str) -> str:
    """Final cleanup of business name."""
    # Remove leading/trailing punctuation
    name = name.strip('.,;:!?-|/\\')
    
    # Remove multiple spaces
    name = re.sub(r'\s+', ' ', name)
    
    # Remove leading/trailing quotes
    name = name.strip('\'"')
    
    # Capitalize first letter of each word if all lowercase
    if name.islower() and len(name) > 3:
        name = name.title()
    
    return name.strip()
