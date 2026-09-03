"""
Web Dashboard.
Flask-based dashboard for monitoring campaigns, viewing leads, and taking actions.
Accessible via browser at http://localhost:5000

Supports real-time campaign progress via Server-Sent Events (SSE).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import sys
import threading
import time
import uuid
from datetime import datetime, date
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, Response

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

# ── SSE Event Bus ──────────────────────────────────────────────────────────
# Global event bus: maps session_id -> queue of SSE events
_event_queues: dict[str, queue.Queue] = {}
_event_lock = threading.Lock()
_campaign_active: dict[str, bool] = {}


def _publish_event(session_id: str, event: dict) -> None:
    """Publish an event to a specific session's SSE queue."""
    with _event_lock:
        q = _event_queues.get(session_id)
    if q:
        q.put(event)


def _create_session() -> str:
    """Create a new SSE session and return its ID."""
    sid = uuid.uuid4().hex[:12]
    with _event_lock:
        _event_queues[sid] = queue.Queue()
        _campaign_active[sid] = False
    return sid


def _cleanup_session(sid: str) -> None:
    """Remove a session's queue."""
    with _event_lock:
        _event_queues.pop(sid, None)
        _campaign_active.pop(sid, None)


def _is_campaign_active(sid: str) -> bool:
    with _event_lock:
        return _campaign_active.get(sid, False)


def _set_campaign_active(sid: str, active: bool) -> None:
    with _event_lock:
        _campaign_active[sid] = active


# ── Base Template ──────────────────────────────────────────────────────────

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
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
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


# ── Dashboard Routes ───────────────────────────────────────────────────────

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
        <a href="/campaign" class="btn btn-primary">Run Campaign</a>
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


# ── Campaign Routes (with SSE live streaming) ─────────────────────────────

@app.route("/campaign")
def campaign_page():
    """Campaign management page with live terminal UI."""
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
<style>
    /* ── Live Campaign Styles ── */
    .campaign-form {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
    .campaign-form .form-group {{ margin-bottom: 0; }}
    .campaign-form .full-width {{ grid-column: 1 / -1; }}

    /* Stepper */
    .stepper {{ display: flex; justify-content: space-between; align-items: center; margin: 25px 0; position: relative; }}
    .stepper::before {{ content: ''; position: absolute; top: 20px; left: 40px; right: 40px; height: 3px; background: #e0e0e0; z-index: 0; }}
    .stepper .step {{ display: flex; flex-direction: column; align-items: center; z-index: 1; flex: 1; }}
    .stepper .step-icon {{
        width: 40px; height: 40px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 16px; font-weight: bold; color: #999;
        background: #e0e0e0; transition: all 0.4s ease;
        border: 3px solid transparent;
    }}
    .stepper .step-label {{
        margin-top: 8px; font-size: 12px; color: #999;
        text-align: center; font-weight: 500; transition: color 0.3s;
    }}
    .stepper .step.active .step-icon {{
        background: #3498db; color: white;
        border-color: #3498db;
        box-shadow: 0 0 0 4px rgba(52,152,219,0.25);
        animation: pulse 1.5s ease-in-out infinite;
    }}
    .stepper .step.active .step-label {{ color: #3498db; font-weight: 700; }}
    .stepper .step.done .step-icon {{ background: #27ae60; color: white; border-color: #27ae60; }}
    .stepper .step.done .step-label {{ color: #27ae60; }}
    .stepper .step.error .step-icon {{ background: #e74c3c; color: white; border-color: #e74c3c; }}
    .stepper .step.error .step-label {{ color: #e74c3c; }}

    @keyframes pulse {{
        0%, 100% {{ box-shadow: 0 0 0 4px rgba(52,152,219,0.25); }}
        50% {{ box-shadow: 0 0 0 8px rgba(52,152,219,0.1); }}
    }}

    /* Terminal Log Box */
    .terminal-wrap {{
        background: #0d1117; border-radius: 10px; overflow: hidden;
        box-shadow: 0 4px 20px rgba(0,0,0,0.3); margin-top: 20px;
        display: none;
    }}
    .terminal-wrap.visible {{ display: block; }}
    .terminal-bar {{
        background: #161b22; padding: 10px 16px;
        display: flex; align-items: center; gap: 8px;
        border-bottom: 1px solid #30363d;
    }}
    .terminal-dot {{ width: 12px; height: 12px; border-radius: 50%; }}
    .terminal-dot.red {{ background: #ff5f57; }}
    .terminal-dot.yellow {{ background: #febc2e; }}
    .terminal-dot.green {{ background: #28c840; }}
    .terminal-title {{ color: #8b949e; font-size: 12px; margin-left: 10px; font-family: monospace; }}
    .terminal-body {{
        padding: 16px; height: 340px; overflow-y: auto;
        font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
        font-size: 13px; line-height: 1.6;
    }}
    .terminal-body::-webkit-scrollbar {{ width: 6px; }}
    .terminal-body::-webkit-scrollbar-track {{ background: #0d1117; }}
    .terminal-body::-webkit-scrollbar-thumb {{ background: #30363d; border-radius: 3px; }}
    .terminal-line {{ white-space: pre-wrap; word-break: break-word; }}
    .terminal-line .ts {{ color: #484f58; }}
    .terminal-line .msg {{ color: #c9d1d9; }}
    .terminal-line.info .msg {{ color: #58a6ff; }}
    .terminal-line.success .msg {{ color: #3fb950; }}
    .terminal-line.warn .msg {{ color: #d29922; }}
    .terminal-line.error .msg {{ color: #f85149; }}
    .terminal-line.stage .msg {{ color: #bc8cff; font-weight: bold; }}

    /* Summary Bar */
    .summary-bar {{
        display: none; margin-top: 15px; padding: 15px;
        background: #f0fff4; border: 1px solid #c6f6d5; border-radius: 8px;
    }}
    .summary-bar.visible {{ display: block; }}
    .summary-bar.error {{ background: #fff5f5; border-color: #fed7d7; }}
    .summary-bar h3 {{ margin-bottom: 10px; }}
    .summary-bar .stats {{ display: flex; gap: 20px; flex-wrap: wrap; }}
    .summary-bar .stat {{ text-align: center; padding: 10px 15px; background: white; border-radius: 6px; min-width: 100px; }}
    .summary-bar .stat .number {{ font-size: 24px; font-weight: bold; color: #27ae60; }}
    .summary-bar .stat .label {{ font-size: 12px; color: #666; margin-top: 2px; }}
</style>

<div class="card">
    <h2>Campaign Management</h2>
    <div>
        <h3>Run New Campaign</h3>
        <form id="campaignForm" class="campaign-form" onsubmit="return startCampaign(event)">
            <div class="form-group">
                <label>Country:</label>
                <input type="text" name="country" id="f-country" value="{settings.campaign.target_country}">
            </div>
            <div class="form-group">
                <label>City:</label>
                <input type="text" name="city" id="f-city" value="{settings.campaign.target_city}">
            </div>
            <div class="form-group">
                <label>Category:</label>
                <input type="text" name="category" id="f-category" value="{settings.campaign.target_business_category}">
            </div>
            <div class="form-group">
                <label>Number of Leads:</label>
                <input type="number" name="count" id="f-count" value="{settings.campaign.daily_lead_target}">
            </div>
            <div class="form-group full-width" style="display:flex;gap:10px;align-items:flex-end;">
                <button type="submit" id="runBtn" class="btn btn-primary" style="padding:10px 30px;">
                    &#x1f680; Run Campaign
                </button>
                <span id="runStatus" style="color:#888;font-size:13px;padding-bottom:10px;"></span>
            </div>
        </form>
    </div>
</div>

<!-- Stepper -->
<div class="stepper" id="stepper" style="display:none;">
    <div class="step" id="step-discovery" data-step="discovery">
        <div class="step-icon">1</div>
        <div class="step-label">Discovery</div>
    </div>
    <div class="step" id="step-filtering" data-step="filtering">
        <div class="step-icon">2</div>
        <div class="step-label">Filtering</div>
    </div>
    <div class="step" id="step-verification" data-step="verification">
        <div class="step-icon">3</div>
        <div class="step-label">Verification</div>
    </div>
    <div class="step" id="step-research" data-step="research">
        <div class="step-icon">4</div>
        <div class="step-label">Research</div>
    </div>
    <div class="step" id="step-scoring" data-step="scoring">
        <div class="step-icon">5</div>
        <div class="step-label">Scoring</div>
    </div>
    <div class="step" id="step-saving" data-step="saving">
        <div class="step-icon">6</div>
        <div class="step-label">Saving</div>
    </div>
    <div class="step" id="step-complete" data-step="complete">
        <div class="step-icon">&#10003;</div>
        <div class="step-label">Complete</div>
    </div>
</div>

<!-- Terminal Log -->
<div class="terminal-wrap" id="terminalWrap">
    <div class="terminal-bar">
        <div class="terminal-dot red"></div>
        <div class="terminal-dot yellow"></div>
        <div class="terminal-dot green"></div>
        <span class="terminal-title" id="terminalTitle">campaign &mdash; live</span>
    </div>
    <div class="terminal-body" id="terminalBody"></div>
</div>

<!-- Summary -->
<div class="summary-bar" id="summaryBar">
    <h3 id="summaryTitle">Campaign Complete</h3>
    <div class="stats" id="summaryStats"></div>
</div>

<script>
const STEP_ORDER = ['discovery','filtering','verification','research','scoring','saving','complete'];
let eventSource = null;
let sessionId = null;
let sseConnected = false;
let sseRetryCount = 0;

function addTerminalLine(text, cls) {{
    const body = document.getElementById('terminalBody');
    const now = new Date().toLocaleTimeString('en-US', {{hour12:false}});
    const line = document.createElement('div');
    line.className = 'terminal-line ' + (cls || '');
    line.innerHTML = '<span class="ts">[' + now + ']</span> <span class="msg">' + text + '</span>';
    body.appendChild(line);
    body.scrollTop = body.scrollHeight;
}}

function setStepActive(stepName) {{
    STEP_ORDER.forEach(s => {{
        const el = document.getElementById('step-' + s);
        if (!el) return;
        if (s === stepName) {{
            el.className = 'step active';
        }} else if (STEP_ORDER.indexOf(s) < STEP_ORDER.indexOf(stepName)) {{
            el.className = 'step done';
        }} else {{
            el.className = 'step';
        }}
    }});
}}

function setStepError(stepName) {{
    const el = document.getElementById('step-' + stepName);
    if (el) el.className = 'step error';
}}

function showSummary(data) {{
    const bar = document.getElementById('summaryBar');
    const title = document.getElementById('summaryTitle');
    const stats = document.getElementById('summaryStats');
    const isFailed = data.status === 'failed';

    bar.className = 'summary-bar visible' + (isFailed ? ' error' : '');
    title.textContent = isFailed ? 'Campaign Failed' : 'Campaign Complete';

    stats.innerHTML = [
        {{ n: data.discovered || 0, l: 'Discovered' }},
        {{ n: data.qualified || 0, l: 'Qualified' }},
        {{ n: data.final_leads || 0, l: 'Final Leads' }},
        {{ n: data.emails_sent || 0, l: 'Emails Sent' }},
        {{ n: data.whatsapp_sent || 0, l: 'WhatsApp Sent' }},
    ].map(s => '<div class="stat"><div class="number">' + s.n + '</div><div class="label">' + s.l + '</div></div>').join('');
}}

function connectSSE(sid) {{
    if (eventSource) eventSource.close();
    sseConnected = false;
    sseRetryCount = 0;
    eventSource = new EventSource('/campaign/stream?sid=' + sid);

    eventSource.onopen = function() {{
        sseConnected = true;
        sseRetryCount = 0;
    }};

    eventSource.onmessage = function(e) {{
        try {{
            const data = JSON.parse(e.data);
            const type = data.type || '';

            if (type === 'log') {{
                addTerminalLine(data.message, data.level || '');
            }} else if (type === 'stage') {{
                setStepActive(data.stage);
                addTerminalLine('\\u2500\\u2500 ' + (data.label || data.stage) + ' \\u2500\\u2500', 'stage');
            }} else if (type === 'error') {{
                addTerminalLine(data.message, 'error');
            }} else if (type === 'done') {{
                setStepActive('complete');
                addTerminalLine('Campaign finished: ' + (data.status || 'completed'), 'success');
                showSummary(data.summary || {{}});
                document.getElementById('runBtn').disabled = false;
                document.getElementById('runBtn').innerHTML = '&#x1f680; Run Campaign';
                document.getElementById('runStatus').textContent = '';
                eventSource.close();
            }} else if (type === 'started') {{
                document.getElementById('terminalTitle').textContent = data.label || 'campaign \\u2014 live';
            }}
        }} catch(err) {{ console.error('SSE parse error', err); }}
    }};

    eventSource.onerror = function() {{
        // EventSource auto-reconnects; suppress transient disconnect warnings.
        // Only show a message if we were previously connected (real drop)
        // and only after a few retries to avoid spam during normal reconnects.
        if (sseConnected) {{
            sseRetryCount++;
            if (sseRetryCount <= 2) {{
                addTerminalLine('Reconnecting to stream...', 'info');
            }} else if (sseRetryCount === 3) {{
                addTerminalLine('Still reconnecting... proxy may be buffering.', 'warn');
            }}
            sseConnected = false;
        }}
    }};
}}

function startCampaign(e) {{
    e.preventDefault();

    const btn = document.getElementById('runBtn');
    btn.disabled = true;
    btn.innerHTML = '&#x23f3; Running...';
    document.getElementById('runStatus').textContent = 'Starting campaign...';

    // Show UI elements
    document.getElementById('stepper').style.display = 'flex';
    document.getElementById('terminalWrap').className = 'terminal-wrap visible';
    document.getElementById('summaryBar').className = 'summary-bar';
    document.getElementById('terminalBody').innerHTML = '';

    // Reset stepper
    STEP_ORDER.forEach(s => {{
        const el = document.getElementById('step-' + s);
        if (el) el.className = 'step';
    }});

    const params = new URLSearchParams({{
        country: document.getElementById('f-country').value,
        city: document.getElementById('f-city').value,
        category: document.getElementById('f-category').value,
        count: document.getElementById('f-count').value,
    }});

    fetch('/campaign/run-async?' + params.toString(), {{ method: 'POST' }})
        .then(r => r.json())
        .then(data => {{
            sessionId = data.session_id;
            document.getElementById('runStatus').textContent = 'Connected to live stream';
            connectSSE(sessionId);
        }})
        .catch(err => {{
            addTerminalLine('Failed to start campaign: ' + err.message, 'error');
            btn.disabled = false;
            btn.innerHTML = '&#x1f680; Run Campaign';
        }});

    return false;
}}
</script>
"""

    content += run_info

    return _base(content, "Campaign", "campaign")


@app.route("/campaign/run-async", methods=["POST"])
def run_campaign_async():
    """Start a campaign in a background thread and return a session ID for SSE streaming."""
    country = request.args.get("country", settings.campaign.target_country)
    city = request.args.get("city", settings.campaign.target_city)
    category = request.args.get("category", settings.campaign.target_business_category)
    count = int(request.args.get("count", settings.campaign.daily_lead_target))

    sid = _create_session()
    _set_campaign_active(sid, True)

    def _run():
        try:
            _publish_event(sid, {"type": "started", "label": f"Campaign: {category} in {city}, {country}"})
            _publish_event(sid, {"type": "stage", "stage": "discovery", "label": f"Discovery — {category} in {city}, {country}"})
            _publish_event(sid, {"type": "log", "message": f"Starting campaign: {category} in {city}, {country} (target: {count})", "level": "info"})

            # ── Step 1: Discovery ──
            from app.agents.lead_discovery import LeadDiscoveryAgent
            discovery = LeadDiscoveryAgent()

            # Attach a temporary log handler that streams discovery/
            # source log messages to the SSE client so the user can
            # see exactly which sources are running, whether fallback
            # triggers, and why.  Filtered to app.agents / app.sources
            # modules only — no secrets or internal debug noise.
            import logging as _log_mod
            _sse_handler_added = False

            class _SSELogHandler(_log_mod.Handler):
                def __init__(self, session_id: str):
                    super().__init__()
                    self._sid = session_id

                def emit(self, record: _log_mod.LogRecord) -> None:
                    if record.name.startswith(("app.agents", "app.sources")):
                        _publish_event(self._sid, {
                            "type": "log",
                            "message": record.getMessage(),
                            "level": record.levelname.lower(),
                        })

            _sse_handler = _SSELogHandler(sid)
            _sse_handler.setLevel(_log_mod.INFO)
            _log_mod.getLogger().addHandler(_sse_handler)
            _sse_handler_added = True

            prospects = discovery.discover(
                country=country,
                city=city,
                category=category,
                max_results=count * 3,
            )
            _publish_event(sid, {"type": "log", "message": f"Discovery complete: {len(prospects)} prospects from all sources", "level": "success"})

            # ── Step 2: Dedup / Filtering ──
            _publish_event(sid, {"type": "stage", "stage": "filtering", "label": "Filtering & Deduplication"})
            _publish_event(sid, {"type": "log", "message": f"Running deduplication on {len(prospects)} prospects..."})

            # Dedup happens inside verification, but we show it here
            seen = set()
            unique = []
            for p in prospects:
                key = (p.business_name or "").lower().strip()
                if key and key not in seen:
                    seen.add(key)
                    unique.append(p)
            removed = len(prospects) - len(unique)
            if removed:
                _publish_event(sid, {"type": "log", "message": f"Removed {removed} duplicates → {len(unique)} unique", "level": "info"})
            prospects = unique

            _publish_event(sid, {"type": "log", "message": "Running contact availability check..."})

            # ── Step 3: Verification ──
            _publish_event(sid, {"type": "stage", "stage": "verification", "label": "Location Verification & Qualification"})
            from app.agents.lead_verification import LeadVerificationAgent
            verification = LeadVerificationAgent()
            prospects = verification.verify_batch(prospects)
            _publish_event(sid, {"type": "log", "message": f"Verified {len(prospects)} leads after contact + location checks", "level": "success"})

            if not prospects:
                _publish_event(sid, {"type": "log", "message": "No prospects passed verification. Campaign ending.", "level": "warn"})
                _publish_event(sid, {"type": "done", "status": "completed", "summary": {"discovered": len(unique), "qualified": 0, "final_leads": 0, "emails_sent": 0, "whatsapp_sent": 0}})
                return

            # ── Step 4: Business Research ──
            _publish_event(sid, {"type": "stage", "stage": "research", "label": "Business Research & Analysis"})
            from app.agents.business_research import BusinessResearchAgent
            research = BusinessResearchAgent()
            for i, p in enumerate(prospects):
                try:
                    _publish_event(sid, {"type": "log", "message": f"Researching: {p.business_name[:50]}..."})
                    research.research(p)
                except Exception as e:
                    _publish_event(sid, {"type": "log", "message": f"Research skipped for {p.business_name[:40]}: {str(e)[:60]}", "level": "warn"})

            # ── Step 5: Problem Analysis ──
            from app.agents.problem_analysis import ProblemAnalysisAgent
            problem_agent = ProblemAnalysisAgent()
            for p in prospects:
                try:
                    problem_agent.analyze(p, category)
                except Exception as e:
                    pass  # silent

            # ── Step 6: Solution Matching ──
            from app.agents.solution_matching import SolutionMatchingAgent
            matching = SolutionMatchingAgent()
            for p in prospects:
                try:
                    matching.match(p)
                except Exception:
                    pass

            # ── Step 7: Scoring ──
            _publish_event(sid, {"type": "stage", "stage": "scoring", "label": "Lead Scoring & Selection"})
            from app.agents.lead_scoring import LeadScoringAgent
            scoring = LeadScoringAgent(target_category=category, target_country=country, target_city=city)
            prospects = scoring.score_batch(prospects)
            qualified = [p for p in prospects if p.is_qualified]
            _publish_event(sid, {"type": "log", "message": f"Scored {len(prospects)} prospects → {len(qualified)} qualified (threshold: {settings.campaign.lead_score_threshold})", "level": "success"})

            final_leads = scoring.select_top_leads(prospects, count)
            _publish_event(sid, {"type": "log", "message": f"Selected top {len(final_leads)} leads for outreach", "level": "info"})

            if not final_leads:
                _publish_event(sid, {"type": "log", "message": "No leads selected. Campaign ending.", "level": "warn"})
                _publish_event(sid, {"type": "done", "status": "completed", "summary": {"discovered": len(unique), "qualified": len(qualified), "final_leads": 0, "emails_sent": 0, "whatsapp_sent": 0}})
                return

            # ── Step 8: Save & Outreach ──
            _publish_event(sid, {"type": "stage", "stage": "saving", "label": "Saving to Database & Outreach"})
            from app.agents.personalization import PersonalizationAgent
            personalizer = PersonalizationAgent()
            from app.agents.outreach import OutreachAgent
            outreach_agent = OutreachAgent()
            from app.database import CampaignRepository, FollowUpRepository, LeadRepository
            lead_repo = LeadRepository()
            followup_repo = FollowUpRepository()

            emails_sent = 0
            whatsapp_sent = 0
            failed = 0

            for i, p in enumerate(final_leads):
                _publish_event(sid, {"type": "log", "message": f"[{i+1}/{len(final_leads)}] {p.business_name[:50]} (score: {p.lead_score})"})

                # Save to DB
                lead_data = {
                    "business_name": p.business_name,
                    "business_category": p.business_category or category,
                    "country": p.country or country,
                    "city": p.city or city,
                    "address": p.address,
                    "phone": p.phone,
                    "email": p.email,
                    "website": p.website,
                    "google_maps_url": p.google_maps_url,
                    "source": p.source,
                    "source_url": p.source_url,
                    "posted_date": p.posted_date,
                    "business_research": p.business_research,
                    "potential_problem": p.potential_problem,
                    "recommended_service": p.recommended_service,
                    "recommended_ai_solution": p.recommended_ai_solution,
                    "lead_score": p.lead_score,
                    "is_qualified": p.is_qualified,
                    "dedup_website": p.website.lower().strip() if p.website else "",
                    "dedup_email": p.email.lower().strip() if p.email else "",
                    "dedup_phone": p.phone.strip() if p.phone else "",
                    "dedup_maps_url": p.google_maps_url.strip() if p.google_maps_url else "",
                }
                db_lead = lead_repo.save_lead(lead_data)
                followup_repo.create_state(db_lead.id)

                # Generate message
                message = personalizer.generate_message(p)

                # Send outreach
                result = outreach_agent.send_initial(p, message, db_lead.id)
                if result["success"]:
                    if result["channel"] == "email":
                        emails_sent += 1
                        _publish_event(sid, {"type": "log", "message": f"  \u2709 Email sent to {p.email}", "level": "success"})
                    elif result["channel"] == "whatsapp":
                        whatsapp_sent += 1
                        _publish_event(sid, {"type": "log", "message": f"  \U0001f4f1 WhatsApp sent to {p.phone}", "level": "success"})
                    lead_repo.update_lead(db_lead.id, {"is_outreach_lead": True, "notes": message})
                else:
                    failed += 1
                    _publish_event(sid, {"type": "log", "message": f"  \u2716 Send failed: {result.get('status', 'unknown')}", "level": "error"})
                    lead_repo.update_lead(db_lead.id, {"is_outreach_lead": True, "notes": f"Not sent: {result.get('status', 'unknown')}"})

            # ── Follow-ups ──
            from app.agents.follow_up import FollowUpAgent
            followup_agent = FollowUpAgent()
            fu_results = followup_agent.process_all_followups()

            _publish_event(sid, {
                "type": "done",
                "status": "completed",
                "summary": {
                    "discovered": len(unique),
                    "qualified": len(qualified),
                    "final_leads": len(final_leads),
                    "emails_sent": emails_sent,
                    "whatsapp_sent": whatsapp_sent,
                },
            })

        except Exception as e:
            logger.error(f"Campaign failed: {e}", exc_info=True)
            _publish_event(sid, {"type": "error", "message": f"Campaign failed: {str(e)[:200]}"})
            _publish_event(sid, {"type": "done", "status": "failed", "summary": {"discovered": 0, "qualified": 0, "final_leads": 0, "emails_sent": 0, "whatsapp_sent": 0}})
        finally:
            # Remove the temporary SSE log handler
            if _sse_handler_added:
                _log_mod.getLogger().removeHandler(_sse_handler)
            _set_campaign_active(sid, False)

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    return jsonify({"session_id": sid, "status": "started"})


@app.route("/campaign/stream")
def campaign_stream():
    """SSE endpoint that streams campaign events for a given session."""
    sid = request.args.get("sid", "")
    if not sid or sid not in _event_queues:
        return "Invalid session", 400

    def generate():
        q = _event_queues.get(sid)
        if not q:
            return

        # Keep alive heartbeat every 15s
        last_heartbeat = time.time()

        while True:
            try:
                evt = q.get(timeout=15)
                yield f"data: {json.dumps(evt)}\n\n"

                if evt.get("type") == "done":
                    # Send one final keepalive then stop
                    time.sleep(1)
                    _cleanup_session(sid)
                    break

                last_heartbeat = time.time()

            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f": heartbeat\n\n"
                if time.time() - last_heartbeat > 120:
                    _cleanup_session(sid)
                    break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/campaign/run")
def run_campaign():
    """Run a campaign synchronously (legacy)."""
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


# ── Follow-up Routes ───────────────────────────────────────────────────────

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


# ── Config Route ───────────────────────────────────────────────────────────

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


# ── Interactive Review & Selective Dispatch ────────────────────────────────

@app.route("/review")
def review_page():
    """Interactive lead review page with checkboxes for selective dispatch."""
    init_db()
    lead_repo = LeadRepository()
    all_leads = lead_repo.get_all_qualified()

    # Show leads that haven't been emailed yet in THIS session (no 'Email sent' in notes)
    pending = [
        l for l in all_leads
        if not (l.notes and "Email sent" in str(l.notes))
    ]

    # Check historical outreach (past campaigns)
    already_contacted_count = 0
    for lead in pending:
        lead._already_contacted = lead_repo.was_previously_contacted(
            email=lead.email or "",
            website=lead.website or "",
        )
        if lead._already_contacted:
            already_contacted_count += 1

    # Group by category for display
    categories = {}
    for lead in pending:
        cat = lead.business_category or "Uncategorized"
        categories.setdefault(cat, []).append(lead)

    # Pre-generate email previews for leads with email
    from app.agents.personalization import PersonalizationAgent
    from app.sources.base import RawProspect
    personalizer = PersonalizationAgent()
    email_previews = {}  # lead_id -> {subject, body_preview}
    for lead in pending:
        if lead.email and lead.email not in ("N/A", ""):
            try:
                prospect = RawProspect(
                    business_name=lead.business_name or '',
                    business_category=lead.business_category or '',
                    country=lead.country or '',
                    city=lead.city or '',
                    email=lead.email,
                    website=lead.website or '',
                    business_research=lead.business_research or '',
                    potential_problem=lead.potential_problem or '',
                    recommended_service=lead.recommended_service or '',
                    recommended_ai_solution=lead.recommended_ai_solution or '',
                    source=lead.source or '',
                    metadata={'lead_id': lead.id},
                )
                msg = personalizer.generate_message(prospect)
                if isinstance(msg, dict):
                    email_previews[lead.id] = {
                        'subject': msg.get('subject', f"Quick question regarding {lead.business_name}'s client bookings"),
                        'body': msg.get('body', ''),
                    }
                else:
                    email_previews[lead.id] = {
                        'subject': f"Quick question regarding {lead.business_name}'s client bookings",
                        'body': str(msg),
                    }
            except Exception:
                email_previews[lead.id] = {
                    'subject': f"Quick question regarding {lead.business_name}'s client bookings",
                    'body': '(Message generation failed — template fallback would be used)',
                }

    lead_cards = ""
    for cat, cat_leads in sorted(categories.items()):
        lead_cards += f'<h3 class="category-header">{cat} ({len(cat_leads)})</h3>'
        for lead in cat_leads:
            was_contacted = getattr(lead, '_already_contacted', False)
            status_class = "status-sent" if lead.is_outreach_lead else ("status-pending" if lead.is_qualified else "status-draft")
            status_text = "Outreach" if lead.is_outreach_lead else ("Qualified" if lead.is_qualified else "New")
            has_email = bool(lead.email and lead.email not in ("N/A", ""))
            has_phone = bool(lead.phone and lead.phone not in ("N/A", ""))

            email_color = '#27ae60' if has_email else '#e74c3c'
            phone_color = '#27ae60' if has_phone else '#e74c3c'

            # Grayed-out styling for previously contacted leads
            card_opacity = '0.55' if was_contacted else '1'
            card_bg = '#f0f0f0' if was_contacted else 'white'
            card_border = '1px solid #ddd' if not was_contacted else '1px solid #ccc'
            checked_attr = '' if was_contacted else ('checked' if has_email else '')
            disabled_attr = 'disabled' if was_contacted else ''
            name_color = '#999' if was_contacted else '#1a1a2e'

            # Badge for already-contacted
            contact_badge = ''
            if was_contacted:
                contact_badge = '<span class="status-badge status-sent" style="margin-left:8px;font-size:11px;">Email was Sent</span>'

            # Email preview for right column
            preview = email_previews.get(lead.id, {})
            preview_subject = preview.get('subject', '(No email configured)')
            preview_body = preview.get('body', '(No email configured)')
            # Truncate body for display but keep readable
            preview_body_short = preview_body[:600] + ('...' if len(preview_body) > 600 else '')
            # Escape HTML for safe rendering
            import html as _html
            preview_body_escaped = _html.escape(preview_body_short)
            preview_subject_escaped = _html.escape(preview_subject)

            # Format body with line breaks for display
            preview_body_formatted = preview_body_escaped.replace('\n', '<br>')

            lead_cards += f"""
<div class="review-card" style="opacity:{card_opacity};background:{card_bg};border:{card_border};">
    <!-- LEFT: Lead Information + Checkbox -->
    <div class="review-col review-col-left">
        <div class="review-checkbox-row">
            <input type="checkbox" name="lead_ids" value="{lead.id}" class="lead-cb"
                   {checked_attr} {disabled_attr} style="width:18px;height:18px;cursor:{'not-allowed' if was_contacted else 'pointer'};">
            <span class="review-id">#{lead.id}</span>
        </div>
        <h4 class="review-biz-name" style="color:{name_color};">{lead.business_name} {contact_badge}</h4>
        <div class="review-meta">
            <span class="review-badge">{lead.business_category or 'N/A'}</span>
            <span class="review-score">Score: {lead.lead_score}</span>
        </div>
        <div class="review-detail"><strong>City:</strong> {lead.city or 'N/A'}, {lead.country or ''}</div>
        <div class="review-detail"><strong>Phone:</strong> <span style="color:{phone_color};">{lead.phone or 'N/A'}</span></div>
        <div class="review-detail"><strong>Email:</strong> <span style="color:{email_color};">{lead.email or 'N/A'}</span></div>
        <div class="review-detail"><strong>Website:</strong> {(lead.website or 'N/A')[:45]}</div>
        <div class="review-detail"><strong>Source:</strong> {lead.source or 'N/A'}</div>
        <div class="review-status"><span class="status-badge {status_class}">{status_text}</span></div>
    </div>

    <!-- MIDDLE: Problems & Analysis -->
    <div class="review-col review-col-mid">
        <div class="review-section-title">Problems &amp; Analysis</div>
        <div class="review-problem">
            <div class="review-problem-label">Identified Issues</div>
            <div class="review-problem-text">{(lead.potential_problem or 'N/A')[:200]}</div>
        </div>
        <div class="review-problem">
            <div class="review-problem-label">Recommended Service</div>
            <div class="review-problem-text" style="font-weight:600;color:#2c3e50;">{lead.recommended_service or 'N/A'}</div>
        </div>
        <div class="review-problem">
            <div class="review-problem-label">AI Solution</div>
            <div class="review-problem-text">{(lead.recommended_ai_solution or 'N/A')[:200]}</div>
        </div>
    </div>

    <!-- RIGHT: Email Preview -->
    <div class="review-col review-col-right">
        <div class="review-section-title">Outbound Email Preview</div>
        {'<div class="review-email-preview"><div class="review-email-subject"><strong>Subject:</strong> ' + preview_subject_escaped + '</div><div class="review-email-body">' + preview_body_formatted + '</div></div>' if has_email else '<div class="review-no-email">No email configured for this lead</div>'}
    </div>
</div>"""

    if not pending:
        lead_cards = "<p>No pending leads to review. Run a campaign first.</p>"

    content = f"""
<style>
    .review-header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:15px; }}
    .review-actions {{ display:flex; gap:10px; flex-wrap:wrap; }}
    .btn-send {{ background:#27ae60; color:white; padding:10px 24px; font-size:15px; font-weight:600; }}
    .btn-purge {{ background:#e74c3c; color:white; padding:10px 24px; font-size:15px; }}
    .btn-select-all {{ background:#3498db; color:white; padding:8px 16px; font-size:13px; }}
    .review-result {{ margin-top:20px; padding:15px; border-radius:8px; display:none; }}
    .review-result.ok {{ display:block; background:#d4edda; border:1px solid #c3e6cb; }}
    .review-result.err {{ display:block; background:#f8d7da; border:1px solid #f5c6cb; }}
    #reviewLog {{ font-family:monospace; font-size:13px; white-space:pre-wrap; max-height:300px; overflow-y:auto; padding:10px; background:#f8f9fa; border-radius:4px; margin-top:10px; }}

    /* Category headers */
    .category-header {{ margin:25px 0 12px; color:#2c3e50; font-size:16px; border-bottom:2px solid #3498db; padding-bottom:6px; }}

    /* 3-column lead card */
    .review-card {{
        display:grid;
        grid-template-columns:260px 1fr 1fr;
        gap:0;
        border-radius:10px;
        margin-bottom:12px;
        overflow:hidden;
        box-shadow:0 1px 4px rgba(0,0,0,0.08);
        transition:opacity 0.2s;
    }}
    .review-col {{ padding:16px 18px; }}
    .review-col-left {{
        border-right:1px solid #eee;
        display:flex;
        flex-direction:column;
        gap:6px;
    }}
    .review-col-mid {{
        border-right:1px solid #eee;
        display:flex;
        flex-direction:column;
        gap:8px;
    }}
    .review-col-right {{
        display:flex;
        flex-direction:column;
        gap:8px;
    }}

    /* Left column elements */
    .review-checkbox-row {{ display:flex; align-items:center; gap:10px; margin-bottom:4px; }}
    .review-id {{ font-size:12px; color:#888; font-weight:600; }}
    .review-biz-name {{ margin:0; font-size:14px; line-height:1.3; }}
    .review-meta {{ display:flex; gap:8px; align-items:center; margin:2px 0; }}
    .review-badge {{ background:#e8f4fd; color:#2980b9; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:600; }}
    .review-score {{ font-size:12px; color:#666; font-weight:600; }}
    .review-detail {{ font-size:12px; color:#444; line-height:1.5; }}
    .review-status {{ margin-top:4px; }}

    /* Middle column */
    .review-section-title {{ font-size:12px; font-weight:700; color:#2c3e50; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px; }}
    .review-problem {{ background:#f8f9fa; border-radius:6px; padding:8px 10px; }}
    .review-problem-label {{ font-size:10px; color:#888; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:2px; }}
    .review-problem-text {{ font-size:12px; color:#333; line-height:1.4; }}

    /* Right column - email preview */
    .review-email-preview {{ background:#fafbfc; border:1px solid #e8e8e8; border-radius:6px; padding:10px 12px; flex:1; overflow-y:auto; max-height:200px; }}
    .review-email-subject {{ font-size:12px; color:#2c3e50; margin-bottom:8px; padding-bottom:6px; border-bottom:1px solid #eee; }}
    .review-email-body {{ font-size:11px; color:#444; line-height:1.5; white-space:pre-wrap; word-break:break-word; }}
    .review-no-email {{ font-size:12px; color:#999; font-style:italic; padding:20px; text-align:center; }}

    /* Responsive */
    @media (max-width:1100px) {{
        .review-card {{ grid-template-columns:1fr; }}
        .review-col-left, .review-col-mid {{ border-right:none; border-bottom:1px solid #eee; }}
    }}
</style>

<div class="card">
    <div class="review-header">
        <h2>Lead Review &amp; Dispatch ({len(pending)} pending{', ' + str(already_contacted_count) + ' already contacted' if already_contacted_count else ''})</h2>
        <div class="review-actions">
            <button class="btn btn-select-all" onclick="toggleAll()">Select / Deselect All</button>
            <button class="btn btn-send" id="sendBtn" onclick="sendSelected()">\u2709 Send Selected Emails</button>
            <button class="btn btn-purge" onclick="purgeUnselected()">\U0001f5d1 Purge Unselected</button>
        </div>
    </div>
    <p style="color:#666;font-size:13px;">Leads with email are pre-checked. Uncheck leads you want to skip. Grayed-out leads were already contacted in past campaigns and cannot be re-selected.</p>
</div>

<div id="reviewResult" class="review-result"><pre id="reviewLog"></pre></div>

<form id="reviewForm">
{lead_cards}
</form>

<script>
function getSelectedIds() {{
    return Array.from(document.querySelectorAll('.lead-cb:checked')).map(cb => cb.value);
}}

function toggleAll() {{
    const cbs = document.querySelectorAll('.lead-cb');
    const allChecked = Array.from(cbs).every(cb => cb.checked);
    cbs.forEach(cb => cb.checked = !allChecked);
}}

function sendSelected() {{
    const ids = getSelectedIds();
    if (ids.length === 0) {{ alert('Select at least one lead.'); return; }}
    if (!confirm('Send emails to ' + ids.length + ' selected lead(s)?')) return;

    const btn = document.getElementById('sendBtn');
    btn.disabled = true; btn.innerHTML = '\u23f3 Sending...';

    fetch('/review/send', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{lead_ids: ids}})
    }})
    .then(r => r.json())
    .then(data => {{
        const el = document.getElementById('reviewResult');
        el.className = 'review-result ok';
        document.getElementById('reviewLog').textContent = data.log || JSON.stringify(data, null, 2);
        btn.innerHTML = '\u2705 Done (' + (data.sent || 0) + ' sent)';
        // Remove sent leads from the page
        ids.forEach(id => {{
            const cb = document.querySelector('.lead-cb[value="' + id + '"]');
            if (cb) cb.closest('.card').remove();
        }});
    }})
    .catch(err => {{
        const el = document.getElementById('reviewResult');
        el.className = 'review-result err';
        document.getElementById('reviewLog').textContent = 'Error: ' + err.message;
        btn.disabled = false; btn.innerHTML = '\u2709 Send Selected Emails';
    }});
}}

function purgeUnselected() {{
    const allIds = Array.from(document.querySelectorAll('.lead-cb')).map(cb => cb.value);
    const selectedIds = getSelectedIds();
    const unselectedIds = allIds.filter(id => !selectedIds.includes(id));
    if (unselectedIds.length === 0) {{ alert('No unselected leads to purge.'); return; }}
    if (!confirm('Permanently delete ' + unselectedIds.length + ' unselected lead(s) from the database?')) return;

    fetch('/review/cleanup', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{purge_ids: unselectedIds}})
    }})
    .then(r => r.json())
    .then(data => {{
        const el = document.getElementById('reviewResult');
        el.className = 'review-result ok';
        document.getElementById('reviewLog').textContent = data.log || JSON.stringify(data, null, 2);
        unselectedIds.forEach(id => {{
            const cb = document.querySelector('.lead-cb[value="' + id + '"]');
            if (cb) cb.closest('.card').remove();
        }});
    }})
    .catch(err => {{
        const el = document.getElementById('reviewResult');
        el.className = 'review-result err';
        document.getElementById('reviewLog').textContent = 'Error: ' + err.message;
    }});
}}
</script>
"""

    return _base(content, "Lead Review", "review")


@app.route("/review/send", methods=["POST"])
def review_send():
    """Send emails only to selected leads, archive to Google Sheets by category."""
    from datetime import datetime as _dt
    from app.integrations.email import email_client
    from app.agents.personalization import PersonalizationAgent
    from app.integrations.google_sheets import sheets_client

    data = request.get_json() or {}
    lead_ids = data.get("lead_ids", [])

    if not lead_ids:
        return jsonify({"success": False, "log": "No leads selected", "sent": 0})

    init_db()
    lead_repo = LeadRepository()
    personalizer = PersonalizationAgent()
    from app.sources.base import RawProspect

    log_lines = []
    sent_count = 0
    failed_count = 0
    archived_count = 0

    log_lines.append(f"\u2500" * 50)
    log_lines.append(f"Selective Dispatch: {len(lead_ids)} lead(s) selected")
    log_lines.append(f"\u2500" * 50)

    for lid in lead_ids:
        try:
            lid_int = int(lid)
        except (ValueError, TypeError):
            continue

        lead = lead_repo.get_lead(lid_int)
        if not lead:
            log_lines.append(f"[{lid}] Lead not found — skipped")
            continue

        if not lead.email or lead.email in ("N/A", ""):
            log_lines.append(f"[{lid}] {lead.business_name[:35]} — No email, skipped")
            failed_count += 1
            continue

        if lead.notes and "Email sent" in str(lead.notes):
            log_lines.append(f"[{lid}] {lead.business_name[:35]} — Already sent, skipped")
            continue

        # Build RawProspect for personalizer
        prospect = RawProspect(
            business_name=lead.business_name or '',
            business_category=lead.business_category or '',
            country=lead.country or '',
            city=lead.city or '',
            email=lead.email,
            website=lead.website or '',
            business_research=lead.business_research or '',
            potential_problem=lead.potential_problem or '',
            recommended_service=lead.recommended_service or '',
            recommended_ai_solution=lead.recommended_ai_solution or '',
            source=lead.source or '',
            metadata={{'lead_id': lid_int}},
        )

        try:
            msg = personalizer.generate_message(prospect)
            if isinstance(msg, dict):
                subject = msg.get('subject', f"Quick question regarding {lead.business_name}'s client bookings")
                body = msg.get('body', '')
            else:
                subject = f"Quick question regarding {lead.business_name}'s client bookings"
                body = str(msg)
        except Exception as e:
            log_lines.append(f"[{lid}] {lead.business_name[:35]} — Message gen failed: {str(e)[:50]}")
            failed_count += 1
            continue

        # Send email
        try:
            result = email_client.send(
                to_email=lead.email,
                subject=subject,
                body_text=body,
            )
            is_success = result.get('success', False)
            gmail_id = result.get('id', '')
        except Exception as e:
            is_success = False
            gmail_id = ''
            log_lines.append(f"[{lid}] {lead.business_name[:35]} — Send error: {str(e)[:50]}")

        ts = _dt.now().strftime('%Y-%m-%d %H:%M')

        if is_success:
            sent_count += 1
            # Update DB
            lead_repo.update_lead(lid_int, {
                'is_outreach_lead': True,
                'notes': f'Email sent {ts} | Gmail ID: {gmail_id}',
            })

            # Archive to Google Sheets by category
            if sheets_client.is_configured:
                try:
                    row_data = {
                        'Lead ID': str(lid_int),
                        'Date Found': ts,
                        'Business Name': lead.business_name or '',
                        'Business Category': lead.business_category or '',
                        'Country': lead.country or '',
                        'City': lead.city or '',
                        'Address': lead.address or '',
                        'Phone': lead.phone or '',
                        'Email': lead.email or '',
                        'Website': lead.website or '',
                        'Google Maps URL': lead.google_maps_url or '',
                        'Source': lead.source or '',
                        'Source URL': lead.source_url or '',
                        'Business Research': (lead.business_research or '')[:500],
                        'Potential Problem': lead.potential_problem or '',
                        'Recommended Service': lead.recommended_service or '',
                        'Recommended AI Solution': (lead.recommended_ai_solution or '')[:500],
                        'Lead Score': str(lead.lead_score or ''),
                        'Contact Channel': 'email',
                        'Initial Message': body[:500] if body else '',
                        'Initial Contact Date': ts,
                        'Initial Contact Status': 'Sent',
                        'Follow-up Status': 'Active',
                        'Do Not Contact': 'No',
                        'Human Required': 'No',
                    }
                    sheets_client.append_lead_to_category(
                        row_data,
                        category=lead.business_category or '',
                    )
                    archived_count += 1
                    log_lines.append(f"[{lid}] {lead.business_name[:35]} — \u2709 SENT + archived to '{lead.business_category or 'Leads'}' tab")
                except Exception as e:
                    log_lines.append(f"[{lid}] {lead.business_name[:35]} — \u2709 SENT but Sheets archive failed: {str(e)[:50]}")
            else:
                log_lines.append(f"[{lid}] {lead.business_name[:35]} — \u2709 SENT (Sheets not configured)")
        else:
            failed_count += 1
            lead_repo.update_lead(lid_int, {
                'notes': f'Failed: {result.get("message", "unknown")}',
            })
            log_lines.append(f"[{lid}] {lead.business_name[:35]} — \u2716 FAILED: {result.get('message', 'unknown')[:50]}")

    log_lines.append(f"\u2500" * 50)
    log_lines.append(f"Done: {sent_count} sent, {archived_count} archived, {failed_count} failed")
    log_lines.append(f"\u2500" * 50)

    return jsonify({
        'success': True,
        'sent': sent_count,
        'archived': archived_count,
        'failed': failed_count,
        'log': '\n'.join(log_lines),
    })


@app.route("/review/cleanup", methods=["POST"])
def review_cleanup():
    """Purge unselected leads from the local database."""
    data = request.get_json() or {}
    purge_ids = data.get("purge_ids", [])

    if not purge_ids:
        return jsonify({"success": False, "log": "No leads to purge", "purged": 0})

    init_db()
    lead_repo = LeadRepository()
    followup_repo = FollowUpRepository()
    purged = 0
    log_lines = []

    for lid in purge_ids:
        try:
            lid_int = int(lid)
        except (ValueError, TypeError):
            continue

        lead = lead_repo.get_lead(lid_int)
        if not lead:
            continue

        name = lead.business_name[:35]
        try:
            # Delete follow-up state first
            followup_repo.delete_by_lead_id(lid_int)
            # Delete the lead
            lead_repo.delete_lead(lid_int)
            purged += 1
            log_lines.append(f"\u2716 Deleted: #{lid_int} {name}")
        except Exception as e:
            log_lines.append(f"\u2716 Failed to delete #{lid_int} {name}: {str(e)[:50]}")

    log_lines.insert(0, f"Purged {purged} leads from database")

    return jsonify({
        'success': True,
        'purged': purged,
        'log': '\n'.join(log_lines),
    })


def run_web_dashboard(host: str = "0.0.0.0", port: int = 5000, debug: bool = False):
    """Run the web dashboard."""
    init_db()
    print(f"\nStarting web dashboard at http://{host}:{port}")
    print("Press Ctrl+C to stop\n")
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_web_dashboard(debug=True)
