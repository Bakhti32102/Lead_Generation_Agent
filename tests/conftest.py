"""
Shared test fixtures for the Lead Generation Agent test suite.
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Set test environment variables BEFORE any app imports
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("LLM_API_KEY", "")
os.environ.setdefault("SEARCH_PROVIDER", "tavily")
os.environ.setdefault("SEARCH_API_KEY", "")
os.environ.setdefault("GOOGLE_MAPS_API_KEY", "")
os.environ.setdefault("GOOGLE_SHEET_ID", "")
os.environ.setdefault("GOOGLE_SERVICE_ACCOUNT_JSON", "nonexistent.json")
os.environ.setdefault("EMAIL_PROVIDER", "gmail")
os.environ.setdefault("EMAIL_API_KEY", "")
os.environ.setdefault("EMAIL_FROM", "")
os.environ.setdefault("WHATSAPP_ACCESS_TOKEN", "")
os.environ.setdefault("WHATSAPP_PHONE_NUMBER_ID", "")
os.environ.setdefault("DRY_RUN", "true")
os.environ.setdefault("REVIEW_MODE", "true")
os.environ.setdefault("DAILY_LEAD_TARGET", "10")
os.environ.setdefault("LEAD_SCORE_THRESHOLD", "60")
os.environ.setdefault("MY_NAME", "Test Agent")
os.environ.setdefault("MY_BUSINESS_DESCRIPTION", "AI Development Business")
os.environ.setdefault("MY_EMAIL", "test@example.com")
os.environ.setdefault("MY_WEBSITE_URL", "https://example.com")
os.environ.setdefault("MY_FIVERR_URL", "https://fiverr.com/test")
os.environ.setdefault("MY_LINKEDIN_URL", "https://linkedin.com/in/test")


@pytest.fixture(autouse=True)
def init_test_db():
    """Auto-initialize the database before every test that touches the DB."""
    from app.database.models import init_db
    init_db()
    yield


@pytest.fixture
def sample_prospect():
    """A basic RawProspect for testing."""
    from app.sources.base import RawProspect
    return RawProspect(
        business_name="Smile Dental Clinic",
        business_category="Dental Clinic",
        country="Pakistan",
        city="Lahore",
        address="123 Main Street, Lahore",
        phone="+923001234567",
        email="info@smiledental.pk",
        website="https://smiledental.pk",
        google_maps_url="https://maps.google.com/place?place_id=abc123",
        source="google_maps",
        source_url="https://google.com/maps/smiledental",
    )


@pytest.fixture
def sample_prospect_no_website():
    """A prospect without a website."""
    from app.sources.base import RawProspect
    return RawProspect(
        business_name="Quick Bites Restaurant",
        business_category="Restaurant",
        country="UAE",
        city="Dubai",
        phone="+971501234567",
        email="contact@quickbites.ae",
        source="google_maps",
    )


@pytest.fixture
def sample_prospect_recent_requirement():
    """A prospect with a recent AI requirement."""
    from app.sources.base import RawProspect
    return RawProspect(
        business_name="TechCorp Solutions",
        business_category="Technology",
        country="UK",
        city="London",
        website="https://techcorp.co.uk",
        source="linkedin",
        source_url="https://linkedin.com/posts/abc123",
        requirement_text="Looking for AI chatbot developer to build customer support bot",
        freshness="verified_recent",
        hours_old=2,
    )
