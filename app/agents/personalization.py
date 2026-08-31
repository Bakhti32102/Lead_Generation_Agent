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

        system_prompt = f"""You are a professional outreach specialist for an AI development business.
Write a short, personalized outreach message to a business owner.

Rules:
- Keep it under 200 words
- Simple professional English
- Mention the business by name
- Mention a specific automation opportunity (NOT as a proven fact, but as a potential)
- Mention the recommended solution briefly
- Include a relevant demo link if available
- Keep a natural, non-pushy tone
- End with a soft call to action
- Include these links at the end (only include available ones):
  Website: {my.website_url}
  Fiverr: {my.fiverr_url}
  LinkedIn: {my.linkedin_url}

Do NOT use:
- Excessive AI jargon
- Long paragraphs
- Fake urgency or scarcity
- Guaranteed results claims
- "Revolutionary" or "10x" language
- Pressure tactics

The message should communicate: "You know your business best. There may be repetitive work that an AI agent can automate. I've built working systems and can customize one for your business."

Structure:
1. Personal greeting mentioning the business name
2. Brief observation about a potential automation opportunity
3. How the recommended solution could help
4. Link to a relevant working demo
5. Soft invitation to discuss
6. Your links (website, fiverr, linkedin)

Write the message directly. No subject line. No quotes around the message."""

        demo_info = ""
        if prospect.metadata.get("demo_url"):
            demo_info = f"Relevant demo: {prospect.metadata['demo_name']} — {prospect.metadata['demo_url']}"
        else:
            demo_info = "No specific demo available for this business type."

        user_prompt = f"""Business: {prospect.business_name}
Category: {prospect.business_category}
Location: {prospect.city}, {prospect.country}
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
        city = prospect.city or "your city"
        service = prospect.recommended_service or "AI automation"
        solution = prospect.recommended_ai_solution or "AI agent"

        problems_text = ""
        problems = prospect.metadata.get("problems_list", [])
        if problems:
            problems_text = f"such as {' and '.join(problems[:2])}"

        demo_text = ""
        if prospect.metadata.get("demo_url"):
            demo_text = f"\n\nI've built a working demo you can check out: {prospect.metadata['demo_url']}"

        links = []
        if my.website_url:
            links.append(f"Website: {my.website_url}")
        if my.fiverr_url:
            links.append(f"Fiverr: {my.fiverr_url}")
        if my.linkedin_url:
            links.append(f"LinkedIn: {my.linkedin_url}")
        links_text = "\n\n".join(links)

        message = f"""Hi there,

I came across {name} in {city} and wanted to reach out.

If your team handles customer inquiries, appointment requests, or routine questions {problems_text}, this is a workflow that could potentially be automated.

I build {solution} systems using AI that can handle these tasks automatically — using your business information and connected tools to manage routine operations and escalate complex cases to your team.{demo_text}

I'd be happy to show you how it could work for {name} if you're interested. No pressure — just thought it might be worth exploring.

{my.name}
{my.description}

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
        solution = prospect.recommended_ai_solution or "AI automation"

        if followup_type == "3day":
            message = f"""Hi,

Just following up on my previous message about {solution} for {name}.

I thought this could be useful for your business, especially around your daily customer workflows. I'd be happy to show you a quick example if you're interested.

{my.name}"""
        else:  # 7day
            message = f"""Hi,

Just one last follow-up regarding the {solution} idea I shared for {name}.

If this is something you're considering, I'd be happy to show you how it could work for your business. If not, no problem at all.

Wishing you all the best!

{my.name}"""

        return message.strip()
