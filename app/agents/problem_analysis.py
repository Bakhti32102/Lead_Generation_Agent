"""
Problem Analysis Agent.
Identifies realistic potential problems for each business that our services could solve.
IMPORTANT: Never fabricates evidence. Distinguishes between verified facts and potential problems.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.integrations.llm import LLMClient, get_llm
from app.sources.base import RawProspect

logger = logging.getLogger(__name__)

# Category-specific problem templates (deterministic, no LLM needed)
CATEGORY_PROBLEMS = {
    "clinic": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Appointment inquiries may require manual phone handling",
            "Repeated FAQ questions from patients",
            "After-hours inquiries may go unanswered",
            "WhatsApp inquiries may need manual responses",
        ],
        "default_solution": "AI Clinic Receptionist / Appointment Agent",
    },
    "dental clinic": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Dental appointment requests require manual scheduling",
            "Service and pricing questions from potential patients",
            "WhatsApp inquiries for booking",
            "After-hours lead capture",
        ],
        "default_solution": "AI Dental Receptionist",
    },
    "dentist": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Appointment scheduling may require phone calls",
            "Patients may have repeated questions about services",
            "Online booking may be missing",
            "Customer support after hours",
        ],
        "default_solution": "AI Dental Receptionist",
    },
    "hospital": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "High volume of patient inquiries",
            "Department routing may be manual",
            "Appointment coordination may be complex",
        ],
        "default_solution": "AI Hospital Information & Routing Agent",
    },
    "restaurant": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Reservation inquiries may require phone handling",
            "Menu and pricing questions from customers",
            "Delivery and takeout inquiries",
            "Opening hours and location questions",
        ],
        "default_solution": "Restaurant AI Customer Support / Reservation Agent",
    },
    "cafe": {
        "service_match": ["website", "ai_chatbot"],
        "default_problems": [
            "Menu and pricing questions",
            "Opening hours inquiries",
            "Delivery or takeaway questions",
        ],
        "default_solution": "Cafe AI Customer Support Agent",
    },
    "beauty parlor": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Appointment booking may require phone calls",
            "Service and pricing information requests",
            "Makeup package questions",
            "Availability inquiries",
        ],
        "default_solution": "Beauty Business AI Booking & Customer Support Agent",
    },
    "beauty salon": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Appointment scheduling via phone may be time-consuming",
            "Customers may have service and pricing questions",
            "Product inquiries",
            "Follow-up with past customers",
        ],
        "default_solution": "Beauty Business AI Booking & Customer Support Agent",
    },
    "makeup studio": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Appointment booking for makeup sessions",
            "Package and pricing inquiries",
            "Availability questions",
            "Portfolio inquiries",
        ],
        "default_solution": "Beauty Business AI Booking & Customer Support Agent",
    },
    "makeup shop": {
        "service_match": ["website", "ai_chatbot"],
        "default_problems": [
            "Product availability questions",
            "Order inquiries",
            "Product recommendations",
            "FAQ handling",
        ],
        "default_solution": "AI Cosmetic Customer Support / Sales Agent",
    },
    "cosmetic business": {
        "service_match": ["website", "ai_chatbot", "ai_agent"],
        "default_problems": [
            "Product questions from customers",
            "Customer support inquiries",
            "Order status questions",
            "Product recommendation requests",
        ],
        "default_solution": "AI Cosmetic Customer Support / Sales Agent",
    },
    "spa": {
        "service_match": ["website", "ai_agent", "ai_chatbot"],
        "default_problems": [
            "Appointment booking for spa treatments",
            "Service and pricing inquiries",
            "Package questions",
            "Availability and scheduling",
        ],
        "default_solution": "Spa AI Booking & Customer Support Agent",
    },
    "gym": {
        "service_match": ["website", "ai_chatbot"],
        "default_problems": [
            "Membership inquiries",
            "Class schedule questions",
            "Personal training availability",
            "Facility tour booking",
        ],
        "default_solution": "Gym AI Customer Support Agent",
    },
}


class ProblemAnalysisAgent:
    """Identifies realistic potential problems for each business."""

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or get_llm()

    def analyze(self, prospect: RawProspect, category: str = "") -> RawProspect:
        """
        Analyze a prospect and identify potential problems.
        Uses deterministic rules first, then LLM for enhanced analysis.
        """
        cat = (category or prospect.business_category or "").lower().strip()

        # Step 1: Use deterministic category-based problems
        category_key = self._match_category(cat)
        if category_key:
            template = CATEGORY_PROBLEMS[category_key]
            problems = template["default_problems"]
            solution = template["default_solution"]
        else:
            problems = []
            solution = ""

        # Step 2: Enhance with website analysis if available
        website_analysis = prospect.metadata.get("website_analysis", {})
        if isinstance(website_analysis, dict):
            if not website_analysis.get("has_booking"):
                problems.append("Online booking may not be available")
            if not website_analysis.get("has_chatbot"):
                problems.append("No chatbot for customer inquiries")
            if not website_analysis.get("has_whatsapp"):
                problems.append("WhatsApp integration not visible on website")
            if website_analysis.get("website_quality") in ("poor", "outdated"):
                problems.append("Website may appear outdated or have quality issues")

        # Step 3: Use LLM for nuanced analysis if available
        if self.llm.is_configured and prospect.metadata.get("website_analysis"):
            llm_problems = self._llm_analyze(prospect, cat)
            if llm_problems:
                problems.extend(llm_problems.get("problems", []))
                if llm_problems.get("solution"):
                    solution = llm_problems["solution"]

        # Remove duplicates and limit
        seen = set()
        unique_problems = []
        for p in problems:
            normalized = p.lower().strip()
            if normalized not in seen:
                seen.add(normalized)
                unique_problems.append(p)
        unique_problems = unique_problems[:5]

        # If no problems found, add a generic one
        if not unique_problems:
            unique_problems = [
                "If the business handles customer inquiries manually, "
                "this could potentially be automated."
            ]

        prospect.potential_problem = "\n".join(f"- {p}" for p in unique_problems)
        if solution:
            prospect.recommended_ai_solution = solution
        prospect.metadata["problems_list"] = unique_problems

        return prospect

    def _match_category(self, category: str) -> str:
        """Match a category string to our known categories."""
        category_lower = category.lower()

        # Direct match
        if category_lower in CATEGORY_PROBLEMS:
            return category_lower

        # Partial match
        for key in CATEGORY_PROBLEMS:
            if key in category_lower or category_lower in key:
                return key

        # Keyword-based match
        keyword_map = {
            "clinic": ["clinic", "medical center", "health center", "polyclinic"],
            "dental clinic": ["dental", "dentist", "dental clinic", "teeth"],
            "dentist": ["dental", "dentist", "dental care"],
            "restaurant": ["restaurant", "dining", "food court"],
            "cafe": ["cafe", "coffee", "coffee shop"],
            "beauty parlor": ["beauty parlor", "beauty salon", "parlor", "salon"],
            "beauty salon": ["salon", "beauty salon", "hair salon"],
            "makeup studio": ["makeup", "makeup studio", "beauty studio"],
            "makeup shop": ["makeup shop", "cosmetic shop", "beauty shop"],
            "cosmetic business": ["cosmetic", "cosmetics", "skincare", "skin care"],
            "spa": ["spa", "wellness", "massage"],
            "gym": ["gym", "fitness", "fitness center"],
        }

        for key, keywords in keyword_map.items():
            for kw in keywords:
                if kw in category_lower:
                    return key

        return ""

    def _llm_analyze(self, prospect: RawProspect, category: str) -> dict:
        """Use LLM for enhanced problem analysis."""
        analysis = prospect.metadata.get("website_analysis", {})
        summary = analysis.get("summary", "Unknown business")
        repetitive = analysis.get("repetitive_questions", [])
        automation = analysis.get("automation_opportunities", [])

        system_prompt = """You are a business automation consultant. Given information about a business,
identify the top 3-5 most realistic potential problems that could be solved by AI automation or web development.
Return a JSON object:
{"problems": ["problem1", "problem2", ...], "solution": "recommended solution name"}

Rules:
- Problems must be realistic and common for this type of business
- Do NOT fabricate evidence. Frame problems as potential opportunities.
- Keep problem descriptions short (one sentence each)
- The solution should be one of: "AI Agent", "AI Chatbot", "Website", or a combination
- Return ONLY valid JSON"""

        user_prompt = f"""Business: {prospect.business_name}
Category: {category}
Location: {prospect.city}, {prospect.country}
Website summary: {summary[:500]}
Known repetitive questions: {repetitive}
Automation opportunities observed: {automation}"""

        try:
            return self.llm.generate_json(system_prompt, user_prompt)
        except Exception as e:
            logger.debug(f"LLM problem analysis failed: {e}")
            return {}
