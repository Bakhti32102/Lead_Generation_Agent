"""Tests for lead deduplication."""

import uuid
import pytest

from app.sources.base import RawProspect
from app.agents.lead_discovery import LeadDiscoveryAgent


class TestDeduplication:
    """Deduplication by website, email, phone, maps URL, name+city."""

    def _uid(self):
        """Generate a unique identifier for test isolation."""
        return uuid.uuid4().hex[:8]

    def _make_prospect(self, **kwargs):
        defaults = {
            "business_name": "Test Business",
            "business_category": "Clinic",
            "country": "Pakistan",
            "city": "Lahore",
        }
        defaults.update(kwargs)
        return RawProspect(**defaults)

    def test_duplicate_website_removed(self):
        """Two prospects with same website should be deduplicated."""
        agent = LeadDiscoveryAgent()
        uid = self._uid()
        p1 = self._make_prospect(website=f"https://{uid}clinic.com")
        p2 = self._make_prospect(
            business_name=f"Test Business 2 {uid}",
            website=f"https://{uid}clinic.com",
        )
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 1

    def test_duplicate_email_removed(self):
        """Two prospects with same email should be deduplicated."""
        agent = LeadDiscoveryAgent()
        uid = self._uid()
        p1 = self._make_prospect(email=f"info@{uid}clinic.com")
        p2 = self._make_prospect(
            business_name=f"Clinic 2 {uid}",
            email=f"info@{uid}clinic.com",
        )
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 1

    def test_duplicate_phone_removed(self):
        """Two prospects with same phone should be deduplicated."""
        agent = LeadDiscoveryAgent()
        uid = self._uid()
        phone = f"+92300{uid[:7]}"
        p1 = self._make_prospect(phone=phone)
        p2 = self._make_prospect(
            business_name=f"Clinic 3 {uid}",
            phone=phone,
        )
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 1

    def test_duplicate_name_city_removed(self):
        """Two prospects with same name+city should be deduplicated."""
        agent = LeadDiscoveryAgent()
        uid = self._uid()
        name = f"Smile Dental {uid}"
        p1 = self._make_prospect(business_name=name, city="Lahore")
        p2 = self._make_prospect(business_name=name, city="Lahore")
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 1

    def test_different_businesses_not_deduped(self):
        """Different businesses should NOT be deduplicated."""
        agent = LeadDiscoveryAgent()
        uid = self._uid()
        p1 = self._make_prospect(
            business_name=f"Clinic A {uid}",
            website=f"https://clinica{uid}.com",
            email=f"a@clinica{uid}.com",
        )
        p2 = self._make_prospect(
            business_name=f"Clinic B {uid}",
            website=f"https://clinicb{uid}.com",
            email=f"b@clinicb{uid}.com",
        )
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 2

    def test_website_normalization(self):
        """Same domain with different URL formats should be deduplicated."""
        agent = LeadDiscoveryAgent()
        uid = self._uid()
        p1 = self._make_prospect(website=f"https://www.{uid}clinic.com")
        p2 = self._make_prospect(
            business_name=f"Clinic 2 {uid}",
            website=f"http://{uid}clinic.com/",
        )
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 1

    def test_phone_normalization(self):
        """Same phone with different formats should be deduplicated."""
        agent = LeadDiscoveryAgent()
        import random
        # Use digits-only UID so phone normalization works correctly
        uid = ''.join([str(random.randint(0,9)) for _ in range(8)])
        # Both must normalize to the same digit sequence
        # p1: +92 300 <8 digits> -> digits: 92300<8digits> = 13 digits
        # p2: 92300<8 digits>   -> digits: 92300<8digits> = 13 digits
        p1 = self._make_prospect(phone=f"+92 300 {uid[:4]} {uid[4:]}")
        p2 = self._make_prospect(
            business_name=f"Clinic 2 {uid}",
            phone=f"92300{uid}",
        )
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 1

    def test_dedup_across_sources(self):
        """Same business found in Google Maps and Google Search should be deduplicated."""
        agent = LeadDiscoveryAgent()
        uid = self._uid()
        p1 = self._make_prospect(
            website=f"https://{uid}clinic.com",
            source="google_maps",
        )
        p2 = self._make_prospect(
            business_name=f"Same Clinic {uid}",
            website=f"https://{uid}clinic.com",
            source="google_search",
        )
        merged = agent._deduplicate([p1, p2])
        assert len(merged) == 1
        # The first source should be preserved
        assert merged[0].source == "google_maps"
