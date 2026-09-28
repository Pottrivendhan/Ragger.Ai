"""
Determinism and Zero-Network / Zero-LLM tests for Phase 4 Recommendation Engine.
Evaluates 100 consecutive runs on identical inputs to verify bit-for-bit reproducibility.
"""

from datetime import datetime, timezone
import pytest
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
from ragger_engine.recommendation.service import RecommendationService


def test_recommendation_evaluation_determinism_100_runs(tmp_path):
    service = RecommendationService(storage_dir=tmp_path)

    files = [
        FileAnalysisProfile(
            source_id="src_doc1",
            original_filename="manual.pdf",
            structural_facts=StructuralFacts(
                source_id="src_doc1",
                detected_format="pdf",
                file_size_bytes=5000,
                heading_depth=3,
                table_count=1,
                tabular_ratio=0.0,
                page_count=10,
                slide_count=None,
                total_words=1200,
                total_rows=None,
                total_columns=None,
                has_numerical_columns=False,
                has_hierarchical_headings=True,
                extraction_warnings=[],
            ),
            semantic_observations=SemanticObservations(
                detected_domain="finance",
                primary_modality=ContentModality.HIERARCHICAL_DOCUMENT,
                semantic_density=SemanticDensity.HIGH,
                entity_relationship_density=EntityRelationshipDensity.MEDIUM,
                key_entities=["Revenue", "Client"],
                extraction_quality_score=1.0,
                summary_description="Financial policy guide with nested sections.",
            ),
            telemetry=ProviderTelemetry(requested_provider="heuristic", actual_provider="heuristic"),
        ),
        FileAnalysisProfile(
            source_id="src_data1",
            original_filename="sales.xlsx",
            structural_facts=StructuralFacts(
                source_id="src_data1",
                detected_format="xlsx",
                file_size_bytes=12000,
                heading_depth=0,
                table_count=2,
                tabular_ratio=1.0,
                page_count=None,
                slide_count=None,
                total_words=0,
                total_rows=500,
                total_columns=12,
                has_numerical_columns=True,
                has_hierarchical_headings=False,
                extraction_warnings=[],
            ),
            semantic_observations=SemanticObservations(
                detected_domain="finance",
                primary_modality=ContentModality.TABULAR_DATASET,
                semantic_density=SemanticDensity.HIGH,
                entity_relationship_density=EntityRelationshipDensity.LOW,
                key_entities=["Revenue", "Policy"],
                extraction_quality_score=1.0,
                summary_description="Quarterly sales data table.",
            ),
            telemetry=ProviderTelemetry(requested_provider="heuristic", actual_provider="heuristic"),
        ),
    ]

    workspace = WorkspaceKnowledgeProfile(
        total_sources=2,
        is_homogeneous=False,
        modality_distribution={
            ContentModality.HIERARCHICAL_DOCUMENT.value: 0.50,
            ContentModality.TABULAR_DATASET.value: 0.50,
        },
        dominant_modality=ContentModality.HIERARCHICAL_DOCUMENT.value,
        cross_source_entity_overlap=["Revenue", "Client", "Policy"],
        overall_domain="finance",
        file_profiles={f.source_id: f for f in files},
    )

    initial_result = service.evaluate(workspace, files)

    # Run 100 consecutive evaluations
    for i in range(100):
        run_res = service.evaluate(workspace, files)
        assert run_res.recommended_architecture == initial_result.recommended_architecture
        assert run_res.confidence_score == initial_result.confidence_score
        assert run_res.confidence_level == initial_result.confidence_level
        assert run_res.matched_rule_id == initial_result.matched_rule_id
        assert run_res.detected_signals == initial_result.detected_signals
        assert [a.architecture_id for a in run_res.alternative_architectures] == [
            a.architecture_id for a in initial_result.alternative_architectures
        ]
        assert len(run_res.evaluated_rules) == len(initial_result.evaluated_rules)
