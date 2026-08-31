# AI Lead Generation & Outreach Agent

An autonomous AI-powered lead generation system that finds, researches, scores, and contacts local businesses — then manages follow-ups automatically via Google Sheets CRM.

## How It Works

```
Target Input → Search → Verify → Research → Problem Analysis → Service Match
     → Score → Personalize → Review → Send → Google Sheets → Follow-up
```

You provide a daily target (Country + City + Category + Count). The agent discovers businesses, analyzes automation opportunities, matches your services, generates personalized outreach, and manages the 3-day and 7-day follow-up sequences.

---

## 1. Installation

```bash
# Clone or navigate to the project
cd E:\Lead_Generation_Agent

# Install dependencies
pip install -r requirements.txt
```

**Requirements:** Python 3.9+

---

## 2. Environment Setup

```bash
# Copy the template
cp .env.example .env

# Edit .env with your API keys and business info
# (Use any text editor)
```

The `.env.example` file has clear sections:
- **REQUIRED** — LLM and Search API (at least one of each)
- **OPTIONAL** — Google Maps, Google Sheets, Email, WhatsApp
- **YOUR BUSINESS** — Name, email, website, Fiverr, LinkedIn URLs

---

## 3. Google Maps Setup (Optional)

Google Maps/Places API discovers local businesses with phone, website, and address.

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a project (or select existing)
3. Enable **Places API**
4. Create an API key
5. Add to `.env`:
   ```
   GOOGLE_MAPS_API_KEY=your_key_here
   ```

---

## 4. Search API Setup (Required)

At least one search provider is needed. Options:

| Provider | Free Tier | Setup |
|----------|-----------|-------|
| **Tavily** | 1000 searches/month | [tavily.com](https://tavily.com) — sign up, get API key |
| **SerpAPI** | 100 searches/month | [serpapi.com](https://serpapi.com) — sign up, get API key |
| **Google CSE** | 100 searches/day | Enable Custom Search API + create search engine |
| **Bing** | 1000 searches/month | [Bing Search API](https://www.microsoft.com/en-us/bing/apis/bing-web-search-api) |

Set in `.env`:
```
SEARCH_PROVIDER=tavily
SEARCH_API_KEY=your_key_here
```

---

## 5. Google Sheets Setup (Optional)

Google Sheets acts as the human-readable CRM. All leads, outreach status, and follow-up history are saved here.

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Enable **Google Sheets API**
3. Create a **Service Account**
4. Download the JSON key file → place in `E:\Lead_Generation_Agent\service_account.json`
5. Create a Google Sheet (or use existing)
6. Share the sheet with the service account email (the one in the JSON file)
7. Set in `.env`:
   ```
   GOOGLE_SHEET_ID=your_sheet_id_from_url
   GOOGLE_WORKSHEET_NAME=Leads
   ```

**Sheet columns** (auto-created):
Lead ID, Date Found, Business Name, Business Category, Country, City, Address, Phone, Email, Website, Google Maps URL, Source, Source URL, Posted Date, Requirement, Business Research, Potential Problem, Recommended Service, Recommended AI Solution, Lead Score, Contact Channel, Initial Message, Initial Contact Date, Initial Contact Status, Follow-up 3 Day, Follow-up 7 Day, Response, Response Category, Follow-up Status, Do Not Contact, Human Required, Notes

---

## 6. Email Setup (Optional)

Choose one provider:

### Resend (Recommended)
```
EMAIL_PROVIDER=resend
EMAIL_API_KEY=re_your_key
EMAIL_FROM=you@yourdomain.com
```
Sign up at [resend.com](https://resend.com) — free tier: 100 emails/day.

### Gmail API
```
EMAIL_PROVIDER=gmail
EMAIL_FROM=you@gmail.com
```
Uses the same Google service account from Google Sheets setup.

### SendGrid
```
EMAIL_PROVIDER=sendgrid
EMAIL_API_KEY=SG.your_key
EMAIL_FROM=you@yourdomain.com
```

### SMTP
```
EMAIL_PROVIDER=smtp
EMAIL_API_KEY=your_smtp_password
EMAIL_FROM=you@gmail.com
```
Also set: `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`, `EMAIL_SMTP_USER`

---

## 7. WhatsApp Setup (Optional)

Uses the **official Meta Cloud API** — no session hijacking or unofficial methods.

1. Create a [Meta Business](https://business.facebook.com/) account
2. Set up WhatsApp Business API
3. Get access token and phone number ID
4. Set in `.env`:
   ```
   WHATSAPP_ACCESS_TOKEN=your_token
   WHATSAPP_PHONE_NUMBER_ID=your_phone_id
   WHATSAPP_BUSINESS_ACCOUNT_ID=your_account_id
   ```

---

## 8. LLM Setup (Required)

At least one LLM provider is needed for business research, problem analysis, and message personalization.

| Provider | Recommended Model | Free/Cheap |
|----------|------------------|------------|
| **OpenAI** | gpt-4o-mini | ~$0.15/1M tokens |
| **Anthropic** | claude-3-haiku | ~$0.25/1M tokens |
| **Google Gemini** | gemini-1.5-flash | Free tier available |
| **Groq** | llama3-70b-8192 | Free tier available |

Set in `.env`:
```
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-your_key_here
```

---

## 9. Adding AI Agent Demos

Edit `agents.json` in the project root to add your demo links:

```json
[
  {
    "name": "Restaurant AI Agent",
    "category": "restaurant",
    "description": "Handles restaurant customer inquiries, reservations, and menu questions automatically.",
    "demo_url": "https://your-demo-url.com/restaurant"
  },
  {
    "name": "Dental Receptionist AI",
    "category": "dental",
    "description": "AI receptionist that books dental appointments and answers patient questions 24/7.",
    "demo_url": "https://your-demo-url.com/dental"
  },
  {
    "name": "Beauty Salon Booking Agent",
    "category": "beauty",
    "description": "Handles beauty salon appointment booking, service questions, and pricing inquiries.",
    "demo_url": "https://your-demo-url.com/beauty"
  }
]
```

**Matching rules:** The system automatically selects the most relevant demo based on business category. If no relevant demo exists, no demo is shown (it does not invent one).

---

## 10. Setting Daily Targets

### Via `.env` (defaults)
```
TARGET_COUNTRY=Pakistan
TARGET_CITY=Lahore
TARGET_BUSINESS_CATEGORY=Dental Clinics
DAILY_LEAD_TARGET=15
```

### Via CLI (override)
```bash
python -m app.main run --country UAE --city Dubai --category "Beauty Parlors" --count 10
```

The agent **only** searches the exact target you specify. It never expands to other cities or countries unless you explicitly allow it.

---

## 11. Running a Campaign

```bash
# Check configuration status
python -m app.main config

# Run a campaign (dry run by default)
python -m app.main run --country Pakistan --city Lahore --category "Dental Clinics" --count 10

# Run with specific flags
python -m app.main run --country UAE --city Dubai --category "Restaurants" --count 15
```

The pipeline:
1. **Search** — Google Maps, Google Search, LinkedIn, Public Jobs, SerpAPI
2. **Verify** — Business validity, contact info, freshness
3. **Research** — Website analysis via HTTP + LLM
4. **Problem Analysis** — Category-specific automation opportunities
5. **Service Match** — Website / AI Agent / AI Chatbot recommendation
6. **Score** — 100-point scoring system, threshold = 60
7. **Personalize** — LLM-generated outreach (or template fallback)
8. **Send** — Email / WhatsApp / Fiverr (respects dry run + review mode)
9. **Google Sheets** — All data saved to CRM
10. **Follow-up** — Automatic 3-day and 7-day sequences

---

## 12. Review Mode

Default: `REVIEW_MODE=true`

In review mode:
- All messages are generated and saved as **drafts**
- No messages are sent automatically
- You review, approve, or reject each lead
- Use the dashboard or CLI to approve

To send automatically:
```
REVIEW_MODE=false
```

---

## 13. Dry Run

Default: `DRY_RUN=true`

In dry run mode:
- Full search, research, scoring, and message generation runs
- **No emails, WhatsApp, or Fiverr messages are sent**
- All data is saved to the database
- Google Sheets receives draft entries (if configured)

To send real messages:
```
DRY_RUN=false
```

---

## 14. Follow-ups

The system manages a 3-step outreach sequence:

| Step | Timing | Action |
|------|--------|--------|
| **Initial** | Day 0 | First personalized message |
| **Follow-up 1** | Day 3 | Gentle reminder (if no reply) |
| **Follow-up 2** | Day 7 | Final follow-up |

**Stop conditions** (all automatic):
- Prospect replies → follow-ups stop
- Prospect says "not interested" → marked Do Not Contact
- Prospect opts out → marked Do Not Contact
- Final follow-up sent → sequence completed
- Max follow-ups reached → stopped

Process follow-ups:
```bash
python -m app.main followups
```

---

## 15. Dashboard

### Terminal Dashboard
```bash
python -m app.main menu
```
Interactive menu with:
- View today's campaign stats
- List qualified leads
- Approve/reject leads
- Process follow-ups
- View configuration

### Web Dashboard
```bash
python -m app.main web
```
Opens at `http://127.0.0.1:5000` with:
- **Dashboard** (`/`) — Stats, quick actions, recent leads
- **Leads** (`/leads`) — Full lead table with actions
- **Campaign** (`/campaign`) — Run new campaign
- **Follow-ups** (`/followups`) — Due follow-ups, process buttons
- **Config** (`/config`) — API status, settings

---

## 16. Scheduler

For automatic daily campaigns:

```bash
# Start the scheduler (runs in background)
python -m app.main schedule
```

Schedule behavior:
- **Daily at configured hour** — Runs full campaign
- **Every 6 hours** — Processes due follow-ups
- **Daily at 11:59 PM** — Generates daily report

Configure in `.env`:
```
SCHEDULER_ENABLED=true
SCHEDULER_CRON_HOUR=9
SCHEDULER_CRON_MINUTE=0
```

---

## 17. Troubleshooting

### "Search API not configured"
→ Set `SEARCH_API_KEY` in `.env`. Get a free key from [Tavily](https://tavily.com) or [SerpAPI](https://serpapi.com).

### "Google Sheets API is not configured"
→ Set `GOOGLE_SHEET_ID` and ensure `service_account.json` exists in the project root. Share your sheet with the service account email.

### "Email API not configured"
→ Set `EMAIL_PROVIDER` and `EMAIL_API_KEY`. For quick testing, use Resend (free tier).

### "WhatsApp API not configured"
→ Set `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`. Requires Meta Business account.

### "LLM client is not configured"
→ Set `LLM_API_KEY`. For cheap testing, use Groq (free tier) or Gemini.

### Tests fail
```bash
python -m pytest tests/ -v
```

### No qualified leads found
→ The threshold is 60/100. Lower it in `.env`:
```
LEAD_SCORE_THRESHOLD=40
```

---

## Architecture

```
app/
├── agents/           # Core pipeline agents
│   ├── lead_discovery.py      # Orchestrates all search sources
│   ├── lead_verification.py   # Validates businesses
│   ├── business_research.py   # Website analysis + LLM
│   ├── problem_analysis.py    # Category-specific problem templates
│   ├── solution_matching.py   # Service + demo selection
│   ├── lead_scoring.py        # 100-point scoring system
│   ├── personalization.py     # LLM message generation
│   ├── outreach.py            # Email/WhatsApp/Fiverr sending
│   ├── follow_up.py           # 3-day and 7-day sequences
│   ├── response_classifier.py # Categorize prospect replies
│   └── escalation.py          # Human escalation triggers
├── sources/          # Modular search providers
│   ├── base.py               # LeadSource interface + RawProspect
│   ├── google_maps.py        # Google Places API
│   ├── google_search.py      # Tavily/SerpAPI/Bing/Google CSE
│   ├── linkedin.py           # Indexed public LinkedIn search
│   ├── public_jobs.py        # Indeed, Upwork, Freelancer
│   └── serpapi.py            # SerpAPI multi-engine search
├── integrations/     # External service clients
│   ├── llm.py                # OpenAI/Anthropic/Gemini/Groq
│   ├── google_sheets.py      # Google Sheets CRM
│   ├── email.py              # Gmail/Resend/SendGrid/SMTP
│   ├── whatsapp.py           # Meta Cloud API
│   └── fiverr.py             # Fiverr buyer request generation
├── database/         # SQLite persistence
│   ├── models.py             # SQLAlchemy models
│   └── repository.py         # CRUD + dedup + counters
├── scheduler/        # Automation
│   ├── daily_campaign.py     # Full pipeline orchestration
│   ├── followups.py          # Scheduled follow-up processing
│   └── scheduler.py          # APScheduler integration
├── dashboard/        # UI
│   ├── terminal.py           # Interactive CLI menu
│   └── web.py                # Flask web dashboard
├── config/
│   └── settings.py           # Centralized configuration
└── main.py           # CLI entry point
```

---

## Production Status

| Component | Status | Notes |
|-----------|--------|-------|
| Core Pipeline | ✅ Working | Target → Search → Score → Send |
| Google Maps | ⚪ Not Configured | Requires `GOOGLE_MAPS_API_KEY` |
| Search (Tavily/SerpAPI) | ⚪ Not Configured | Requires `SEARCH_API_KEY` |
| LinkedIn Search | ✅ Architecture Ready | Uses indexed public search (not API) |
| Google Sheets CRM | ⚪ Not Configured | Requires service account + sheet ID |
| Email | ⚪ Not Configured | Requires `EMAIL_API_KEY` |
| WhatsApp | ⚪ Not Configured | Requires Meta Business credentials |
| LLM | ⚪ Not Configured | Requires `LLM_API_KEY` |
| Dashboard (Web) | ✅ Working | Flask at localhost:5000 |
| Dashboard (Terminal) | ✅ Working | Interactive CLI menu |
| Scheduler | ✅ Working | APScheduler integration |
| Follow-up Engine | ✅ Working | 3-day + 7-day with stop conditions |
| Tests | ✅ 347 passing | Production audit + unit + integration |

---

## License

Internal project. All rights reserved.
