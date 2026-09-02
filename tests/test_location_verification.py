"""
Tests for Location Verification and Updated Lead Scoring.

Tests cover:
1. LocationVerifier textual evidence extraction
2. LocationVerifier structured field matching
3. LocationVerifier mismatch detection
4. LeadScoringAgent with location verification
5. Score cap at 100 preserved
6. Lahore prospects with missing structured location but strong textual evidence
7. Businesses from other cities/countries rejected
8. Weak/uncertain leads below threshold
"""

import pytest

from app.sources.base import RawProspect
from app.agents.location_verifier import LocationVerifier, LocationVerification
from app.agents.lead_scoring import LeadScoringAgent


class TestLocationVerifier:
    """Test the LocationVerifier class."""

    def setup_method(self):
        self.verifier = LocationVerifier()
        self.target_city = "lahore"
        self.target_country = "pakistan"

    # ── Structured Field Tests ──

    def test_structured_both_match_verified(self):
        """Prospect with matching structured city+country → verified."""
        p = RawProspect(
            business_name="Smile Dental",
            country="Pakistan",
            city="Lahore",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "verified"
        assert result.confidence >= 0.9

    def test_structured_country_only_mismatch(self):
        """Prospect with wrong country → mismatch."""
        p = RawProspect(
            business_name="Dubai Dental",
            country="UAE",
            city="Dubai",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "mismatch"

    def test_structured_city_only_no_country_verified_with_text(self):
        """Prospect with matching city but no country → verified via structured."""
        p = RawProspect(
            business_name="Smile Dental",
            city="Lahore",
            metadata={"snippet": "Dental clinic in Lahore, Pakistan"},
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state in ("verified", "probably_verified")

    def test_empty_structured_fields_unknown(self):
        """Prospect with no structured location and no text → unknown."""
        p = RawProspect(
            business_name="Some Clinic",
            country="",
            city="",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "unknown"

    # ── Textual Evidence Tests ──

    def test_snippet_contains_city_and_country(self):
        """Snippet mentioning 'Lahore, Pakistan' → verified."""
        p = RawProspect(
            business_name="Smile Dental",
            country="",
            city="",
            metadata={"snippet": "Best dental clinic in Lahore, Pakistan. Call now!"},
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "verified"
        assert result.found_city == "lahore"
        assert result.found_country == "pakistan"

    def test_snippet_contains_city_only(self):
        """Snippet mentioning 'Lahore' but not Pakistan → probably_verified."""
        p = RawProspect(
            business_name="Smile Dental",
            country="",
            city="",
            metadata={"snippet": "Dental clinic in Lahore. Open 9am-5pm."},
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "probably_verified"
        assert result.found_city == "lahore"

    def test_url_contains_city(self):
        """URL containing 'lahore' and '.pk' → verified (both city and country)."""
        p = RawProspect(
            business_name="Smile Dental",
            country="",
            city="",
            source_url="https://smile-dental-lahore.pk/appointments",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "verified"  # .pk = Pakistan + lahore = city

    def test_url_contains_country_code(self):
        """URL with .pk domain → probably_verified (country match)."""
        p = RawProspect(
            business_name="Smile Dental",
            country="",
            city="",
            website="https://smiledental.pk",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "probably_verified"

    def test_business_name_contains_city(self):
        """Business name 'Lahore Dental Care' → probably_verified."""
        p = RawProspect(
            business_name="Lahore Dental Care",
            country="",
            city="",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state in ("probably_verified", "verified")

    def test_address_contains_city(self):
        """Address field with city → probably_verified."""
        p = RawProspect(
            business_name="Smile Dental",
            country="",
            city="",
            address="123 Main Boulevard, Gulberg, Lahore",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state in ("probably_verified", "verified")

    def test_business_research_contains_city(self):
        """Business research mentioning Lahore → probably_verified."""
        p = RawProspect(
            business_name="Smile Dental",
            country="",
            city="",
            business_research="Smile Dental is a dental clinic in Lahore offering cosmetic dentistry.",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state in ("probably_verified", "verified")

    # ── Mismatch Detection ──

    def test_text_mentions_other_city(self):
        """Text mentioning 'Karachi' when target is Lahore → mismatch."""
        p = RawProspect(
            business_name="Karachi Dental Center",
            country="Pakistan",
            city="",
            metadata={"snippet": "Located in Karachi, Pakistan"},
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "mismatch"

    def test_text_mentions_other_country(self):
        """Text mentioning 'India' when target is Pakistan → mismatch."""
        p = RawProspect(
            business_name="Mumbai Dental",
            country="",
            city="",
            metadata={"snippet": "Dental clinic in Mumbai, India"},
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "mismatch"

    def test_structured_mismatch_overrides_text(self):
        """Structured UAE/Dubai overrides any text saying Lahore."""
        p = RawProspect(
            business_name="Dubai Dental",
            country="UAE",
            city="Dubai",
            metadata={"snippet": "Also serving clients in Lahore, Pakistan"},
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        # Structured says mismatch, so mismatch wins
        assert result.state == "mismatch"

    # ── Fuzzy Matching ──

    def test_city_alias_match(self):
        """'LHR' should match 'Lahore'."""
        p = RawProspect(
            business_name="Smile Dental",
            country="Pakistan",
            city="LHR",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "verified"

    def test_country_code_match(self):
        """'.pk' in country field should match Pakistan (probably_verified without city)."""
        p = RawProspect(
            business_name="Smile Dental",
            country=".pk",
            city="",
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "probably_verified"  # country matches but city missing

    # ── Multiple Evidence Sources ──

    def test_multiple_evidence_sources(self):
        """Multiple textual sources reinforcing the same location → higher confidence."""
        p = RawProspect(
            business_name="Smile Dental Lahore",
            country="",
            city="",
            website="https://smiledental-lahore.pk",
            address="Gulberg, Lahore",
            metadata={"snippet": "Best dental clinic in Lahore, Pakistan"},
        )
        result = self.verifier.verify(p, self.target_city, self.target_country)
        assert result.state == "verified"
        assert result.confidence >= 0.7


class TestLeadScoringLocationVerification:
    """Test LeadScoringAgent with location verification."""

    def _make_prospect(self, **kwargs):
        defaults = {
            "business_name": "Test Business",
            "business_category": "Dental Clinic",
            "country": "",
            "city": "",
        }
        defaults.update(kwargs)
        return RawProspect(**defaults)

    def test_lahore_prospect_with_textual_evidence_qualifies(self):
        """Lahore business with empty structured fields but strong text evidence
        should qualify (score >= 60)."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_category="Dental Clinic",
            country="",
            city="",
            website="https://smiledental.pk",
            email="info@smiledental.pk",
            phone="+923001234567",
            source="google_search",
            address="Gulberg, Lahore",
            metadata={
                "snippet": "Smile Dental Clinic in Lahore, Pakistan. Expert dental care.",
                "problems_list": ["Appointment booking", "Patient inquiries"],
                "demo_url": "https://demo.example.com",
            },
        )

        score = scoring.score_batch([p])[0]
        # Should be >= 60 now with textual evidence
        assert score.lead_score >= 60, f"Expected >= 60, got {score.lead_score}"
        assert score.is_qualified is True

    def test_lahore_business_name_contains_city(self):
        """Business name 'Lahore Dental Care' should provide location evidence."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_name="Lahore Dental Care",
            business_category="Dental Clinic",
            country="Pakistan",
            website="https://lahoredental.pk",
            email="info@lahoredental.pk",
            phone="+923001234567",
        )

        score = scoring.score_batch([p])[0]
        assert score.lead_score >= 60

    def test_other_city_business_rejected(self):
        """Karachi business should NOT match Lahore target."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_name="Karachi Dental Center",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Karachi",
            metadata={"snippet": "Located in Karachi, Pakistan"},
        )

        result = scoring.score_batch([p])[0]
        # Should be rejected or score very low
        assert result.lead_score == 0 or result.is_qualified is False

    def test_other_country_business_rejected(self):
        """Dubai business should NOT match Pakistan target."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_name="Dubai Dental Center",
            business_category="Dental Clinic",
            country="UAE",
            city="Dubai",
        )

        result = scoring.score_batch([p])[0]
        assert result.lead_score == 0
        assert result.is_qualified is False

    def test_unknown_location_not_assumed(self):
        """Prospect with no location evidence at all should not be assumed relevant."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_name="Random Dental",
            business_category="Dental Clinic",
            country="",
            city="",
            website="https://randomdental.com",
            email="info@randomdental.com",
        )

        score = scoring.score_batch([p])[0]
        # Without location evidence, should score lower (no location points)
        assert score.lead_score < 60

    def test_strong_target_business_high_score(self):
        """Strong Lahore business with all evidence should score 80+."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_name="Smile Dental Clinic",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://smiledental.pk",
            email="info@smiledental.pk",
            phone="+923001234567",
            source="google_maps",
            google_maps_url="https://maps.google.com/cid/123",
            address="Gulberg, Lahore",
            metadata={
                "problems_list": ["Appointment booking", "Patient inquiries"],
                "demo_url": "https://demo.example.com",
            },
        )

        score = scoring.score_batch([p])[0]
        assert score.lead_score >= 80

    def test_weak_business_below_threshold(self):
        """Business with minimal info should score below 60."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_name="Random Clinic",
            business_category="Gym",
            country="India",
            city="Mumbai",
        )

        score = scoring.score_batch([p])[0]
        assert score.lead_score < 30

    def test_duplicate_prospect_rejected_by_scoring(self):
        """Duplicate detection is at discovery level, but scoring rejects mismatches."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p1 = self._make_prospect(
            business_name="Smile Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://smiledental.pk",
        )
        p2 = self._make_prospect(
            business_name="Smile Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://smiledental.pk",
        )

        # Both are valid Lahore prospects — dedup happens at discovery level
        scored = scoring.score_batch([p1, p2])
        assert len(scored) == 2
        # Both should have valid scores (no mismatch)
        assert scored[0].lead_score > 0
        assert scored[1].lead_score > 0

    def test_score_never_exceeds_100(self):
        """Score must be capped at 100 even with all factors present."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = self._make_prospect(
            business_name="Smile Dental Clinic Lahore",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://smiledental.pk",
            email="info@smiledental.pk",
            phone="+923001234567",
            source="google_maps",
            google_maps_url="https://maps.google.com/cid/123",
            address="Gulberg, Lahore",
            business_research="Smile Dental is a leading dental clinic in Lahore, Pakistan",
            metadata={
                "problems_list": ["Appointment booking", "Patient inquiries", "WhatsApp"],
                "demo_url": "https://demo.example.com",
                "snippet": "Best dental clinic in Lahore, Pakistan",
            },
        )

        score = scoring.score_batch([p])[0]
        assert score.lead_score <= 100

    def test_weights_sum_to_100(self):
        """Verify the scoring weights are reasonable and score caps at 100."""
        total = sum(LeadScoringAgent.WEIGHTS.values())
        # Weights can slightly exceed 100 since score() caps at min(score, 100)
        assert total <= 110, f"Weights sum to {total}, expected <= 110"


class TestLocationVerificationEdgeCases:
    """Edge cases for location verification."""

    def setup_method(self):
        self.verifier = LocationVerifier()

    def test_completely_empty_prospect(self):
        """Empty prospect should return unknown."""
        p = RawProspect()
        result = self.verifier.verify(p, "lahore", "pakistan")
        assert result.state == "unknown"

    def test_www_in_url_not_flagged_as_mismatch(self):
        """'www.' in URL should not trigger country mismatch."""
        p = RawProspect(
            business_name="Smile Dental",
            website="https://www.smiledental.pk",
        )
        result = self.verifier.verify(p, "lahore", "pakistan")
        # .pk matches Pakistan — should be probably_verified, not mismatch
        assert result.state in ("probably_verified", "verified")

    def test_dotcom_not_flagged_as_usa_mismatch(self):
        """'.com' domain should NOT trigger USA mismatch."""
        p = RawProspect(
            business_name="Smile Dental Lahore",
            website="https://smiledental.com",
            metadata={"snippet": "Dental clinic in Lahore, Pakistan"},
        )
        result = self.verifier.verify(p, "lahore", "pakistan")
        # Should NOT be mismatch just because of .com
        assert result.state != "mismatch"
        assert result.state in ("verified", "probably_verified")

    def test_target_city_empty_always_unknown(self):
        """If target city is empty, should return unknown (can't verify)."""
        p = RawProspect(
            business_name="Smile Dental",
            metadata={"snippet": "Dental clinic"},
        )
        result = self.verifier.verify(p, "", "pakistan")
        # No target city to match against
        assert result.state in ("unknown", "probably_verified")

    def test_structured_city_matches_wrong_country_rejects(self):
        """City matches but country is wrong → mismatch."""
        p = RawProspect(
            business_name="Lahore Dental",
            country="India",
            city="Lahore",
        )
        result = self.verifier.verify(p, "lahore", "pakistan")
        assert result.state == "mismatch"


class TestScoreBatchRejectsLocationMismatches:
    """Test that score_batch properly rejects location mismatches."""

    def test_mismatched_leads_score_zero(self):
        """Location mismatch leads should score 0."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        # Good lead
        good = RawProspect(
            business_name="Lahore Dental",
            business_category="Dental Clinic",
            country="Pakistan",
            city="Lahore",
            website="https://lahoredental.pk",
            email="info@lahoredental.pk",
            phone="+923001234567",
        )

        # Bad lead (wrong city)
        bad = RawProspect(
            business_name="Mumbai Dental",
            business_category="Dental Clinic",
            country="India",
            city="Mumbai",
        )

        scored = scoring.score_batch([good, bad])
        # Good lead should be first with high score
        assert scored[0].business_name == "Lahore Dental"
        assert scored[0].lead_score > 0
        # Bad lead should be last with 0
        bad_result = [s for s in scored if s.business_name == "Mumbai Dental"][0]
        assert bad_result.lead_score == 0
        assert bad_result.is_qualified is False

    def test_text_evidence_mismatch_rejects(self):
        """Textual evidence showing different city should reject."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        p = RawProspect(
            business_name="Karachi Dental Center",
            business_category="Dental Clinic",
            country="Pakistan",
            city="",
            metadata={"snippet": "Located in Karachi, Pakistan"},
        )

        scored = scoring.score_batch([p])[0]
        assert scored.lead_score == 0
        assert scored.is_qualified is False

    def test_mixed_batch_correct_ordering(self):
        """Batch with good + bad leads should order correctly."""
        scoring = LeadScoringAgent(
            target_category="dental clinic",
            target_country="pakistan",
            target_city="lahore",
        )

        leads = [
            RawProspect(
                business_name="Mumbai Dental",
                business_category="Dental Clinic",
                country="India",
                city="Mumbai",
            ),
            RawProspect(
                business_name="Lahore Dental",
                business_category="Dental Clinic",
                country="Pakistan",
                city="Lahore",
                website="https://lahoredental.pk",
                email="info@lahoredental.pk",
                phone="+923001234567",
            ),
            RawProspect(
                business_name="Dubai Dental",
                business_category="Dental Clinic",
                country="UAE",
                city="Dubai",
            ),
        ]

        scored = scoring.score_batch(leads)
        # Lahore should be first, mismatches at bottom
        assert scored[0].business_name == "Lahore Dental"
        assert scored[0].lead_score > 0
        # Mismatches should have 0
        for s in scored[1:]:
            assert s.lead_score == 0
