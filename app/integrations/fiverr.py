"""
Fiverr Outreach Integration.
Provides capabilities for sending buyer requests and managing Fiverr outreach.
Since Fiverr doesn't have a public API for messaging, this module provides:
1. Message generation optimized for Fiverr buyer requests
2. Template management for Fiverr proposals
3. Tracking of Fiverr outreach campaigns

Note: Fiverr buyer requests are submitted through the Fiverr website.
This module generates and formats messages for manual submission.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class FiverrClient:
    """Manages Fiverr outreach and message generation."""

    def __init__(self):
        self.fiverr_url = settings.my_business.fiverr_url

    @property
    def is_configured(self) -> bool:
        return bool(self.fiverr_url)

    def generate_buyer_request(
        self,
        business_name: str,
        business_category: str,
        city: str,
        country: str,
        requirement: str,
        demo_url: str = "",
        solution: str = "AI Agent",
    ) -> str:
        """
        Generate a Fiverr buyer request message.
        This is a formatted message for submitting as a Fiverr buyer request.
        """
        message = f"""Hi there,

I saw your request for {requirement} and I'd love to help.

I specialize in building custom AI agents and chatbots for businesses like {business_name}. My solutions include:

- AI-powered customer support and FAQ automation
- Appointment booking and scheduling systems
- Lead generation and qualification workflows
- WhatsApp and website chatbot integration

{f"I've built a working demo you can see here: {demo_url}" if demo_url else ""}

I have experience working with {business_category} businesses in {city}, {country}, and I understand the unique challenges you face.

I'd be happy to discuss your specific needs and provide a free consultation.

Best regards,
{settings.my_business.name}
{settings.my_business.description}
{self.fiverr_url}"""

        return message.strip()

    def generate_proposal(
        self,
        business_name: str,
        business_category: str,
        problem: str,
        solution: str,
        demo_url: str = "",
    ) -> str:
        """
        Generate a Fiverr proposal for a specific business problem.
        This is formatted for Fiverr's proposal system.
        """
        proposal = f"""Project Proposal for {business_name}

Understanding Your Needs:
I understand you're looking for {solution} to help with {problem} in your {business_category} business.

My Approach:
1. Discovery Phase: Understand your specific workflows and pain points
2. Design Phase: Create a custom AI solution tailored to your business
3. Development Phase: Build and test the solution with your team
4. Deployment: Launch and provide ongoing support

What I Deliver:
- Custom AI agent/chatbot configured for your business
- Integration with your existing tools and systems
- Training and documentation for your team
- 30 days of post-launch support

{f"See a working demo of similar work: {demo_url}" if demo_url else "I can show you a live demo of similar work upon request."}

Timeline: 2-3 weeks depending on complexity
Investment: Custom quote based on your specific requirements

I'd be happy to schedule a free consultation to discuss your project in detail.

Best regards,
{settings.my_business.name}
{self.fiverr_url}"""

        return proposal.strip()

    def format_for_fiverr(self, message: str) -> str:
        """Format a message for Fiverr's text input (character limits, etc.)."""
        # Fiverr buyer requests have a 2500 character limit
        if len(message) > 2500:
            message = message[:2497] + "..."
        return message

    def get_fiverr_profile_url(self) -> str:
        """Get the Fiverr profile URL."""
        return self.fiverr_url

    def track_outreach(
        self,
        business_name: str,
        message_type: str,
        message: str,
    ) -> Dict:
        """
        Track Fiverr outreach for reporting.
        Returns a dict with tracking information.
        """
        from datetime import datetime

        return {
            "business_name": business_name,
            "message_type": message_type,
            "message_preview": message[:100] + "..." if len(message) > 100 else message,
            "timestamp": datetime.now().isoformat(),
            "channel": "fiverr",
            "status": "prepared",
        }


# Module-level singleton
fiverr_client = FiverrClient()
