"""
Canonical data models and contracts for Query Standardization Service.
"""

from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class StandardizedQuery(BaseModel):
    """Authoritative normalized query object emitted by QueryStandardizationService."""

    model_config = ConfigDict(extra="forbid")

    original_query: str = Field(..., description="The exact raw query supplied by the user")
    normalized_query: str = Field(..., description="Cleaned, typo-corrected, entity-preserved retrieval query")
    detected_intent: str = Field(default="fact_lookup", description="Detected query intent (e.g. summary, fact_lookup, entity_query)")
    changes_made: List[str] = Field(default_factory=list, description="List of corrections or normalization transforms applied")
    provider: str = Field(..., description="Provider executing normalization (e.g. ollama, test_deterministic, rule_fallback)")
    model: str = Field(..., description="Model name used for standardization")
    success: bool = Field(default=True, description="Whether query normalization succeeded")
