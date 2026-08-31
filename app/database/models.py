"""
SQLAlchemy models for internal database (SQLite).
Used for: deduplication, search cache, job history, scheduler state.
Google Sheets is the primary human-visible CRM.
"""

from __future__ import annotations

import datetime as _dt
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config.settings import DATA_DIR


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class DiscoveredLead(Base):
    """Internal tracking of every business discovered during search."""

    __tablename__ = "discovered_leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    # Business identity
    business_name = Column(String(500), nullable=False)
    business_category = Column(String(200), default="")
    country = Column(String(100), default="")
    city = Column(String(100), default="")
    address = Column(Text, default="")
    phone = Column(String(100), default="")
    email = Column(String(300), default="")
    website = Column(String(1000), default="")
    google_maps_url = Column(String(2000), default="")

    # Source tracking
    source = Column(String(100), default="")  # google_maps / google_search / linkedin / public_jobs
    source_url = Column(String(2000), default="")
    posted_date = Column(String(100), default="")  # raw date string if available

    # Research
    business_research = Column(Text, default="")
    potential_problem = Column(Text, default="")
    recommended_service = Column(String(200), default="")
    recommended_ai_solution = Column(Text, default="")

    # Scoring
    lead_score = Column(Integer, default=0)

    # Outreach state
    is_qualified = Column(Boolean, default=False)
    is_outreach_lead = Column(Boolean, default=False)
    is_duplicate = Column(Boolean, default=False)
    duplicate_of_id = Column(Integer, nullable=True)

    # Dedup keys (for fast lookup)
    dedup_website = Column(String(1000), default="")
    dedup_email = Column(String(300), default="")
    dedup_phone = Column(String(100), default="")
    dedup_maps_url = Column(String(2000), default="")

    # Google Sheets row reference
    sheets_row_id = Column(String(100), default="")

    # Additional notes
    notes = Column(Text, default="")


class CampaignRun(Base):
    """Tracks a single daily campaign execution."""

    __tablename__ = "campaign_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    target_country = Column(String(100), default="")
    target_city = Column(String(100), default="")
    target_category = Column(String(200), default="")
    target_count = Column(Integer, default=0)

    discovered_count = Column(Integer, default=0)
    qualified_count = Column(Integer, default=0)
    final_count = Column(Integer, default=0)

    emails_sent = Column(Integer, default=0)
    whatsapp_sent = Column(Integer, default=0)
    followups_3day = Column(Integer, default=0)
    followups_7day = Column(Integer, default=0)
    failed = Column(Integer, default=0)
    skipped = Column(Integer, default=0)
    interested = Column(Integer, default=0)
    human_required = Column(Integer, default=0)

    status = Column(String(50), default="running")  # running / completed / failed
    error_message = Column(Text, default="")


class FollowUpState(Base):
    """Tracks follow-up status for each outreach lead."""

    __tablename__ = "followup_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(Integer, nullable=False)

    initial_sent_at = Column(DateTime, nullable=True)
    initial_channel = Column(String(50), default="")  # email / whatsapp
    initial_status = Column(String(50), default="pending")  # pending / sent / failed

    followup_3day_sent_at = Column(DateTime, nullable=True)
    followup_3day_status = Column(String(50), default="pending")

    followup_7day_sent_at = Column(DateTime, nullable=True)
    followup_7day_status = Column(String(50), default="pending")

    overall_status = Column(String(50), default="active")  # active / stopped / completed
    do_not_contact = Column(Boolean, default=False)
    human_required = Column(Boolean, default=False)
    response_category = Column(String(100), default="")

    # Google Sheets row id for updates
    sheets_row_id = Column(String(100), default="")


class DailyCounter(Base):
    """Persists the daily outreach count across restarts."""

    __tablename__ = "daily_counters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String(10), nullable=False, unique=True)  # YYYY-MM-DD
    outreach_count = Column(Integer, default=0)
    search_count = Column(Integer, default=0)


# ---------------------------------------------------------------------------
# Engine & session factory
# ---------------------------------------------------------------------------
_DB_PATH = DATA_DIR / "lead_agent.db"
_engine = create_engine(
    f"sqlite:///{_DB_PATH}",
    echo=False,
    connect_args={"check_same_thread": False},
)

# Enable WAL mode for better concurrency
@event.listens_for(_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    """Get a new database session."""
    return SessionLocal()
