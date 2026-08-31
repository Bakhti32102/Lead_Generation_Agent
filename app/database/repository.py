"""
Repository layer for all database operations.
Provides clean interfaces for CRUD, dedup, counters, and follow-up state.
"""

from __future__ import annotations

import datetime as _dt
from typing import List, Optional

from sqlalchemy import and_

from app.database.models import (
    CampaignRun,
    DailyCounter,
    DiscoveredLead,
    FollowUpState,
    get_session,
)


class LeadRepository:
    """Handles DiscoveredLead CRUD and deduplication checks."""

    # ---- Create ----

    def save_lead(self, lead_data: dict) -> DiscoveredLead:
        """Insert a new discovered lead and return it."""
        session = get_session()
        try:
            lead = DiscoveredLead(**lead_data)
            session.add(lead)
            session.commit()
            session.refresh(lead)
            return lead
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def save_leads_batch(self, leads_data: List[dict]) -> List[DiscoveredLead]:
        """Bulk insert leads. Returns list of created leads."""
        session = get_session()
        try:
            leads = [DiscoveredLead(**d) for d in leads_data]
            session.add_all(leads)
            session.commit()
            for lead in leads:
                session.refresh(lead)
            return leads
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- Read ----

    def get_lead(self, lead_id: int) -> Optional[DiscoveredLead]:
        session = get_session()
        try:
            return session.query(DiscoveredLead).filter_by(id=lead_id).first()
        finally:
            session.close()

    def get_qualified_leads_for_date(
        self, date: Optional[_dt.date] = None
    ) -> List[DiscoveredLead]:
        """Get all qualified outreach leads for a given date."""
        if date is None:
            date = _dt.date.today()
        start = _dt.datetime.combine(date, _dt.time.min)
        end = _dt.datetime.combine(date, _dt.time.max)
        session = get_session()
        try:
            return (
                session.query(DiscoveredLead)
                .filter(
                    and_(
                        DiscoveredLead.is_outreach_lead == True,
                        DiscoveredLead.created_at >= start,
                        DiscoveredLead.created_at <= end,
                    )
                )
                .order_by(DiscoveredLead.lead_score.desc())
                .all()
            )
        finally:
            session.close()

    def get_leads_by_date_range(
        self, start_date: _dt.date, end_date: _dt.date
    ) -> List[DiscoveredLead]:
        start = _dt.datetime.combine(start_date, _dt.time.min)
        end = _dt.datetime.combine(end_date, _dt.time.max)
        session = get_session()
        try:
            return (
                session.query(DiscoveredLead)
                .filter(
                    and_(
                        DiscoveredLead.created_at >= start,
                        DiscoveredLead.created_at <= end,
                    )
                )
                .all()
            )
        finally:
            session.close()

    def get_all_qualified(self) -> List[DiscoveredLead]:
        session = get_session()
        try:
            return (
                session.query(DiscoveredLead)
                .filter_by(is_outreach_lead=True)
                .order_by(DiscoveredLead.lead_score.desc())
                .all()
            )
        finally:
            session.close()

    # ---- Update ----

    def update_lead(self, lead_id: int, updates: dict) -> Optional[DiscoveredLead]:
        session = get_session()
        try:
            lead = session.query(DiscoveredLead).filter_by(id=lead_id).first()
            if lead is None:
                return None
            for key, value in updates.items():
                if hasattr(lead, key):
                    setattr(lead, key, value)
            session.commit()
            session.refresh(lead)
            return lead
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def mark_duplicate(self, lead_id: int, original_id: int) -> None:
        self.update_lead(lead_id, {
            "is_duplicate": True,
            "duplicate_of_id": original_id,
        })

    # ---- Deduplication ----

    def is_duplicate(
        self,
        website: str = "",
        email: str = "",
        phone: str = "",
        maps_url: str = "",
        name: str = "",
    ) -> Optional[DiscoveredLead]:
        """Check if a lead already exists by ANY of the dedup keys (OR logic)."""
        from sqlalchemy import or_

        session = get_session()
        try:
            query = session.query(DiscoveredLead)
            filters = []
            if website:
                filters.append(DiscoveredLead.dedup_website == website.lower().strip())
            if email:
                filters.append(DiscoveredLead.dedup_email == email.lower().strip())
            if phone:
                filters.append(DiscoveredLead.dedup_phone == phone.strip())
            if maps_url:
                filters.append(DiscoveredLead.dedup_maps_url == maps_url.strip())

            if filters:
                # Use OR: if ANY dedup key matches, it's a duplicate
                result = query.filter(or_(*filters)).first()
                return result

            # Fallback: match by normalized business name
            if name and name.strip():
                result = (
                    query.filter(
                        DiscoveredLead.business_name.ilike(f"%{name.strip()}%")
                    )
                    .first()
                )
                return result

            return None
        finally:
            session.close()

    # ---- Counting ----

    def count_qualified_today(self) -> int:
        today = _dt.date.today()
        start = _dt.datetime.combine(today, _dt.time.min)
        end = _dt.datetime.combine(today, _dt.time.max)
        session = get_session()
        try:
            return (
                session.query(DiscoveredLead)
                .filter(
                    and_(
                        DiscoveredLead.is_outreach_lead == True,
                        DiscoveredLead.created_at >= start,
                        DiscoveredLead.created_at <= end,
                    )
                )
                .count()
            )
        finally:
            session.close()


class FollowUpRepository:
    """Handles follow-up state tracking."""

    def create_state(self, lead_id: int, initial_channel: str = "") -> FollowUpState:
        session = get_session()
        try:
            state = FollowUpState(
                lead_id=lead_id,
                initial_channel=initial_channel,
                initial_status="pending",
                overall_status="active",
            )
            session.add(state)
            session.commit()
            session.refresh(state)
            return state
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_by_lead_id(self, lead_id: int) -> Optional[FollowUpState]:
        session = get_session()
        try:
            return session.query(FollowUpState).filter_by(lead_id=lead_id).first()
        finally:
            session.close()

    def get_due_followups_3day(self) -> List[FollowUpState]:
        """Get leads that need a 3-day follow-up."""
        session = get_session()
        try:
            three_days_ago = _dt.datetime.utcnow() - _dt.timedelta(days=3)
            return (
                session.query(FollowUpState)
                .filter(
                    and_(
                        FollowUpState.overall_status == "active",
                        FollowUpState.initial_status == "sent",
                        FollowUpState.followup_3day_status == "pending",
                        FollowUpState.initial_sent_at <= three_days_ago,
                        FollowUpState.do_not_contact == False,
                    )
                )
                .all()
            )
        finally:
            session.close()

    def get_due_followups_7day(self) -> List[FollowUpState]:
        """Get leads that need a 7-day follow-up."""
        session = get_session()
        try:
            seven_days_ago = _dt.datetime.utcnow() - _dt.timedelta(days=7)
            return (
                session.query(FollowUpState)
                .filter(
                    and_(
                        FollowUpState.overall_status == "active",
                        FollowUpState.initial_status == "sent",
                        FollowUpState.followup_7day_status == "pending",
                        FollowUpState.initial_sent_at <= seven_days_ago,
                        FollowUpState.do_not_contact == False,
                    )
                )
                .all()
            )
        finally:
            session.close()

    def mark_initial_sent(
        self, lead_id: int, channel: str, sheets_row_id: str = ""
    ) -> None:
        session = get_session()
        try:
            state = session.query(FollowUpState).filter_by(lead_id=lead_id).first()
            if state:
                state.initial_sent_at = _dt.datetime.utcnow()
                state.initial_channel = channel
                state.initial_status = "sent"
                state.sheets_row_id = sheets_row_id
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def mark_followup_3day_sent(self, lead_id: int) -> None:
        session = get_session()
        try:
            state = session.query(FollowUpState).filter_by(lead_id=lead_id).first()
            if state:
                state.followup_3day_sent_at = _dt.datetime.utcnow()
                state.followup_3day_status = "sent"
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def mark_followup_7day_sent(self, lead_id: int) -> None:
        session = get_session()
        try:
            state = session.query(FollowUpState).filter_by(lead_id=lead_id).first()
            if state:
                state.followup_7day_sent_at = _dt.datetime.utcnow()
                state.followup_7day_status = "sent"
                state.overall_status = "completed"
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def stop_followups(self, lead_id: int) -> None:
        session = get_session()
        try:
            state = session.query(FollowUpState).filter_by(lead_id=lead_id).first()
            if state:
                state.overall_status = "stopped"
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_do_not_contact(self, lead_id: int) -> None:
        session = get_session()
        try:
            state = session.query(FollowUpState).filter_by(lead_id=lead_id).first()
            if state:
                state.do_not_contact = True
                state.overall_status = "stopped"
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def set_human_required(self, lead_id: int) -> None:
        session = get_session()
        try:
            state = session.query(FollowUpState).filter_by(lead_id=lead_id).first()
            if state:
                state.human_required = True
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_response(self, lead_id: int, category: str) -> None:
        session = get_session()
        try:
            state = session.query(FollowUpState).filter_by(lead_id=lead_id).first()
            if state:
                state.response_category = category
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class CampaignRepository:
    """Tracks campaign run history."""

    def create_run(self, data: dict) -> CampaignRun:
        session = get_session()
        try:
            run = CampaignRun(**data)
            session.add(run)
            session.commit()
            session.refresh(run)
            return run
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_run(self, run_id: int, updates: dict) -> None:
        session = get_session()
        try:
            run = session.query(CampaignRun).filter_by(id=run_id).first()
            if run:
                for k, v in updates.items():
                    if hasattr(run, k):
                        setattr(run, k, v)
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_today_run(self) -> Optional[CampaignRun]:
        today = _dt.date.today()
        start = _dt.datetime.combine(today, _dt.time.min)
        end = _dt.datetime.combine(today, _dt.time.max)
        session = get_session()
        try:
            return (
                session.query(CampaignRun)
                .filter(and_(CampaignRun.created_at >= start, CampaignRun.created_at <= end))
                .first()
            )
        finally:
            session.close()


class CounterRepository:
    """Persists daily counters (outreach count, search count) to survive restarts."""

    def _get_or_create(self, session, date_str: str) -> DailyCounter:
        counter = session.query(DailyCounter).filter_by(date=date_str).first()
        if counter is None:
            counter = DailyCounter(date=date_str, outreach_count=0, search_count=0)
            session.add(counter)
            session.flush()
        return counter

    def increment_outreach(self, date_str: str = "", amount: int = 1) -> int:
        if not date_str:
            date_str = _dt.date.today().isoformat()
        session = get_session()
        try:
            counter = self._get_or_create(session, date_str)
            counter.outreach_count += amount
            session.commit()
            return counter.outreach_count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_outreach_count(self, date_str: str = "") -> int:
        if not date_str:
            date_str = _dt.date.today().isoformat()
        session = get_session()
        try:
            counter = session.query(DailyCounter).filter_by(date=date_str).first()
            return counter.outreach_count if counter else 0
        finally:
            session.close()

    def can_send_more(self, max_daily: int, date_str: str = "") -> bool:
        return self.get_outreach_count(date_str) < max_daily
