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


class PersonalizationAgent:
    """Generates personalized outreach messages for each qualified lead."""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or get_llm()

    def generate_message(self, prospect: RawProspect) -> str:
        """
        Generate a personalized outreach message for this prospect.
        Uses LLM if available, falls back to template-based generation.
        """
        if self.llm.is_configured:
            return self._generate_with_llm(prospect)
        else:
            return self._generate_template(prospect)

    def _generate_with_llm(self, prospect: RawProspect) -> str:
        """Generate a message using LLM."""
        my = settings.my_business

        system_prompt = f"""You are a Senior B2B Conversion Copywriter for an AI automation agency.
Write a short, high-converting outreach email to a business owner.

TONE: Professional, consultative, peer-to-peer. Every sentence must earn its place.
No florid adjectives, no desperate sales fluff, no buzzwords.

STRUCTURE (follow this EXACTLY):
1. Opening line: Call out a specific, relatable operational bottleneck for their category
   (e.g. staff spending hours on repetitive booking calls, missing client queries after hours).
   Do NOT use generic openers like "I hope this email finds you well".
2. Brief bridge: One sentence connecting the bottleneck to the cost (lost revenue, wasted staff time).
3. Value prop (3 short lines, no bullets): Frame the solution as an automatic growth engine:
   - 24/7 instant WhatsApp responses
   - Zero missed client leads
   - Automated calendar scheduling
4. CTA: Low-friction and conversational.
   "Open to seeing a quick 2-minute custom demo built for {{business_name}} next week?"
5. Sign-off:
   Best regards,
   {my.name} ({my.description})
   - Email: {my.email}
   - WhatsApp: {my.whatsapp_number}
   - Website: {my.website_url}
   - Fiverr: {my.fiverr_url}
   - LinkedIn: {my.linkedin_url}

RULES:
- Under 150 words
- Simple professional English
- Mention the business by name at least once
- Never claim guaranteed results
- Never use urgency/scarcity tactics
- Write the message directly. No subject line. No quotes."""

        demo_info = ""
        if prospect.metadata.get("demo_url"):
            demo_info = f"Relevant demo: {prospect.metadata['demo_name']} — {prospect.metadata['demo_url']}"
        else:
            demo_info = "No specific demo available for this business type."

        # Build location string with target city fallback
        display_city = prospect.city
        if not display_city and settings.campaign.target_city:
            display_city = settings.campaign.target_city

        user_prompt = f"""Business: {prospect.business_name}
Category: {prospect.business_category}
Location: {display_city or 'their area'}, {prospect.country or ''}
Website: {prospect.website or 'No website'}
Potential problems:
{prospect.potential_problem}
Recommended service: {prospect.recommended_service}
Recommended AI solution: {prospect.recommended_ai_solution}
{demo_info}
Business research summary: {prospect.business_research[:300]}

Write the personalized outreach message:"""

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
            return message.strip()
        except Exception as e:
            logger.error(f"LLM message generation failed: {e}")
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
                # Location is verified but city field is empty - use target city
                city = settings.campaign.target_city or "your city"
            else:
                city = "your city"
        category = prospect.business_category or "business"
        service = prospect.recommended_service or "AI automation"
        solution = prospect.recommended_ai_solution or "AI agent"

        problems_text = ""
        problems = prospect.metadata.get("problems_list", [])
        if problems:
            problems_text = f"such as {' and '.join(problems[:2])}"

        demo_text = ""
        if prospect.metadata.get("demo_url"):
            demo_text = f"\n\nYou can see a working demo here: {prospect.metadata['demo_url']}"

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

        # Build automation-gaps context for the pitch
        gaps = prospect.metadata.get("automation_gaps", [])
        gap_text = ""
        if gaps:
            gap_text = "\n" + "\n".join(
                f"  - {g}" for g in gaps
            )

        message = f"""Hi {name},

I noticed your front desk in {city} is likely handling the same booking calls and client questions on repeat — that's hours of staff time that could go toward actual patient care.

We build AI assistants that sit on your WhatsApp and website, answering client queries instantly 24/7, filling your calendar automatically, and making sure no lead falls through the cracks after hours.

It's not a big tech overhaul — it's a focused automation layer that runs in the background while your team focuses on what they do best.{demo_text}

Open to seeing a quick 2-minute custom demo built for {name} next week?

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
        solution = prospect.recommended_ai_solution or "AI automation"

        if followup_type == "3day":
            message = f"""Hi {name},

Wanted to circle back on the WhatsApp automation idea I mentioned — it's a quick win that eliminates repetitive booking calls and keeps your inbox clear.

Happy to walk you through a 2-minute demo whenever it's convenient.

{my.name}"""
        else:  # 7day
            message = f"""Hi {name},

Last note from me — if automating client bookings and after-hours queries is on your radar, I'm happy to show you exactly how it works for a {category} business like yours.

Either way, wishing you a strong week ahead.

{my.name}"""

        return message.strip()
