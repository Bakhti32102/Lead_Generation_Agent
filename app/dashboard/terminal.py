"""
Terminal Dashboard.
Rich terminal-based dashboard for monitoring campaigns, viewing leads, and taking actions.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import sys
from typing import Dict, List, Optional

from app.config.settings import settings
from app.database import CampaignRepository, FollowUpRepository, LeadRepository
from app.database.models import init_db

logger = logging.getLogger(__name__)


def _print_header(title: str) -> None:
    width = 60
    print(f"\n{'=' * width}")
    print(f"  {title}")
    print(f"{'=' * width}")


def _print_row(label: str, value: str, width: int = 40) -> None:
    print(f"  {label:<20s} {value}")


def print_config_status() -> None:
    """Print the configuration status checker."""
    print(settings.print_status())

    # Additional details
    _print_header("Target Configuration")
    _print_row("Country", settings.campaign.target_country or "(not set)")
    _print_row("City", settings.campaign.target_city or "(not set)")
    _print_row("Category", settings.campaign.target_business_category or "(not set)")
    _print_row("Daily Target", str(settings.campaign.daily_lead_target))
    _print_row("Score Threshold", str(settings.campaign.lead_score_threshold))
    _print_row("Dry Run", str(settings.campaign.dry_run))
    _print_row("Review Mode", str(settings.campaign.review_mode))
    print()


def print_today_dashboard() -> None:
    """Print the today's campaign dashboard."""
    init_db()

    _print_header("Today's Campaign Dashboard")

    # Campaign info
    _print_row("Date", _dt.date.today().isoformat())
    _print_row("Country", settings.campaign.target_country or "(not set)")
    _print_row("City", settings.campaign.target_city or "(not set)")
    _print_row("Category", settings.campaign.target_business_category or "(not set)")

    # Counts
    lead_repo = LeadRepository()
    today_leads = lead_repo.get_qualified_leads_for_date()
    counter = __import__("app.database.repository", fromlist=["CounterRepository"]).CounterRepository()
    sent_today = counter.get_outreach_count()

    _print_row("Target Leads", str(settings.campaign.daily_lead_target))
    _print_row("Qualified Leads", str(len(today_leads)))
    _print_row("Messages Sent Today", str(sent_today))
    _print_row(
        "Remaining Limit",
        str(max(0, settings.campaign.max_daily_outreach - sent_today)),
    )

    # Follow-ups due
    followup_repo = FollowUpRepository()
    due_3day = followup_repo.get_due_followups_3day()
    due_7day = followup_repo.get_due_followups_7day()
    _print_row("3-Day Follow-ups Due", str(len(due_3day)))
    _print_row("7-Day Follow-ups Due", str(len(due_7day)))

    print()


def print_lead_table(leads=None, limit: int = 20) -> None:
    """Print a formatted lead table."""
    init_db()
    lead_repo = LeadRepository()

    if leads is None:
        leads = lead_repo.get_all_qualified()

    if not leads:
        print("\n  No qualified leads found.\n")
        return

    _print_header(f"Lead Table ({len(leads)} leads, showing {min(limit, len(leads))})")

    # Table header
    print(
        f"  {'ID':<4s} {'Score':<5s} {'Business':<25s} {'Category':<15s} "
        f"{'City':<12s} {'Source':<10s} {'Service':<15s}"
    )
    print(f"  {'─' * 4} {'─' * 5} {'─' * 25} {'─' * 15} {'─' * 12} {'─' * 10} {'─' * 15}")

    for lead in leads[:limit]:
        print(
            f"  {str(lead.id):<4s} "
            f"{str(lead.lead_score):<5s} "
            f"{(lead.business_name[:23] or ''):<25s} "
            f"{(lead.business_category[:13] or ''):<15s} "
            f"{(lead.city[:10] or ''):<12s} "
            f"{(lead.source[:8] or ''):<10s} "
            f"{(lead.recommended_service[:13] or ''):<15s}"
        )

    print()


def print_lead_detail(lead_id: int) -> None:
    """Print detailed information for a single lead."""
    init_db()
    lead_repo = LeadRepository()
    lead = lead_repo.get_lead(lead_id)

    if not lead:
        print(f"\n  Lead {lead_id} not found.\n")
        return

    _print_header(f"Lead Detail — #{lead.id}")
    _print_row("Business Name", lead.business_name)
    _print_row("Category", lead.business_category)
    _print_row("Country", lead.country)
    _print_row("City", lead.city)
    _print_row("Address", lead.address[:50] if lead.address else "")
    _print_row("Phone", lead.phone)
    _print_row("Email", lead.email)
    _print_row("Website", lead.website)
    _print_row("Maps URL", lead.google_maps_url[:50] if lead.google_maps_url else "")
    _print_row("Source", lead.source)
    _print_row("Score", str(lead.lead_score))
    _print_row("Qualified", str(lead.is_qualified))
    _print_row("Outreach Lead", str(lead.is_outreach_lead))
    print()
    _print_row("Research", lead.business_research[:100] if lead.business_research else "")
    _print_row("Problems", lead.potential_problem[:100] if lead.potential_problem else "")
    _print_row("Service", lead.recommended_service)
    _print_row("AI Solution", lead.recommended_ai_solution)
    print()
    _print_row("Notes", lead.notes[:100] if lead.notes else "")
    print()


def interactive_menu() -> None:
    """Run an interactive menu for managing leads."""
    init_db()

    while True:
        print("\n+--------------------------------------+")
        print("|        Lead Management Menu          |")
        print("+--------------------------------------+")
        print("|  1. View Dashboard                   |")
        print("|  2. View Lead Table                  |")
        print("|  3. View Lead Detail                 |")
        print("|  4. Approve Lead                     |")
        print("|  5. Reject Lead                      |")
        print("|  6. Stop Follow-ups                  |")
        print("|  7. Mark Do Not Contact              |")
        print("|  8. Mark Interested                  |")
        print("|  9. Mark Human Required              |")
        print("|  10. Run Campaign                    |")
        print("|  11. Run Follow-ups                  |")
        print("|  12. Config Status                   |")
        print("|  0. Exit                             |")
        print("+--------------------------------------+")

        choice = input("\n  Select option: ").strip()

        if choice == "1":
            print_today_dashboard()
        elif choice == "2":
            print_lead_table()
        elif choice == "3":
            lid = input("  Enter Lead ID: ").strip()
            if lid.isdigit():
                print_lead_detail(int(lid))
        elif choice == "4":
            lid = input("  Enter Lead ID to approve: ").strip()
            if lid.isdigit():
                _approve_lead(int(lid))
        elif choice == "5":
            lid = input("  Enter Lead ID to reject: ").strip()
            if lid.isdigit():
                _reject_lead(int(lid))
        elif choice == "6":
            lid = input("  Enter Lead ID to stop follow-ups: ").strip()
            if lid.isdigit():
                _stop_followups(int(lid))
        elif choice == "7":
            lid = input("  Enter Lead ID to mark Do Not Contact: ").strip()
            if lid.isdigit():
                _mark_dnc(int(lid))
        elif choice == "8":
            lid = input("  Enter Lead ID to mark Interested: ").strip()
            if lid.isdigit():
                _mark_interested(int(lid))
        elif choice == "9":
            lid = input("  Enter Lead ID to mark Human Required: ").strip()
            if lid.isdigit():
                _mark_human_required(int(lid))
        elif choice == "10":
            _run_campaign_interactive()
        elif choice == "11":
            _run_followups()
        elif choice == "12":
            print_config_status()
        elif choice == "0":
            print("Goodbye!")
            break


def _approve_lead(lead_id: int) -> None:
    from app.agents.outreach import OutreachAgent
    outreach = OutreachAgent()
    result = outreach.approve_and_send(lead_id)
    if result.get("success"):
        print(f"  ✓ Lead {lead_id} approved and sent!")
    else:
        print(f"  ✗ Failed: {result.get('message', 'Unknown error')}")


def _reject_lead(lead_id: int) -> None:
    repo = LeadRepository()
    repo.update_lead(lead_id, {"is_outreach_lead": False})
    print(f"  ✓ Lead {lead_id} rejected.")


def _stop_followups(lead_id: int) -> None:
    from app.agents.follow_up import FollowUpAgent
    fu = FollowUpAgent()
    fu.stop_followups_for_lead(lead_id)
    print(f"  ✓ Follow-ups stopped for lead {lead_id}.")


def _mark_dnc(lead_id: int) -> None:
    from app.agents.follow_up import FollowUpAgent
    fu = FollowUpAgent()
    fu.mark_do_not_contact(lead_id)
    repo = LeadRepository()
    repo.update_lead(lead_id, {"is_outreach_lead": False})
    print(f"  ✓ Lead {lead_id} marked as Do Not Contact.")


def _mark_interested(lead_id: int) -> None:
    from app.agents.follow_up import FollowUpAgent
    fu = FollowUpAgent()
    fu.handle_reply(lead_id, "interested")
    print(f"  ✓ Lead {lead_id} marked as Interested.")


def _mark_human_required(lead_id: int) -> None:
    from app.agents.follow_up import FollowUpAgent
    fu = FollowUpAgent()
    fu.handle_reply(lead_id, "human_required")
    print(f"  ✓ Lead {lead_id} marked as Human Required.")


def _run_campaign_interactive() -> None:
    """Run a campaign with interactive input."""
    print("\n  Enter campaign target (or press Enter to use .env defaults):")
    country = input("  Country: ").strip() or settings.campaign.target_country
    city = input("  City: ").strip() or settings.campaign.target_city
    category = input("  Category: ").strip() or settings.campaign.target_business_category
    count_str = input("  Number of leads: ").strip()
    count = int(count_str) if count_str.isdigit() else settings.campaign.daily_lead_target

    print(f"\n  Starting campaign: {category} in {city}, {country} (target: {count})")

    from app.scheduler.daily_campaign import DailyCampaign
    campaign = DailyCampaign()
    summary = campaign.run(
        country=country,
        city=city,
        category=category,
        target_count=count,
    )

    print(f"\n  Campaign completed with status: {summary['status']}")


def _run_followups() -> None:
    """Process all due follow-ups."""
    from app.scheduler.followups import FollowUpScheduler
    scheduler = FollowUpScheduler()
    results = scheduler.run()
    print(f"\n  Follow-up results: {json.dumps(results, indent=2)}")
