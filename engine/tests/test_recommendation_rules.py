"""
Unit tests for Phase 4 Deterministic Recommendation Rules.
Verifies exact boundary conditions, confidence constants, and factual signal extraction.
"""

import pytest
from datetime import datetime, timezone
from ragger_engine.analyzer.models import (
    ContentModality,
    EntityRelationshipDensity,
    FileAnalysisProfile,
    ProviderTelemetry,
    SemanticDensity,
    SemanticObservations,
    StructuralFacts,
    WorkspaceKnowledgeProfile,
)
from ragger_engine.recommendation.models import RagArchitectureId
from ragger_engine.recommendation.rules import (
    RuleDefaultDocument,
    RuleHierarchicalLongform,
    RuleMixedModality,
    RuleScientificResearch,
    RuleTabularDominant,
)
from ragger_engine.recommendation.service import RecommendationService


def create_file_profile(
    source_id: str,
    modality: str,
    heading_depth: int = 0,
    table_count: int = 0,
    has_numerical: bool = False,
    domain: str = "general",
) -> FileAnalysisProfile:
    return FileAnalysisProfile(
        source_id=source_id,
        original_filename=f"{source_id}.dat",
        structural_facts=StructuralFacts(
            source_id=source_id,
            detected_format="pdf" if "doc" in modality else "xlsx",
            file_size_bytes=2048,
            heading_depth=heading_depth,
            table_count=table_count,
            tabular_ratio=1.0 if "tabular" in modality else 0.0,
            page_count=5 if "doc" in modality else None,
            slide_count=None,
            total_words=500,
            total_rows=10 if "tabular" in modality else None,
            total_columns=4 if "tabular" in modality else None,
            has_numerical_columns=has_numerical,
            has_hierarchical_headings=heading_depth > 0,
            extraction_warnings=[],
        ),
        semantic_observations=SemanticObservations(
            detected_domain=domain,
            primary_modality=modality,
            semantic_density=SemanticDensity.MEDIUM,
            entity_relationship_density=EntityRelationshipDensity.LOW,
            key_entities=["EntityA", "EntityB"],
            extraction_quality_score=1.0,
            summary_description="A sample test document for evaluation.",
        ),
        telemetry=ProviderTelemetry(
            requested_provider="heuristic",
            actual_provider="heuristic",
        ),
    )


def test_rule_mixed_modality_strict_boundary():
    rule = RuleMixedModality()

    # Case 1: 3 documents, 2 tabular datasets -> 60% doc, 40% tabular -> STRICTLY > 20% on both sides
    files_match = [
        create_file_profile("s1", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=2),
        create_file_profile("s2", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=2),
        create_file_profile("s3", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=2),
        create_file_profile("s4", ContentModality.TABULAR_DATASET.value, has_numerical=True),
        create_file_profile("s5", ContentModality.TABULAR_DATASET.value, has_numerical=True),
    ]

    workspace_match = WorkspaceKnowledgeProfile(
        total_sources=5,
        is_homogeneous=False,
        modality_distribution={
            ContentModality.HIERARCHICAL_DOCUMENT.value: 0.60,
            ContentModality.TABULAR_DATASET.value: 0.40,
        },
        dominant_modality=ContentModality.HIERARCHICAL_DOCUMENT.value,
        cross_source_entity_overlap=["Revenue"],
        overall_domain="finance",
        file_profiles={f.source_id: f for f in files_match},
    )

    res = rule.evaluate(workspace_match, files_match)
    assert res.matched is True
    assert res.confidence_score == 0.95
    assert res.target_architecture == RagArchitectureId.HYBRID_RAG
    assert any("60.0% documents, 40.0% tabular datasets" in s for s in res.detected_signals)

    # Case 2: 4 documents, 1 tabular dataset -> 80% doc, 20% tabular -> 20.0% is NOT > 20.0%
    files_boundary = [
        create_file_profile("s1", ContentModality.HIERARCHICAL_DOCUMENT.value),
        create_file_profile("s2", ContentModality.HIERARCHICAL_DOCUMENT.value),
        create_file_profile("s3", ContentModality.HIERARCHICAL_DOCUMENT.value),
        create_file_profile("s4", ContentModality.HIERARCHICAL_DOCUMENT.value),
        create_file_profile("s5", ContentModality.TABULAR_DATASET.value),
    ]

    workspace_boundary = WorkspaceKnowledgeProfile(
        total_sources=5,
        is_homogeneous=False,
        modality_distribution={
            ContentModality.HIERARCHICAL_DOCUMENT.value: 0.80,
            ContentModality.TABULAR_DATASET.value: 0.20,
        },
        dominant_modality=ContentModality.HIERARCHICAL_DOCUMENT.value,
        cross_source_entity_overlap=[],
        overall_domain="finance",
        file_profiles={f.source_id: f for f in files_boundary},
    )

    res_boundary = rule.evaluate(workspace_boundary, files_boundary)
    # Must fail because 0.20 is not strictly > 0.20
    assert res_boundary.matched is False
    assert res_boundary.confidence_score == 0.0


def test_rule_tabular_dominant():
    rule = RuleTabularDominant()

    files = [
        create_file_profile("t1", ContentModality.TABULAR_DATASET.value, table_count=2, has_numerical=True),
        create_file_profile("t2", ContentModality.TABULAR_DATASET.value, table_count=1, has_numerical=True),
        create_file_profile("t3", ContentModality.TABULAR_DATASET.value, table_count=3, has_numerical=True),
        create_file_profile("d1", ContentModality.NARRATIVE_TEXT.value),
    ]

    workspace = WorkspaceKnowledgeProfile(
        total_sources=4,
        is_homogeneous=False,
        modality_distribution={
            ContentModality.TABULAR_DATASET.value: 0.75,
            ContentModality.NARRATIVE_TEXT.value: 0.25,
        },
        dominant_modality=ContentModality.TABULAR_DATASET.value,
        cross_source_entity_overlap=[],
        overall_domain="sales",
        file_profiles={f.source_id: f for f in files},
    )

    res = rule.evaluate(workspace, files)
    assert res.matched is True
    assert res.confidence_score == 0.90
    assert res.target_architecture == RagArchitectureId.STRUCTURED_DATA_RAG
    assert any("Tabular datasets represent 75.0%" in s for s in res.detected_signals)


def test_rule_hierarchical_longform():
    rule = RuleHierarchicalLongform()

    files = [
        create_file_profile("src_1", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=3),
        create_file_profile("src_2", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=2),
    ]

    workspace = WorkspaceKnowledgeProfile(
        total_sources=2,
        is_homogeneous=True,
        modality_distribution={
            ContentModality.HIERARCHICAL_DOCUMENT.value: 1.0,
        },
        dominant_modality=ContentModality.HIERARCHICAL_DOCUMENT.value,
        cross_source_entity_overlap=[],
        overall_domain="legal",
        file_profiles={f.source_id: f for f in files},
    )

    res = rule.evaluate(workspace, files)
    assert res.matched is True
    assert res.confidence_score == 0.80
    assert res.target_architecture == RagArchitectureId.KNOWLEDGE_RAG


def test_rule_scientific_research():
    rule = RuleScientificResearch()

    files = [
        create_file_profile("src_sci", ContentModality.SCIENTIFIC_RESEARCH.value, domain="research"),
    ]

    workspace = WorkspaceKnowledgeProfile(
        total_sources=1,
        is_homogeneous=True,
        modality_distribution={
            ContentModality.SCIENTIFIC_RESEARCH.value: 1.0,
        },
        dominant_modality=ContentModality.SCIENTIFIC_RESEARCH.value,
        cross_source_entity_overlap=[],
        overall_domain="research",
        file_profiles={f.source_id: f for f in files},
    )

    res = rule.evaluate(workspace, files)
    assert res.matched is True
    assert res.confidence_score == 0.85
    assert res.target_architecture == RagArchitectureId.RESEARCH_RAG


def test_rule_default_document_fallback():
    rule = RuleDefaultDocument()

    files = [create_file_profile("d1", ContentModality.NARRATIVE_TEXT.value)]
    workspace = WorkspaceKnowledgeProfile(
        total_sources=1,
        is_homogeneous=True,
        modality_distribution={ContentModality.NARRATIVE_TEXT.value: 1.0},
        dominant_modality=ContentModality.NARRATIVE_TEXT.value,
        cross_source_entity_overlap=[],
        overall_domain="general",
        file_profiles={f.source_id: f for f in files},
    )

    res = rule.evaluate(workspace, files)
    assert res.matched is True
    assert res.confidence_score == 0.60
    assert res.target_architecture == RagArchitectureId.DOCUMENT_RAG


def test_deterministic_alternatives_ordering(tmp_path):
    service = RecommendationService(storage_dir=tmp_path)

    files = [
        create_file_profile("s1", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=2),
        create_file_profile("s2", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=2),
        create_file_profile("s3", ContentModality.HIERARCHICAL_DOCUMENT.value, heading_depth=2),
        create_file_profile("s4", ContentModality.TABULAR_DATASET.value, has_numerical=True),
        create_file_profile("s5", ContentModality.TABULAR_DATASET.value, has_numerical=True),
    ]

    workspace = WorkspaceKnowledgeProfile(
        total_sources=5,
        is_homogeneous=False,
        modality_distribution={
            ContentModality.HIERARCHICAL_DOCUMENT.value: 0.60,
            ContentModality.TABULAR_DATASET.value: 0.40,
        },
        dominant_modality=ContentModality.HIERARCHICAL_DOCUMENT.value,
        cross_source_entity_overlap=[],
        overall_domain="finance",
        file_profiles={f.source_id: f for f in files},
    )

    res = service.evaluate(workspace, files)
    assert res.recommended_architecture == RagArchitectureId.HYBRID_RAG
    assert res.confidence_score == 0.95

    # Check alternative architectures list:
    alt_ids = [alt.architecture_id for alt in res.alternative_architectures]
    assert RagArchitectureId.HYBRID_RAG not in alt_ids
    assert RagArchitectureId.KNOWLEDGE_RAG in alt_ids
    assert RagArchitectureId.GRAPH_RAG in alt_ids  # Graph RAG included at end as advanced option
    assert len(alt_ids) == len(set(alt_ids))
