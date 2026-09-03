"""
Personalization Agent.
Generates unique, business-specific outreach messages.
Every message is based on the specific business, its problems, and the recommended solution.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config.settings import settings
from app.integrations.llm import LLMClient, get_llm
from app.sources.base import RawProspect

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Outreach prompt — comprehensive system instructions for the LLM.
# This is the single source of truth for email generation style and rules.
# ---------------------------------------------------------------------------

_OUTREACH_SYSTEM_PROMPT = """\
You are the Outreach Email Generation Agent for an AI automation agency.

Your job is to generate short, personalized, professional cold emails for qualified business leads.

==================================================
EMAIL OBJECTIVE
==================================================

The email is NOT to aggressively sell. It is to:

1. Show that we understand the type of business.
2. Identify one or two realistic problems that the business MAY face.
3. Explain a practical AI/automation solution that could help.
4. Keep the explanation simple and non-technical.
5. Create curiosity.
6. Ask for a simple next step, usually a short demo.

The email should feel like it was written specifically for this business by a human.

Use this flow:
RESEARCH -> BUSINESS-SPECIFIC CONTEXT -> PLAUSIBLE PROBLEM -> RELEVANT SOLUTION -> SIMPLE BENEFIT -> DEMO/REPLY CTA -> SHORT PERSONAL INTRODUCTION

==================================================
PERSONALIZATION RULES
==================================================

Before writing the email, use the lead's available research:

- Business name, category, city, country
- Website, public information, services
- Booking/contact process if publicly visible
- Any public evidence of customer communication, repetitive enquiries, or booking opportunities

Never invent facts.

If a problem is not directly confirmed, describe it as a possibility:

GOOD:
"Businesses like yours often receive repeated questions..."
"Your team may be handling..."
"An AI assistant could help with..."
"Many customers prefer getting quick answers..."

BAD:
"I noticed that your staff spends hours answering calls."
"Your website does not have online booking."
"You are losing customers after hours."

Do not claim something unless research actually supports it.

==================================================
EMAIL STYLE
==================================================

Every email must be:

- Short (4-6 short paragraphs, under 150 words)
- Clear, Professional, Friendly, Human
- Specific to the business
- Low-pressure, Non-hyped

Avoid:
- Long paragraphs, Corporate language, Technical jargon
- Excessive AI terminology, Fake statistics, Guaranteed results
- "10x your business", "Revolutionary AI", "Game-changing solution"
- Aggressive sales language, Excessive emojis, Generic mass-email wording

The recipient should understand the email in approximately 20-30 seconds.

==================================================
SERVICES WE OFFER
==================================================

1. Website Development
2. Autonomous AI Agents (LLM-based, RAG, business process automation, decision-making workflows)
3. AI Chatbots
4. Customer support automation
5. Appointment/booking automation
6. WhatsApp and website AI assistants
7. Business workflow automation

Only mention services relevant to the lead. Do NOT dump the entire list.

==================================================
CATEGORY-SPECIFIC CONTEXT
==================================================

Use these patterns to understand how context changes per category.
These are STYLE EXAMPLES, not templates. Generate fresh wording each time.

DENTIST / DENTAL CLINIC:
- Patients ask about treatments, availability, appointments
- AI dental receptionist for website/WhatsApp
- Answer common patient questions, help with appointment requests
- Work outside normal hours

RESTAURANT:
- Customers ask about menus, hours, reservations
- AI assistant for website/WhatsApp
- Handle reservation enquiries, provide quick answers

BEAUTY PARLOUR / BEAUTY SALON:
- Regular questions about services, prices, availability, appointments
- AI assistant through WhatsApp or website
- Quick responses for customers, less routine messages for team

MAKEUP CENTER:
- Questions about packages, pricing, availability, appointments
- AI assistant for WhatsApp or website
- Guide potential customers toward the right service

CLINIC / MEDICAL CLINIC:
- Recurring questions about services, appointments, timings
- AI receptionist for website/WhatsApp
- Focus on administrative communication, FAQs, appointment requests
- Do NOT provide medical diagnosis, advice, or treatment recommendations

TRAVEL & TOURS:
- Questions about packages, destinations, prices, availability, booking details
- AI assistant through website/WhatsApp
- Help customers find information before speaking with team

DO NOT USE CATEGORY TEMPLATES BLINDLY.
For every lead:
1. Read the actual research.
2. Identify the category.
3. Find the strongest plausible automation opportunity.
4. Write a new email with the business name and city naturally.

If the research reveals a specific opportunity, prioritize that over generic language.

==================================================
SUBJECT LINE RULES
==================================================

Generate a short, relevant subject line.

Good:
- A simpler way to handle patient enquiries
- AI support for your dental practice
- Automating restaurant enquiries
- Helping customers book more easily
- AI assistant for travel enquiries

Avoid:
"URGENT", "IMPORTANT!!!", "Increase Revenue 500%", "Revolutionary AI Solution"

==================================================
CTA RULES
==================================================

Low-pressure CTAs only:

"Would you be interested in seeing a short demo?"
"Would you like to see how this could work for your business?"
"I'd be happy to show you a quick example."
"If this sounds useful, I can send you a short demo."

Do not pressure the recipient to buy.

==================================================
PERSONAL INTRODUCTION
==================================================

At the end of every email, include a short introduction with the configured business information.

Use these values exactly (omit any field that is empty):

Name: {MY_NAME}
Email: {MY_EMAIL}
WhatsApp: {MY_WHATSAPP_NUMBER}
Website: {MY_WEBSITE_URL}
Fiverr: {MY_FIVERR_URL}
LinkedIn: {MY_LINKEDIN_URL}

Preferred format:

Best regards,

{MY_NAME}
AI Agent Developer
Website: {MY_WEBSITE_URL}
Fiverr: {MY_FIVERR_URL}
LinkedIn: {MY_LINKEDIN_URL}
Email: {MY_EMAIL}
WhatsApp: {MY_WHATSAPP_NUMBER}

Do not invent or modify these links.

==================================================
FINAL EMAIL FORMAT
==================================================

Subject: [short subject]

Hi [Business Name] team,

[Personalized opening based on research.]

[Specific plausible business problem/opportunity.]

[Relevant AI/automation solution.]

[Simple benefit.]

[Low-pressure CTA.]

Best regards,

{MY_NAME}
AI Agent Developer
Website: {MY_WEBSITE_URL}
Fiverr: {MY_FIVERR_URL}
LinkedIn: {MY_LINKEDIN_URL}
Email: {MY_EMAIL}
WhatsApp: {MY_WHATSAPP_NUMBER}

==================================================
QUALITY CHECK (verify silently before returning)
==================================================

- Is this email personalized?
- Is the business category correctly understood?
- Is the problem realistic?
- Did I avoid inventing facts?
- Did I use "may/can/often" where appropriate?
- Is the proposed AI solution relevant?
- Is the email short?
- Does it sound human?
- Is the CTA simple?
- Did I avoid hype?
- Did I avoid unnecessary technical terminology?
- Did I include the configured contact information?
- Did I avoid fake URLs?
- Does it look like a one-to-one business email rather than mass spam?

If any answer is NO, improve the email before returning it.

==================================================
MOST IMPORTANT PRINCIPLE
==================================================

The email should NOT feel like: "Here is an AI product. Please buy it."
It should feel like: "I researched your type of business, understood a possible
communication/automation opportunity, and I have a practical solution that may
be useful. If you're interested, I can show you."

Write the message directly. No subject line inside the body text — only the full email with subject line at the top.
"""


class PersonalizationAgent:
    """Generates personalized outreach messages for each qualified lead."""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or get_llm()

    def generate_message(self, prospect: RawProspect) -> str:
        """
        Generate a personalized outreach message for this prospect.
        Uses LLM if available, falls back to template-based generation.

        The prospect metadata is updated with ``message_source`` to
        distinguish LLM-generated from template-fallback messages:
          - "llm"     — fully AI-generated personalized message
          - "template" — deterministic template fallback (LLM unavailable
                         or rate-limited)
        """
        if self.llm.is_configured:
            return self._generate_with_llm(prospect)
        else:
            prospect.metadata["message_source"] = "template"
            return self._generate_template(prospect)

    def _generate_with_llm(self, prospect: RawProspect) -> str:
        """Generate a message using LLM with the comprehensive outreach prompt."""
        my = settings.my_business

        # Build the system prompt with dynamic business info
        system_prompt = _OUTREACH_SYSTEM_PROMPT.format(
            MY_NAME=my.name or "",
            MY_EMAIL=my.email or "",
            MY_WHATSAPP_NUMBER=my.whatsapp_number or "",
            MY_WEBSITE_URL=my.website_url or "",
            MY_FIVERR_URL=my.fiverr_url or "",
            MY_LINKEDIN_URL=my.linkedin_url or "",
        )

        # Build location string with target city fallback
        display_city = prospect.city
        if not display_city and settings.campaign.target_city:
            display_city = settings.campaign.target_city

        # Collect research context
        problems = prospect.metadata.get("problems_list", [])
        problems_text = ""
        if problems:
            problems_text = "\n".join(f"  - {p}" for p in problems)

        demo_info = ""
        if prospect.metadata.get("demo_url"):
            demo_name = prospect.metadata.get("demo_name", "Demo")
            demo_info = f"Relevant demo: {demo_name} — {prospect.metadata['demo_url']}"
        else:
            demo_info = "No specific demo available for this business type."

        user_prompt = f"""Generate a personalized outreach email for this business:

Business: {prospect.business_name}
Category: {prospect.business_category}
Location: {display_city or 'their area'}, {prospect.country or ''}
Website: {prospect.website or 'No website'}
Potential problems:
{prospect.potential_problem or 'Not yet analyzed'}
{f'Problems identified: {problems_text}' if problems_text else ''}
Recommended service: {prospect.recommended_service or 'Not determined'}
Recommended AI solution: {prospect.recommended_ai_solution or 'Not determined'}
{demo_info}
Business research summary: {prospect.business_research[:500] if prospect.business_research else 'No research data available'}

Write the complete personalized outreach email (Subject + Body + Sign-off)."""

        try:
            message = self.llm.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.7,
                max_tokens=800,
            )
            # Enforce max length
            if len(message) > 2000:
                message = message[:2000]
            prospect.metadata["message_source"] = "llm"
            return message.strip()
        except Exception as e:
            logger.warning(
                f"LLM message generation failed ({type(e).__name__}), "
                f"using template fallback for {prospect.business_name}"
            )
            prospect.metadata["message_source"] = "template"
            return self._generate_template(prospect)

    def _generate_template(self, prospect: RawProspect) -> str:
        """Generate a template-based message when LLM is unavailable."""
        my = settings.my_business

        name = prospect.business_name
        # Use target city as fallback when prospect city is empty and location is verified
        city = prospect.city
        if not city:
            loc_verify = prospect.metadata.get("location_verification")
            if loc_verify and loc_verify.state in ("verified", "probably_verified"):
                city = settings.campaign.target_city or "your city"
            else:
                city = "your city"
        category = prospect.business_category or "business"
        solution = prospect.recommended_ai_solution or "an AI assistant"

        # Build category-specific opening
        category_openings = {
            "dentist": f"dental practices like yours often receive repeated questions about treatments, availability and appointments",
            "dental": f"dental practices like yours often receive repeated questions about treatments, availability and appointments",
            "restaurant": f"restaurants often receive repeated questions about menus, opening hours, reservations and availability",
            "beauty": f"beauty salons often receive regular questions about services, prices, availability and appointments",
            "salon": f"beauty salons often receive regular questions about services, prices, availability and appointments",
            "clinic": f"clinics often handle recurring questions about services, appointments, timings and general information",
            "medical": f"medical clinics often handle recurring questions about services, appointments, timings and general information",
            "travel": f"travel customers often ask similar questions about packages, destinations, prices, availability and booking details",
            "tour": f"travel customers often ask similar questions about packages, destinations, prices, availability and booking details",
            "cosmetic": f"customers looking for beauty and cosmetics services often have questions about products, services, availability and appointments",
            "makeup": f"customers looking for makeup services often have questions about packages, pricing, availability and appointments",
        }

        # Find best matching category
        opening = None
        cat_lower = category.lower()
        for key, text in category_openings.items():
            if key in cat_lower:
                opening = text
                break
        if not opening:
            opening = f"businesses like yours often receive repeated questions about services, availability and bookings"

        # Build sign-off
        links = []
        if my.name:
            links.append(my.name)
        if my.description:
            links.append(my.description)
        if my.email:
            links.append(f"Email: {my.email}")
        if my.whatsapp_number:
            links.append(f"WhatsApp: {my.whatsapp_number}")
        if my.website_url:
            links.append(f"Website: {my.website_url}")
        if my.fiverr_url:
            links.append(f"Fiverr: {my.fiverr_url}")
        if my.linkedin_url:
            links.append(f"LinkedIn: {my.linkedin_url}")
        links_text = "\n".join(links)

        # Include demo URL if available
        demo_text = ""
        if prospect.metadata.get("demo_url"):
            demo_text = f"\n\nYou can see a working example here: {prospect.metadata['demo_url']}"

        message = f"""Subject: A simpler way to handle {category.lower()} enquiries

Hi {name} team,

I came across your {category.lower()} in {city}. {opening.capitalize()}.

An AI assistant could handle many of these conversations automatically through your website or WhatsApp, giving potential customers a quick response while reducing routine messages for your team.

We build {solution} that can work as an additional customer-service layer alongside your existing team, including outside normal business hours.{demo_text}

Would you be interested in seeing a short demo?

Best regards,

{links_text}"""

        return message.strip()

    def generate_followup_message(
        self,
        prospect: RawProspect,
        followup_type: str = "3day",
    ) -> str:
        """Generate a follow-up message (3-day or 7-day)."""
        my = settings.my_business
        name = prospect.business_name
        category = prospect.business_category or "business"

        # Build sign-off
        sign_off_parts = []
        if my.name:
            sign_off_parts.append(my.name)
        if my.email:
            sign_off_parts.append(f"Email: {my.email}")
        sign_off = "\n".join(sign_off_parts) if sign_off_parts else "Best regards"

        if followup_type == "3day":
            message = f"""Hi {name} team,

Wanted to circle back on the automation idea I mentioned — if handling routine customer enquiries about {category.lower()} services is something your team deals with regularly, an AI assistant could help reduce that workload.

I'd be happy to show you a quick demo whenever it's convenient.

{sign_off}"""
        else:  # 7day
            message = f"""Hi {name} team,

Last note from me — if automating customer conversations around {category.lower()} services is on your radar, I'm happy to show you how it works for a business like yours.

Either way, wishing you a strong week ahead.

{sign_off}"""

        return message.strip()
