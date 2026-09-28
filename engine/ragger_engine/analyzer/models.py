"""Strictly observational domain models for Phase 3 Analyzer Agent.

CRITICAL ARCHITECTURAL INVARIANT:
The Analyzer is an Observer, NEVER a Decider.
No fields related to RAG architectures, chunking strategies, vector databases,
or retrieval recommendations may exist in this schema.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class ContentModality(str, Enum):
    NARRATIVE_TEXT = "narrative_text"
    HIERARCHICAL_DOCUMENT = "hierarchical_document"
    TABULAR_DATASET = "tabular_dataset"
    SEMI_STRUCTURED_CODE = "semi_structured_code"
    SLIDE_PRESENTATION = "slide_presentation"
    SCIENTIFIC_RESEARCH = "scientific_research"


class SemanticDensity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EntityRelationshipDensity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class StructuralFacts(BaseModel):
    """Authoritative structural measurements derived strictly from Phase 2 models.
    
    The LLM is NOT permitted to measure or override these verified facts.
    """
    model_config = ConfigDict(extra="forbid")

    source_id: str
    detected_format: str
    file_size_bytes: int
    heading_depth: int = 0
    table_count: int = 0
    tabular_ratio: float = 0.0
    page_count: Optional[int] = None
    slide_count: Optional[int] = None
    total_words: int = 0
    total_rows: Optional[int] = None
    total_columns: Optional[int] = None
    has_numerical_columns: bool = False
    has_hierarchical_headings: bool = False
    extraction_warnings: List[str] = Field(default_factory=list)


class SemanticObservations(BaseModel):
    """Semantic and contextual observations made by the Analyzer (LLM or Heuristic).
    
    All fields are purely descriptive. Recommendations are strictly forbidden.
    """
    model_config = ConfigDict(extra="forbid")

    detected_domain: str
    primary_modality: ContentModality
    secondary_modalities: List[ContentModality] = Field(default_factory=list)
    semantic_density: SemanticDensity
    entity_relationship_density: EntityRelationshipDensity
    key_entities: List[str] = Field(default_factory=list)
    primary_language: str = "en"
    extraction_quality_score: float = Field(ge=0.0, le=1.0)
    observed_characteristics: List[str] = Field(default_factory=list)
    summary_description: str = Field(
        description="Exactly 1-2 objective, factual sentences describing content. No recommendations."
    )


class ProviderTelemetry(BaseModel):
    """Execution telemetry for provider selection and fallback auditability."""
    model_config = ConfigDict(extra="forbid")

    requested_provider: str
    actual_provider: str
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    model_name: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    duration_ms: float = 0.0


class FileAnalysisProfile(BaseModel):
    """Unified file profile joining Phase 2 structural facts with Phase 3 semantic observations."""
    model_config = ConfigDict(extra="forbid")

    source_id: str
    original_filename: str
    structural_facts: StructuralFacts
    semantic_observations: SemanticObservations
    telemetry: ProviderTelemetry
    analyzed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Convenience properties for Phase 4 Recommendation Engine consumption
    @property
    def primary_modality(self) -> ContentModality:
        return self.semantic_observations.primary_modality

    @property
    def detected_domain(self) -> str:
        return self.semantic_observations.detected_domain

    @property
    def semantic_density(self) -> SemanticDensity:
        return self.semantic_observations.semantic_density

    @property
    def tabular_ratio(self) -> float:
        return self.structural_facts.tabular_ratio

    @property
    def heading_depth(self) -> int:
        return self.structural_facts.heading_depth

    @property
    def summary_description(self) -> str:
        return self.semantic_observations.summary_description


class WorkspaceKnowledgeProfile(BaseModel):
    """Deterministic aggregation of all individual file profiles across a workspace."""
    model_config = ConfigDict(extra="forbid")

    workspace_id: str = "default"
    total_sources: int
    is_homogeneous: bool
    modality_distribution: Dict[str, float]
    dominant_modality: str
    cross_source_entity_overlap: List[str] = Field(default_factory=list)
    overall_domain: str
    file_profiles: Dict[str, FileAnalysisProfile]
    synthesized_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
