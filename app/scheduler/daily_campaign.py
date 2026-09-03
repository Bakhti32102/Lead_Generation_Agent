"""
Daily Campaign Scheduler.
Orchestrates the entire pipeline: Search → Verify → Research → Analyze → Score → Outreach → Sheets.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from typing import Dict, List

from app.config.settings import settings
from app.database import CampaignRepository, CounterRepository, FollowUpRepository, LeadRepository
from app.database.models import init_db
from app.integrations.google_sheets import sheets_client

logger = logging.getLogger(__name__)


class DailyCampaign:
    """Executes one complete daily lead generation campaign."""

    def __init__(self):
        self.lead_repo = LeadRepository()
        self.followup_repo = FollowUpRepository()
        self.campaign_repo = CampaignRepository()
        self.counter_repo = CounterRepository()

    def run(
        self,
        country: str = "",
        city: str = "",
        category: str = "",
        target_count: int = 0,
        search_google_maps: bool = True,
        search_google: bool = True,
        search_linkedin: bool = True,
        search_recent_requirements: bool = True,
    ) -> Dict:
        """
        Run a complete daily campaign. Returns a summary dict.
        """
        # Use defaults from config if not provided
        country = country or settings.campaign.target_country
        city = city or settings.campaign.target_city
        category = category or settings.campaign.target_business_category
        target_count = target_count or settings.campaign.daily_lead_target

        logger.info(
            f"=== Starting Daily Campaign ===\n"
            f"  Country: {country}\n"
            f"  City: {city}\n"
            f"  Category: {category}\n"
            f"  Target: {target_count}"
        )

        # Initialize database
        init_db()

        # Create campaign run record
        run = self.campaign_repo.create_run({
            "target_country": country,
            "target_city": city,
            "target_category": category,
            "target_count": target_count,
        })

        summary = {
            "target_country": country,
            "target_city": city,
            "target_category": category,
            "target_count": target_count,
            "discovered": 0,
            "qualified": 0,
            "final_leads": 0,
            "emails_sent": 0,
            "whatsapp_sent": 0,
            "followups_3day": 0,
            "followups_7day": 0,
            "failed": 0,
            "skipped": 0,
            "interested": 0,
            "human_required": 0,
            "status": "running",
        }

        try:
            # ── Step 1: Discovery ──
            from app.agents.lead_discovery import LeadDiscoveryAgent
            discovery = LeadDiscoveryAgent()
            prospects = discovery.discover(
                country=country,
                city=city,
                category=category,
                max_results=target_count * 3,  # Discover more than needed
                search_google_maps=search_google_maps,
                search_google=search_google,
                search_linkedin=search_linkedin,
                search_recent_requirements=search_recent_requirements,
            )
            summary["discovered"] = len(prospects)
            logger.info(f"Discovered: {len(prospects)} prospects")

            # ── Step 2: Verification ──
            from app.agents.lead_verification import LeadVerificationAgent
            verification = LeadVerificationAgent()
            prospects = verification.verify_batch(prospects)
            logger.info(f"After verification: {len(prospects)}")

            # ── Step 3: Business Research ──
            from app.agents.business_research import BusinessResearchAgent
            research = BusinessResearchAgent()
            for p in prospects:
                try:
                    research.research(p)
                except Exception as e:
                    logger.error(f"Research failed for {p.business_name}: {e}")

            # ── Step 4: Problem Analysis ──
            from app.agents.problem_analysis import ProblemAnalysisAgent
            problem_agent = ProblemAnalysisAgent()
            for p in prospects:
                try:
                    problem_agent.analyze(p, category)
                except Exception as e:
                    logger.error(f"Problem analysis failed for {p.business_name}: {e}")

            # ── Step 5: Service Matching ──
            from app.agents.solution_matching import SolutionMatchingAgent
            matching = SolutionMatchingAgent()
            for p in prospects:
                try:
                    matching.match(p)
                except Exception as e:
                    logger.error(f"Solution matching failed for {p.business_name}: {e}")

            # ── Step 6: Scoring ──
            from app.agents.lead_scoring import LeadScoringAgent
            scoring = LeadScoringAgent(
                target_category=category,
                target_country=country,
                target_city=city,
            )
            prospects = scoring.score_batch(prospects)
            qualified = [p for p in prospects if p.is_qualified]
            summary["qualified"] = len(qualified)

            # ── Step 7: Select Top Leads ──
            final_leads = scoring.select_top_leads(prospects, target_count)
            summary["final_leads"] = len(final_leads)

            # ── Step 8: Save to Database + Generate Messages ──
            from app.agents.personalization import PersonalizationAgent
            personalizer = PersonalizationAgent()
            from app.agents.outreach import OutreachAgent
            outreach = OutreachAgent()

            for p in final_leads:
                # Save to database
                lead_data = self._prospect_to_db(p, country, city, category)
                db_lead = self.lead_repo.save_lead(lead_data)
                self.followup_repo.create_state(db_lead.id)

                # Generate personalized message
                message = personalizer.generate_message(p)

                # ── Review Mode: Display full outreach message ──
                # Wrapped in try/except so a console encoding error (e.g.
                # UnicodeEncodeError on Windows cp1252) cannot prevent
                # lead persistence and outreach.
                if settings.campaign.review_mode or settings.campaign.dry_run:
                    try:
                        self._display_outreach_message(p, message, lead_db_id=db_lead.id)
                    except Exception as display_exc:
                        logger.warning(
                            f"Display failed for {p.business_name} (non-critical): "
                            f"{type(display_exc).__name__}: {display_exc}"
                        )

                # Send outreach
                result = outreach.send_initial(p, message, db_lead.id)

                if result["success"]:
                    if result["channel"] == "email":
                        summary["emails_sent"] += 1
                    elif result["channel"] == "whatsapp":
                        summary["whatsapp_sent"] += 1

                    # Update database with message
                    self.lead_repo.update_lead(db_lead.id, {
                        "is_outreach_lead": True,
                        "notes": message,
                    })
                else:
                    summary["failed"] += 1
                    self.lead_repo.update_lead(db_lead.id, {
                        "is_outreach_lead": True,
                        "notes": f"Message generated but not sent: {result.get('status', 'unknown')}",
                    })

                # Save to Google Sheets
                self._save_to_sheets(p, db_lead.id, message, result)

            # ── Step 9: Process Follow-ups ──
            from app.agents.follow_up import FollowUpAgent
            followup_agent = FollowUpAgent()
            followup_results = followup_agent.process_all_followups()
            summary["followups_3day"] = followup_results.get("3day_sent", 0)
            summary["followups_7day"] = followup_results.get("7day_sent", 0)
            summary["skipped"] += followup_results.get("3day_skipped", 0) + followup_results.get("7day_skipped", 0)

            summary["status"] = "completed"

        except Exception as e:
            logger.error(f"Campaign failed: {e}", exc_info=True)
            summary["status"] = "failed"
            summary["error"] = str(e)

        finally:
            # Update campaign run record
            self.campaign_repo.update_run(run.id, {
                "completed_at": _dt.datetime.utcnow(),
                "discovered_count": summary["discovered"],
                "qualified_count": summary["qualified"],
                "final_count": summary["final_leads"],
                "emails_sent": summary["emails_sent"],
                "whatsapp_sent": summary["whatsapp_sent"],
                "followups_3day": summary["followups_3day"],
                "followups_7day": summary["followups_7day"],
                "failed": summary["failed"],
                "skipped": summary["skipped"],
                "status": summary["status"],
            })

            # Generate daily report
            self._generate_report(summary)

        return summary

    def _prospect_to_db(
        self, prospect, country: str, city: str, category: str
    ) -> dict:
        """Convert a RawProspect to a database lead dict."""
        return {
            "business_name": prospect.business_name,
            "business_category": prospect.business_category or category,
            "country": prospect.country or country,
            "city": prospect.city or city,
            "address": prospect.address,
            "phone": prospect.phone,
            "email": prospect.email,
            "website": prospect.website,
            "google_maps_url": prospect.google_maps_url,
            "source": prospect.source,
            "source_url": prospect.source_url,
            "posted_date": prospect.posted_date,
            "business_research": prospect.business_research,
            "potential_problem": prospect.potential_problem,
            "recommended_service": prospect.recommended_service,
            "recommended_ai_solution": prospect.recommended_ai_solution,
            "lead_score": prospect.lead_score,
            "is_qualified": prospect.is_qualified,
            "dedup_website": prospect.website.lower().strip() if prospect.website else "",
            "dedup_email": prospect.email.lower().strip() if prospect.email else "",
            "dedup_phone": prospect.phone.strip() if prospect.phone else "",
            "dedup_maps_url": prospect.google_maps_url.strip() if prospect.google_maps_url else "",
        }

    def _save_to_sheets(self, prospect, db_id: int, message: str, send_result: dict) -> None:
        """Save a lead to Google Sheets."""
        if not sheets_client.is_configured:
            return

        try:
            now = _dt.date.today().isoformat()
            row_data = {
                "Lead ID": str(db_id),
                "Date Found": now,
                "Business Name": prospect.business_name,
                "Business Category": prospect.business_category,
                "Country": prospect.country,
                "City": prospect.city,
                "Address": prospect.address,
                "Phone": prospect.phone,
                "Email": prospect.email,
                "Website": prospect.website,
                "Google Maps URL": prospect.google_maps_url,
                "Source": prospect.source,
                "Source URL": prospect.source_url,
                "Posted Date": prospect.posted_date,
                "Requirement": prospect.requirement_text,
                "Business Research": prospect.business_research[:500],
                "Potential Problem": prospect.potential_problem,
                "Recommended Service": prospect.recommended_service,
                "Recommended AI Solution": prospect.recommended_ai_solution,
                "Lead Score": str(prospect.lead_score),
                "Contact Channel": send_result.get("channel", ""),
                "Initial Message": message[:500] if message else "",
                "Initial Contact Date": now if send_result.get("status") == "sent" else "",
                "Initial Contact Status": {
                    "sent": "Sent",
                    "draft": "Dry Run",
                    "pending_review": "Pending Review",
                    "prepared": "Prepared",
                    "failed": "Failed",
                }.get(send_result.get("status", ""), "Pending"),
                "Follow-up Status": "Active",
                "Do Not Contact": "No",
                "Human Required": "No",
            }

            row_num = sheets_client.append_lead(row_data)
            self.lead_repo.update_lead(db_id, {"sheets_row_id": str(row_num)})

            state = self.followup_repo.get_by_lead_id(db_id)
            if state:
                # Update with row number for future updates
                pass

        except Exception as e:
            logger.error(f"Failed to save lead to Google Sheets: {e}")

    def _display_outreach_message(
        self, prospect, message: str, lead_db_id: int = 0
    ) -> None:
        """Display the full outreach message for human review.

        Prints a clean, readable block showing the email subject,
        complete body text, and channel for each qualified lead.
        """
        from app.integrations.email import email_client
        from app.integrations.whatsapp import whatsapp_client

        # Determine channel
        channel = "whatsapp"
        if prospect.email and email_client.is_configured:
            channel = "email"
        elif prospect.phone and whatsapp_client.is_configured:
            channel = "whatsapp"
        else:
            channel = "email"  # default display

        subject = ""
        if channel == "email":
            subject = f"Quick question regarding {prospect.business_name}'s client bookings"

        border = "=" * 60
        thin_border = "-" * 60

        print(f"\n{border}")
        print(f"  OUTREACH REVIEW — Lead #{lead_db_id}")
        print(border)
        print(f"  Business:   {prospect.business_name}")
        print(f"  Category:   {prospect.business_category}")
        print(f"  Location:   {prospect.city}, {prospect.country}")
        print(f"  Score:      {prospect.lead_score}")
        print(f"  Channel:    {channel.upper()}")
        if channel == "email":
            print(f"  To:         {prospect.email}")
        else:
            print(f"  To:         {prospect.phone}")
        print(thin_border)

        if channel == "email" and subject:
            print(f"  Subject:    {subject}")
            print(thin_border)

        print(f"  Message:")
        for line in message.split("\n"):
            try:
                print(f"  {line}")
            except UnicodeEncodeError:
                # Preserve content where possible; replace only the
                # characters the console cannot render.
                print(f"  {line.encode('ascii', 'replace').decode('ascii')}")

        print(border)
        print()

    def _generate_report(self, summary: Dict) -> str:
        """Generate and log a daily report."""
        report = f"""
+--------------------------------------------------+
|        Daily Lead Generation Report              |
+--------------------------------------------------+
|                                                  |
|  Target:                                         |
|  Country:    {summary['target_country']:<35s} |
|  City:       {summary['target_city']:<35s} |
|  Category:   {summary['target_category']:<35s} |
|                                                  |
|  Requested Leads:  {summary['target_count']:<29d} |
|  Discovered:       {summary['discovered']:<29d} |
|  Qualified Leads:  {summary['qualified']:<29d} |
|  Final Leads:      {summary['final_leads']:<29d} |
|                                                  |
|  Emails Sent:       {summary['emails_sent']:<28d} |
|  WhatsApp Sent:     {summary['whatsapp_sent']:<28d} |
|  3-Day Follow-ups:  {summary['followups_3day']:<28d} |
|  7-Day Follow-ups:  {summary['followups_7day']:<28d} |
|                                                  |
|  Failed:    {summary['failed']:<37d} |
|  Skipped:   {summary['skipped']:<37d} |
|                                                  |
|  Status: {summary['status']:<40s} |
+--------------------------------------------------+
"""
        logger.info(report)
        try:
            print(report)
        except UnicodeEncodeError:
            # Windows cp1252 console cannot render some Unicode.
            # Fall back to ASCII-safe rendering — the report is already
            # saved to file with full UTF-8 content.
            try:
                print(report.encode("ascii", "replace").decode("ascii"))
            except Exception:
                pass  # Last resort: swallow display error, report is in log/file

        # Save report to file
        from app.config.settings import LOG_DIR
        report_file = LOG_DIR / f"report_{_dt.date.today().isoformat()}.txt"
        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(report)
        except Exception as e:
            logger.error(f"Failed to save report: {e}")

        return report
