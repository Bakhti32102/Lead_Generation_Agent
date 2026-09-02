"""
Tests for retail store and e-commerce detection in beauty categories.

Beauty category discovery should ONLY return service providers
(institut de beaute, hair salons, makeup artists, bridal studios).
Retail cosmetics stores, product shops, and e-commerce sites should be rejected.
"""

import pytest
from app.agents.lead_verification import LeadVerificationAgent
from app.agents.business_name_validator import is_retail_store
from app.sources.base import RawProspect


# ── Unit tests for is_retail_store utility ──


class TestRetailStoreDetection:
    """Business name + URL retail detection."""

    def test_sephora_detected(self):
        assert is_retail_store("Sephora", "https://www.sephora.com") is True

    def test_mac_cosmetics_detected(self):
        assert is_retail_store("MAC Cosmetics Store") is True

    def test_beauty_supply_detected(self):
        assert is_retail_store("Beauty Supply Warehouse") is True

    def test_online_store_detected(self):
        assert is_retail_store("Online Beauty Store") is True

    def test_wholesale_detected(self):
        assert is_retail_store("Beauty Wholesale Distributor") is True

    def test_amazon_url_detected(self):
        assert is_retail_store("Beauty Products", "https://www.amazon.com/beauty") is True

    def test_normal_salon_not_retail(self):
        assert is_retail_store("Glamour Beauty Salon", "https://glamour-salon.com") is False

    def test_normal_clinic_not_retail(self):
        assert is_retail_store("Skin Care Clinic", "https://skincare-clinic.com") is False

    def test_makeup_artist_not_retail(self):
        assert is_retail_store("Sarah Makeup Artist") is False

    def test_bridal_studio_not_retail(self):
        assert is_retail_store("Bridal Beauty Studio") is False


# ── Integration tests for LeadVerificationAgent retail filter ──


class TestBeautyRetailFilter:
    """Reject retail stores in beauty categories."""

    def _make(self, **kwargs) -> RawProspect:
        defaults = dict(
            business_name="Test Business",
            business_category="beauty",
            city="Lahore",
            country="Pakistan",
            email="info@test.com",
        )
        defaults.update(kwargs)
        return RawProspect(**defaults)

    def test_reject_sephora(self):
        """Sephora is a retail store → reject."""
        p = self._make(
            business_name="Sephora",
            business_category="beauty",
            website="https://www.sephora.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "retail" in result.metadata["skip_reason"].lower()

    def test_reject_beauty_supply(self):
        """Beauty Supply store → reject."""
        p = self._make(
            business_name="Beauty Supply Warehouse",
            business_category="cosmetics",
            email="info@beautysupply.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "retail" in result.metadata["skip_reason"].lower()

    def test_reject_wholesale_distributor(self):
        """Wholesale distributor → reject."""
        p = self._make(
            business_name="Beauty Products Wholesale",
            business_category="cosmetics",
            email="info@wholesale.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "retail" in result.metadata["skip_reason"].lower()

    def test_reject_online_store(self):
        """Online store → reject."""
        p = self._make(
            business_name="Online Beauty Store",
            business_category="beauty",
            email="info@onlinebeauty.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False

    def test_reject_amazon_url(self):
        """Amazon product page → reject."""
        p = self._make(
            business_name="Beauty Products",
            business_category="beauty",
            website="https://www.amazon.com/beauty-products",
            email="seller@amazon.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False

    def test_accept_normal_salon(self):
        """Normal beauty salon → accept."""
        p = self._make(
            business_name="Glamour Beauty Salon",
            business_category="beauty",
            website="https://glamour-salon.com",
            email="info@glamour-salon.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "Retail store / e-commerce (not a service provider)"

    def test_accept_hair_salon(self):
        """Hair salon → accept."""
        p = self._make(
            business_name="City Hair Salon",
            business_category="hairdresser",
            email="info@cityhair.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "Retail store / e-commerce (not a service provider)"

    def test_accept_makeup_artist(self):
        """Makeup artist → accept."""
        p = self._make(
            business_name="Sarah's Makeup Studio",
            business_category="beauty",
            email="sarah@makeupstudio.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "Retail store / e-commerce (not a service provider)"

    def test_accept_bridal_studio(self):
        """Bridal studio → accept."""
        p = self._make(
            business_name="Royal Bridal Studio",
            business_category="beauty",
            email="info@royalbridal.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "Retail store / e-commerce (not a service provider)"

    def test_accept_skin_clinic(self):
        """Skin care clinic → accept."""
        p = self._make(
            business_name="Advanced Skin Care Clinic",
            business_category="beauty",
            email="info@skincare-clinic.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata.get("skip_reason") != "Retail store / e-commerce (not a service provider)"

    def test_non_beauty_category_skips_retail_check(self):
        """Non-beauty categories should NOT be filtered by retail check."""
        p = self._make(
            business_name="Dental Supply Wholesale",
            business_category="dental clinic",
            email="info@dentalsupply.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        # Should pass retail check (not beauty category)
        assert result.metadata.get("skip_reason") != "Retail store / e-commerce (not a service provider)"

    def test_retail_rejected_before_contact_check(self):
        """Retail check should run, but contact check runs first.
        Both must pass for verification."""
        p = self._make(
            business_name="Sephora",
            business_category="beauty",
            phone="+923001234567",
            email="info@sephora.com",
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        # Sephora has valid contact, but is retail → rejected
        assert result.metadata["is_verified"] is False
        assert "retail" in result.metadata["skip_reason"].lower()

    def test_retail_in_snippet_detected(self):
        """Retail signals in snippet text should be detected."""
        p = self._make(
            business_name="Beauty Products Store",
            business_category="cosmetics",
            email="info@beautyproducts.com",
            metadata={"snippet": "Buy online beauty products, free shipping on orders"},
        )
        agent = LeadVerificationAgent()
        result = agent.verify(p)
        assert result.metadata["is_verified"] is False
        assert "retail" in result.metadata["skip_reason"].lower()


# ── Tests for Google Search retail filtering ──


class TestGoogleSearchRetailFilter:
    """Google Search source should filter retail results for beauty categories."""

    def test_is_beauty_category(self):
        """Beauty-related categories should be detected."""
        from app.sources.google_search import GoogleSearchSource
        source = GoogleSearchSource()
        assert source._is_beauty_category("beauty salon") is True
        assert source._is_beauty_category("makeup artist") is True
        assert source._is_beauty_category("dental clinic") is False

    def test_retail_result_detection(self):
        """Retail results should be detected and filtered."""
        from app.sources.google_search import GoogleSearchSource
        source = GoogleSearchSource()

        # Retail result
        retail = RawProspect(
            business_name="Sephora",
            website="https://www.sephora.com",
        )
        assert source._is_retail_result(retail) is True

        # Normal salon
        salon = RawProspect(
            business_name="Glamour Salon",
            website="https://glamour-salon.com",
        )
        assert source._is_retail_result(salon) is False
