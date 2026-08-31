"""
Web Dashboard.
Flask-based dashboard for monitoring campaigns, viewing leads, and taking actions.
Accessible via browser at http://localhost:5000
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, date
from pathlib import Path

from flask import Flask, render_template_string, request, jsonify, redirect, url_for

# Ensure project root is on path
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from app.config.settings import settings
from app.database import CampaignRepository, FollowUpRepository, LeadRepository
from app.database.models import init_db

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)


def _base(content: str, title: str, active_page: str) -> str:
    """Render base template with content."""
    return render_template_string(
        """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>""" + title + """ - Lead Generation Agent</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; color: #333; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header { background: #2c3e50; color: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; }
        .header h1 { font-size: 24px; margin-bottom: 10px; }
        .header p { opacity: 0.8; }
        .nav { background: white; padding: 10px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .nav a { display: inline-block; padding: 10px 20px; text-decoration: none; color: #2c3e50; border-radius: 4px; margin-right: 10px; }
        .nav a:hover { background: #ecf0f1; }
        .nav a.active { background: #3498db; color: white; }
        .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h2 { color: #2c3e50; margin-bottom: 15px; font-size: 18px; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .stat { text-align: center; padding: 20px; background: #f8f9fa; border-radius: 8px; }
        .stat .number { font-size: 32px; font-weight: bold; color: #3498db; }
        .stat .label { color: #666; margin-top: 5px; }
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }
        th { background: #f8f9fa; font-weight: 600; }
        tr:hover { background: #f5f5f5; }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; text-decoration: none; display: inline-block; }
        .btn-primary { background: #3498db; color: white; }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        .btn-warning { background: #f39c12; color: white; }
        .btn-sm { padding: 4px 8px; font-size: 12px; }
        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: 500; }
        .form-group input, .form-group select { width: 100%%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        .status-badge { padding: 4px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; }
        .status-sent { background: #d4edda; color: #155724; }
        .status-pending { background: #fff3cd; color: #856404; }
        .status-failed { background: #f8d7da; color: #721c24; }
        .status-draft { background: #e2e3e5; color: #383d41; }
        .footer { text-align: center; padding: 20px; color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AI Lead Generation Agent</h1>
            <p>Dashboard &amp; Management Interface</p>
        </div>
        <div class="nav">
            <a href="/" class="{{ 'active' if active_page == 'dashboard' else '' }}">Dashboard</a>
            <a href="/leads" class="{{ 'active' if active_page == 'leads' else '' }}">Leads</a>
            <a href="/campaign" class="{{ 'active' if active_page == 'campaign' else '' }}">Campaign</a>
            <a href="/followups" class="{{ 'active' if active_page == 'followups' else '' }}">Follow-ups</a>
            <a href="/config" class="{{ 'active' if active_page == 'config' else '' }}">Config</a>
        </div>
        """ + content + """
        <div class="footer">
            <p>AI Lead Generation Agent | """ + date.today().isoformat() + """</p>
        </div>
    </div>
</body>
</html>
""",
        active_page=active_page,
    )


@app.route("/")
def dashboard():
    """Main dashboard view."""
    init_db()

    lead_repo = LeadRepository()
    followup_repo = FollowUpRepository()

    today_leads = lead_repo.get_qualified_leads_for_date()
    all_qualified = lead_repo.get_all_qualified()
    due_3day = followup_repo.get_due_followups_3day()
    due_7day = followup_repo.get_due_followups_7day()

    content = f"""
<div class="card">
    <h2>Today's Campaign</h2>
    <div class="stats">
        <div class="stat">
            <div class="number">{settings.campaign.daily_lead_target}</div>
            <div class="label">Target Leads</div>
        </div>
        <div class="stat">
            <div class="number">{len(today_leads)}</div>
            <div class="label">Today's Leads</div>
        </div>
        <div class="stat">
            <div class="number">{len(all_qualified)}</div>
            <div class="label">Total Qualified</div>
        </div>
        <div class="stat">
            <div class="number">{len(due_3day) + len(due_7day)}</div>
            <div class="label">Follow-ups Due</div>
        </div>
    </div>
</div>

<div class="card">
    <h2>Quick Actions</h2>
    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
        <a href="/campaign/run" class="btn btn-primary">Run Campaign</a>
        <a href="/followups/run" class="btn btn-success">Process Follow-ups</a>
        <a href="/leads" class="btn btn-warning">View Leads</a>
        <a href="/config" class="btn">View Config</a>
    </div>
    <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 4px;">
        <strong>Modes:</strong>
        Dry Run: {"ON" if settings.campaign.dry_run else "OFF"} |
        Review Mode: {"ON" if settings.campaign.review_mode else "OFF"}
    </div>
</div>

<div class="card">
    <h2>Recent Leads</h2>
"""

    if all_qualified:
        content += """
    <table>
        <thead>
            <tr>
                <th>ID</th><th>Business</th><th>Category</th><th>City</th>
                <th>Score</th><th>Status</th><th>Actions</th>
            </tr>
        </thead>
        <tbody>
"""
        for lead in all_qualified[:10]:
            status_class = "status-sent" if lead.is_outreach_lead else ("status-pending" if lead.is_qualified else "status-draft")
            status_text = "Outreach" if lead.is_outreach_lead else ("Qualified" if lead.is_qualified else "New")
            approve_btn = f'<a href="/leads/{lead.id}/approve" class="btn btn-sm btn-success">Approve</a>' if not lead.is_outreach_lead and lead.is_qualified else ""
            content += f"""
            <tr>
                <td>{lead.id}</td>
                <td>{lead.business_name}</td>
                <td>{lead.business_category}</td>
                <td>{lead.city}</td>
                <td>{lead.lead_score}</td>
                <td><span class="status-badge {status_class}">{status_text}</span></td>
                <td>
                    <a href="/leads/{lead.id}" class="btn btn-sm btn-primary">View</a>
                    {approve_btn}
                </td>
            </tr>"""
        content += """
        </tbody>
    </table>"""
    else:
        content += "<p>No leads found. Run a campaign to get started.</p>"

    content += "</div>"

    return _base(content, "Dashboard", "dashboard")


@app.route("/leads")
def leads_list():
    """List all leads."""
    init_db()
    lead_repo = LeadRepository()
    leads = lead_repo.get_all_qualified()

    rows = ""
    for lead in leads:
        status_class = "status-sent" if lead.is_outreach_lead else ("status-pending" if lead.is_qualified else "status-draft")
        status_text = "Outreach" if lead.is_outreach_lead else ("Qualified" if lead.is_qualified else "New")
        approve_btn = f'<a href="/leads/{lead.id}/approve" class="btn btn-sm btn-success">Approve</a>' if not lead.is_outreach_lead and lead.is_qualified else ""
        reject_btn = f'<a href="/leads/{lead.id}/reject" class="btn btn-sm btn-danger">Reject</a>' if not lead.is_outreach_lead and lead.is_qualified else ""
        rows += f"""
        <tr>
            <td>{lead.id}</td>
            <td>{lead.business_name}</td>
            <td>{lead.business_category}</td>
            <td>{lead.city}</td>
            <td>{lead.country}</td>
            <td>{lead.lead_score}</td>
            <td>{lead.source}</td>
            <td><span class="status-badge {status_class}">{status_text}</span></td>
            <td>
                <a href="/leads/{lead.id}" class="btn btn-sm btn-primary">View</a>
                {approve_btn}
                {reject_btn}
            </td>
        </tr>"""

    content = f"""
<div class="card">
    <h2>All Qualified Leads ({len(leads)})</h2>
    <table>
        <thead>
            <tr>
                <th>ID</th><th>Business</th><th>Category</th><th>City</th>
                <th>Country</th><th>Score</th><th>Source</th><th>Status</th><th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {rows}
        </tbody>
    </table>
</div>"""

    return _base(content, "Leads", "leads")


@app.route("/leads/<int:lead_id>")
def lead_detail(lead_id):
    """Show detailed view of a single lead."""
    init_db()
    lead_repo = LeadRepository()
    lead = lead_repo.get_lead(lead_id)

    if not lead:
        return "Lead not found", 404

    approve_btn = f'<a href="/leads/{lead.id}/approve" class="btn btn-success">Approve &amp; Send</a>' if not lead.is_outreach_lead and lead.is_qualified else ""
    reject_btn = f'<a href="/leads/{lead.id}/reject" class="btn btn-danger">Reject</a>' if not lead.is_outreach_lead and lead.is_qualified else ""

    content = f"""
<div class="card">
    <h2>Lead #{lead.id}: {lead.business_name}</h2>
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
        <div>
            <h3>Business Information</h3>
            <p><strong>Name:</strong> {lead.business_name}</p>
            <p><strong>Category:</strong> {lead.business_category}</p>
            <p><strong>Country:</strong> {lead.country}</p>
            <p><strong>City:</strong> {lead.city}</p>
            <p><strong>Address:</strong> {lead.address or 'N/A'}</p>
            <p><strong>Phone:</strong> {lead.phone or 'N/A'}</p>
            <p><strong>Email:</strong> {lead.email or 'N/A'}</p>
            <p><strong>Website:</strong> {lead.website or 'N/A'}</p>
            <p><strong>Maps:</strong> {lead.google_maps_url or 'N/A'}</p>
        </div>
        <div>
            <h3>Analysis</h3>
            <p><strong>Score:</strong> {lead.lead_score}</p>
            <p><strong>Qualified:</strong> {'Yes' if lead.is_qualified else 'No'}</p>
            <p><strong>Source:</strong> {lead.source}</p>
            <p><strong>Research:</strong> {(lead.business_research or 'N/A')[:200]}</p>
            <p><strong>Problems:</strong> {(lead.potential_problem or 'N/A')[:200]}</p>
            <p><strong>Service:</strong> {lead.recommended_service or 'N/A'}</p>
            <p><strong>AI Solution:</strong> {lead.recommended_ai_solution or 'N/A'}</p>
        </div>
    </div>
    <div style="margin-top: 20px;">
        <h3>Outreach Status</h3>
        <p><strong>Outreach Lead:</strong> {'Yes' if lead.is_outreach_lead else 'No'}</p>
        <p><strong>Notes:</strong> {(lead.notes or 'N/A')[:500]}</p>
    </div>
    <div style="margin-top: 20px; display: flex; gap: 10px;">
        {approve_btn}
        {reject_btn}
        <a href="/leads" class="btn">Back to List</a>
    </div>
</div>"""

    return _base(content, f"Lead #{lead.id}", "leads")


@app.route("/leads/<int:lead_id>/approve")
def approve_lead(lead_id):
    """Approve a lead for outreach."""
    init_db()
    from app.agents.outreach import OutreachAgent
    outreach = OutreachAgent()
    result = outreach.approve_and_send(lead_id)
    return redirect(url_for("lead_detail", lead_id=lead_id))


@app.route("/leads/<int:lead_id>/reject")
def reject_lead(lead_id):
    """Reject a lead."""
    init_db()
    lead_repo = LeadRepository()
    lead_repo.update_lead(lead_id, {"is_outreach_lead": False})
    return redirect(url_for("leads_list"))


@app.route("/campaign")
def campaign_page():
    """Campaign management page."""
    init_db()
    campaign_repo = CampaignRepository()
    today_run = campaign_repo.get_today_run()

    run_info = ""
    if today_run:
        run_info = f"""
    <div style="margin-top: 20px;">
        <h3>Today's Campaign</h3>
        <p><strong>Status:</strong> {today_run.status}</p>
        <p><strong>Discovered:</strong> {today_run.discovered_count}</p>
        <p><strong>Qualified:</strong> {today_run.qualified_count}</p>
        <p><strong>Final:</strong> {today_run.final_count}</p>
        <p><strong>Emails Sent:</strong> {today_run.emails_sent}</p>
        <p><strong>WhatsApp Sent:</strong> {today_run.whatsapp_sent}</p>
    </div>"""

    content = f"""
<div class="card">
    <h2>Campaign Management</h2>
    <div style="margin-bottom: 20px;">
        <h3>Run New Campaign</h3>
        <form action="/campaign/run" method="get">
            <div class="form-group">
                <label>Country:</label>
                <input type="text" name="country" value="{settings.campaign.target_country}">
            </div>
            <div class="form-group">
                <label>City:</label>
                <input type="text" name="city" value="{settings.campaign.target_city}">
            </div>
            <div class="form-group">
                <label>Category:</label>
                <input type="text" name="category" value="{settings.campaign.target_business_category}">
            </div>
            <div class="form-group">
                <label>Number of Leads:</label>
                <input type="number" name="count" value="{settings.campaign.daily_lead_target}">
            </div>
            <button type="submit" class="btn btn-primary">Run Campaign</button>
        </form>
    </div>
    {run_info}
</div>"""

    return _base(content, "Campaign", "campaign")


@app.route("/campaign/run")
def run_campaign():
    """Run a campaign with parameters."""
    country = request.args.get("country", settings.campaign.target_country)
    city = request.args.get("city", settings.campaign.target_city)
    category = request.args.get("category", settings.campaign.target_business_category)
    count = int(request.args.get("count", settings.campaign.daily_lead_target))

    from app.scheduler.daily_campaign import DailyCampaign
    campaign = DailyCampaign()
    summary = campaign.run(
        country=country,
        city=city,
        category=category,
        target_count=count,
    )

    content = f"""
<div class="card">
    <h2>Campaign Results</h2>
    <div class="stats">
        <div class="stat">
            <div class="number">{summary['discovered']}</div>
            <div class="label">Discovered</div>
        </div>
        <div class="stat">
            <div class="number">{summary['qualified']}</div>
            <div class="label">Qualified</div>
        </div>
        <div class="stat">
            <div class="number">{summary['final_leads']}</div>
            <div class="label">Final Leads</div>
        </div>
        <div class="stat">
            <div class="number">{summary['emails_sent']}</div>
            <div class="label">Emails Sent</div>
        </div>
    </div>
    <div style="margin-top: 20px;">
        <p><strong>Status:</strong> {summary['status']}</p>
        <a href="/leads" class="btn btn-primary">View Leads</a>
        <a href="/" class="btn">Back to Dashboard</a>
    </div>
</div>"""

    return _base(content, "Campaign Results", "campaign")


@app.route("/followups")
def followups_page():
    """Follow-up management page."""
    init_db()
    followup_repo = FollowUpRepository()
    due_3day = followup_repo.get_due_followups_3day()
    due_7day = followup_repo.get_due_followups_7day()

    rows_3day = ""
    for state in due_3day:
        rows_3day += f"""
        <tr>
            <td>{state.lead_id}</td>
            <td>{state.initial_status}</td>
            <td><a href="/leads/{state.lead_id}" class="btn btn-sm btn-primary">View Lead</a></td>
        </tr>"""

    due_3day_table = ""
    if due_3day:
        due_3day_table = f"""
    <div class="card">
        <h2>3-Day Follow-ups Due</h2>
        <table>
            <thead><tr><th>Lead ID</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>{rows_3day}</tbody>
        </table>
    </div>"""

    content = f"""
<div class="card">
    <h2>Follow-up Management</h2>
    <div class="stats">
        <div class="stat">
            <div class="number">{len(due_3day)}</div>
            <div class="label">3-Day Follow-ups Due</div>
        </div>
        <div class="stat">
            <div class="number">{len(due_7day)}</div>
            <div class="label">7-Day Follow-ups Due</div>
        </div>
    </div>
    <div style="margin-top: 20px;">
        <a href="/followups/run" class="btn btn-success">Process All Follow-ups</a>
        <a href="/followups/run/3day" class="btn btn-warning">Process 3-Day Only</a>
        <a href="/followups/run/7day" class="btn btn-warning">Process 7-Day Only</a>
    </div>
</div>
{due_3day_table}"""

    return _base(content, "Follow-ups", "followups")


@app.route("/followups/run")
@app.route("/followups/run/<followup_type>")
def run_followups(followup_type="all"):
    """Process follow-ups."""
    init_db()
    from app.scheduler.followups import FollowUpScheduler
    scheduler = FollowUpScheduler()

    if followup_type == "3day":
        results = scheduler.run_3day_only()
    elif followup_type == "7day":
        results = scheduler.run_7day_only()
    else:
        results = scheduler.run()

    content = f"""
<div class="card">
    <h2>Follow-up Processing Complete</h2>
    <pre>{json.dumps(results, indent=2)}</pre>
    <div style="margin-top: 20px;">
        <a href="/followups" class="btn btn-primary">Back to Follow-ups</a>
        <a href="/" class="btn">Back to Dashboard</a>
    </div>
</div>"""

    return _base(content, "Follow-up Results", "followups")


@app.route("/config")
def config_page():
    """Configuration status page."""
    llm_status = "OK" if settings.llm.is_configured else "Missing"
    search_status = "OK" if settings.search.is_configured else "Missing"
    maps_status = "OK" if settings.google_maps.is_configured else "Missing"
    sheets_status = "OK" if settings.google_sheets.is_configured else "Missing"
    email_status = "OK" if settings.email.is_configured else "Missing"
    whatsapp_status = "OK" if settings.whatsapp.is_configured else "Missing"

    content = f"""
<div class="card">
    <h2>Configuration Status</h2>
    <div class="stats">
        <div class="stat"><div class="number">{llm_status}</div><div class="label">LLM API</div></div>
        <div class="stat"><div class="number">{search_status}</div><div class="label">Search API</div></div>
        <div class="stat"><div class="number">{maps_status}</div><div class="label">Google Maps</div></div>
        <div class="stat"><div class="number">{sheets_status}</div><div class="label">Google Sheets</div></div>
        <div class="stat"><div class="number">{email_status}</div><div class="label">Email</div></div>
        <div class="stat"><div class="number">{whatsapp_status}</div><div class="label">WhatsApp</div></div>
    </div>
</div>

<div class="card">
    <h2>Campaign Settings</h2>
    <p><strong>Target Country:</strong> {settings.campaign.target_country or 'Not set'}</p>
    <p><strong>Target City:</strong> {settings.campaign.target_city or 'Not set'}</p>
    <p><strong>Target Category:</strong> {settings.campaign.target_business_category or 'Not set'}</p>
    <p><strong>Daily Lead Target:</strong> {settings.campaign.daily_lead_target}</p>
    <p><strong>Score Threshold:</strong> {settings.campaign.lead_score_threshold}</p>
    <p><strong>Dry Run:</strong> {"ON" if settings.campaign.dry_run else "OFF"}</p>
    <p><strong>Review Mode:</strong> {"ON" if settings.campaign.review_mode else "OFF"}</p>
</div>

<div class="card">
    <h2>Business Information</h2>
    <p><strong>Name:</strong> {settings.my_business.name or 'Not set'}</p>
    <p><strong>Email:</strong> {settings.my_business.email or 'Not set'}</p>
    <p><strong>Website:</strong> {settings.my_business.website_url or 'Not set'}</p>
    <p><strong>Fiverr:</strong> {settings.my_business.fiverr_url or 'Not set'}</p>
    <p><strong>LinkedIn:</strong> {settings.my_business.linkedin_url or 'Not set'}</p>
</div>"""

    return _base(content, "Configuration", "config")


def run_web_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the web dashboard."""
    init_db()
    print(f"\nStarting web dashboard at http://{host}:{port}")
    print("Press Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_web_dashboard(debug=True)
