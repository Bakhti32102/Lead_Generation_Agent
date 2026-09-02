"""
Business Name Validator Tests.
Comprehensive tests for name validation, cleaning, and rejection.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.business_name_validator import validate_business_name


class TestNormalBusinessNames:
    """Test that normal business names pass validation."""

    def test_simple_name(self):
        cleaned, reason = validate_business_name("Smile Dental Clinic")
        assert cleaned == "Smile Dental Clinic"
        assert reason == ""

    def test_name_with_ampersand(self):
        cleaned, reason = validate_business_name("Smith & Jones Dental")
        assert cleaned == "Smith & Jones Dental"
        assert reason == ""

    def test_name_with_hyphen(self):
        cleaned, reason = validate_business_name("City-Wide Dental Care")
        assert cleaned == "City-Wide Dental Care"
        assert reason == ""

    def test_name_with_numbers(self):
        cleaned, reason = validate_business_name("Dental 360 Clinic")
        assert cleaned == "Dental 360 Clinic"
        assert reason == ""

    def test_name_with_location(self):
        cleaned, reason = validate_business_name("Ghurki Trust Teaching Hospital")
        assert cleaned == "Ghurki Trust Teaching Hospital"
        assert reason == ""

    def test_name_with_abbreviation(self):
        cleaned, reason = validate_business_name("Dr. Smith Dental")
        assert cleaned == "Dr. Smith Dental"
        assert reason == ""

    def test_name_with_apostrophe(self):
        cleaned, reason = validate_business_name("Al-Fazal's Clinic")
        assert "Al-Fazal" in cleaned
        assert reason == ""


class TestLongLegitimateNames:
    """Test that long but legitimate names are handled correctly."""

    def test_long_but_valid(self):
        name = "Best Dental Clinic for Overseas Pakistanis in Lahore"
        cleaned, reason = validate_business_name(name)
        assert len(cleaned) <= 100
        assert "Dental" in cleaned

    def test_very_long_valid_name(self):
        name = "Emergency Dental Treatments | Root Canal, Extractions & Deep Scaling"
        cleaned, reason = validate_business_name(name)
        # Should extract the business part
        assert len(cleaned) <= 100
        assert cleaned  # Not empty


class TestSocialMediaText:
    """Test that social media post text is rejected or cleaned."""

    def test_views_reactions_text(self):
        text = "4.3K views \u00b7 112 reactions | Welcome to our state-of-the-art dental clinic"
        cleaned, reason = validate_business_name(text)
        # Should either extract a name or reject
        if cleaned:
            assert len(cleaned) <= 100
            assert "views" not in cleaned.lower()
            assert "reactions" not in cleaned.lower()
        else:
            assert reason in ("social_media_text", "description_text", "extracted_from_social_text")

    def test_hashtag_text(self):
        text = "#DentalInnovation #SmileTransformation Dental Clinic"
        cleaned, reason = validate_business_name(text)
        if cleaned:
            assert "#" not in cleaned

    def test_mention_text(self):
        text = "@smiledental Best dental clinic in Lahore"
        cleaned, reason = validate_business_name(text)
        if cleaned:
            assert "@" not in cleaned

    def test_social_media_post_long(self):
        text = ("Welcome to our state-of-the-art dental clinic, where innovation meets excellence! "
                "Our latest services are designed to provide you with the most advanced dental care. "
                "Schedule a consultation with us today!")
        cleaned, reason = validate_business_name(text)
        # Should be rejected or significantly cleaned
        if cleaned:
            assert len(cleaned) <= 100
            assert "schedule" not in cleaned.lower()


class TestUrlAsName:
    """Test that URLs used as names are rejected."""

    def test_http_url(self):
        cleaned, reason = validate_business_name("https://example.com/dental")
        assert cleaned == ""
        assert reason == "url_as_name"

    def test_www_url(self):
        cleaned, reason = validate_business_name("www.smiledental.pk")
        assert cleaned == ""
        assert reason == "url_as_name"

    def test_just_domain(self):
        cleaned, reason = validate_business_name("smiledental.pk")
        # Domain-only names should still pass (could be a business name)
        assert cleaned  # Should not be empty


class TestEmptyAndInvalidNames:
    """Test empty, whitespace, and invalid names."""

    def test_empty_string(self):
        cleaned, reason = validate_business_name("")
        assert cleaned == ""
        assert reason == "empty_name"

    def test_whitespace_only(self):
        cleaned, reason = validate_business_name("   ")
        assert cleaned == ""
        assert reason == "too_short"

    def test_single_char(self):
        cleaned, reason = validate_business_name("A")
        assert cleaned == ""
        assert reason == "too_short"

    def test_html_content(self):
        cleaned, reason = validate_business_name("<div>Dental Clinic</div>")
        if cleaned:
            assert "<" not in cleaned
            assert ">" not in cleaned


class TestLongScrapedContent:
    """Test that extremely long scraped content is handled."""

    def test_very_long_description(self):
        text = ("Dental Clinic in Lahore offering comprehensive dental services including "
                "root canal treatment, teeth whitening, orthodontic braces, dental implants, "
                "and cosmetic dentistry. Our experienced team of dentists provides personalized "
                "care using the latest technology. We accept all major insurance plans. "
                "Open Monday to Saturday, 9 AM to 6 PM. Call now for appointment.")
        cleaned, reason = validate_business_name(text)
        if cleaned:
            assert len(cleaned) <= 100
            # Should extract something reasonable
        else:
            assert reason in ("description_text", "too_long_unextractable", "extracted_from_long_text")

    def test_scraped_product_description(self):
        text = ("Cutting-edge implant fixation services. Aligners: Achieve the smile of your "
                "dreams discreetly and comfortably with our innovative aligner treatments.")
        cleaned, reason = validate_business_name(text)
        if cleaned:
            assert len(cleaned) <= 100


class TestRandomStrings:
    """Test that random/meaningless strings are rejected."""

    def test_uuid_like(self):
        cleaned, reason = validate_business_name("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
        assert cleaned == ""
        assert reason == "random_string"

    def test_hex_string(self):
        cleaned, reason = validate_business_name("abcdef123456")
        assert cleaned == ""
        assert reason == "random_string"


class TestBusinessNameValidatorIntegration:
    """Test the validator integration with RawProspect."""

    def test_prospect_validate_name_valid(self):
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Smile Dental Clinic")
        assert p.validate_name() is True
        assert p.business_name == "Smile Dental Clinic"

    def test_prospect_validate_name_empty(self):
        from app.sources.base import RawProspect
        p = RawProspect(business_name="")
        assert p.validate_name() is False
        assert "name_rejection_reason" in p.metadata

    def test_prospect_validate_name_social_media(self):
        from app.sources.base import RawProspect
        p = RawProspect(business_name="4.3K views \u00b7 112 reactions | Welcome to our clinic")
        result = p.validate_name()
        # Should either clean or reject
        if result:
            assert len(p.business_name) <= 100
            assert "views" not in p.business_name.lower()

    def test_prospect_validate_name_long(self):
        from app.sources.base import RawProspect
        p = RawProspect(business_name="Emergency Dental Treatments | Root Canal, Extractions & Deep Scaling")
        result = p.validate_name()
        if result:
            assert len(p.business_name) <= 100
