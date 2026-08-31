"""
Base class for all lead sources.
Every search provider (Google Maps, Google Search, LinkedIn, etc.)
implements this interface so the discovery agent can use them interchangeably.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RawProspect:
    """
    Normalized prospect data returned by any source.
    Fields may be partially filled — downstream agents enrich and verify.
    """

    business_name: str = ""
    business_category: str = ""
    country: str = ""
    city: str = ""
    address: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    google_maps_url: str = ""

    source: str = ""  # which source found this
    source_url: str = ""  # URL where this was found
    posted_date: str = ""  # raw date string if available
    requirement_text: str = ""  # for job/project sources

    # Enrichment fields (set by agents during pipeline)
    business_research: str = ""
    potential_problem: str = ""
    recommended_service: str = ""
    recommended_ai_solution: str = ""
    lead_score: int = 0
    is_qualified: bool = False

    # Freshness metadata
    freshness: str = "unknown"  # verified_recent / probably_recent / unknown
    hours_old: Optional[float] = None

    # Extra data specific to the source
    metadata: Dict[str, Any] = field(default_factory=dict)


class LeadSource(abc.ABC):
    """
    Abstract base for all search providers.

    Each implementation searches a specific platform and returns
    a list of RawProspect objects matching the target criteria.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable source name."""
        ...

    @property
    def is_configured(self) -> bool:
        """Whether this source has the necessary API keys/credentials."""
        return True

    @abc.abstractmethod
    def search(
        self,
        country: str,
        city: str,
        category: str,
        max_results: int = 20,
        **kwargs,
    ) -> List[RawProspect]:
        """
        Search for prospects matching the given target.

        Args:
            country: Target country (e.g., "Pakistan")
            city: Target city (e.g., "Lahore")
            category: Business category (e.g., "Dental Clinics")
            max_results: Maximum number of results to return

        Returns:
            List of RawProspect objects
        """
        ...
