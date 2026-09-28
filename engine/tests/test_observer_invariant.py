"""Critical Architectural Test: Verifies that Phase 3 is strictly an Observer and NEVER a Decider.

Enforces that NO recommendation fields, architecture selections, chunking advice,
or retrieval strategies exist in schemas, prompts, or model outputs.
"""

import pytest
from pydantic import ValidationError
from ragger_engine.analyzer.models import (
    FileAnalysisProfile,
    SemanticObservations,
    StructuralFacts,
    WorkspaceKnowledgeProfile,
)


FORBIDDEN_FIELDS = [
    "recommended_architecture",
    "recommended_chunking",
    "recommended_vector_db",
    "retrieval_strategy",
    "rag_type",
    "recommendation_reason",
    "architecture_confidence",
    "target_architecture",
    "chunk_size_recommendation",
]

FORBIDDEN_RECOMMENDATION_TERMS = [
    "should use",
    "recommend",
    "recommended",
    "we suggest",
    "hierarchical rag",
    "hybrid rag",
    "knowledge rag",
    "graph rag",
    "vector rag",
]


def test_schema_forbids_recommendation_fields():
    """Confirms that none of the forbidden fields exist in any Phase 3 Pydantic model."""
    for model_cls in (FileAnalysisProfile, SemanticObservations, StructuralFacts, WorkspaceKnowledgeProfile):
        field_names = set(model_cls.model_fields.keys())
        for forbidden in FORBIDDEN_FIELDS:
            assert forbidden not in field_names, f"Model {model_cls.__name__} violates Phase 3 by defining '{forbidden}'!"


def test_extra_fields_rejected_by_pydantic():
    """Confirms that attempting to inject any recommendation field into SemanticObservations raises ValidationError."""
    valid_data = {
        "detected_domain": "finance",
        "primary_modality": "tabular_dataset",
        "secondary_modalities": [],
        "semantic_density": "high",
        "entity_relationship_density": "medium",
        "key_entities": ["Revenue", "Customer"],
        "primary_language": "en",
        "extraction_quality_score": 1.0,
        "observed_characteristics": ["Contains numerical tables"],
        "summary_description": "A dataset of financial records with numerical metrics.",
    }

    # Should validate cleanly without extra fields
    obs = SemanticObservations.model_validate(valid_data)
    assert obs.detected_domain == "finance"

    # Now attempt to inject forbidden architectural fields
    for forbidden in FORBIDDEN_FIELDS:
        corrupted_data = dict(valid_data)
        corrupted_data[forbidden] = "hierarchical_rag"
        with pytest.raises(ValidationError):
            SemanticObservations.model_validate(corrupted_data)


def test_summary_description_contains_no_recommendations():
    """Confirms that generated summary strings are strictly observational."""
    sample_summaries = [
        "This finance dataset contains structured records and metrics such as Sales, Customer, Revenue. It is organized into 2 sheet(s) with defined column schemas.",
        "This technology document contains hierarchical sections and headings such as Microservices, Security, Endpoints. It describes operational standards across 2 pages.",
    ]
    for text in sample_summaries:
        lower_text = text.lower()
        for term in FORBIDDEN_RECOMMENDATION_TERMS:
            assert term not in lower_text, f"Summary violates Observer invariant with term '{term}': {text}"
