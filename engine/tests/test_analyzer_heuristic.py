"""Automated tests for Phase 3 DeterministicHeuristicAnalyzer and structural facts."""

import pytest
from pathlib import Path
from ragger_engine.analyzer.models import ContentModality, FileAnalysisProfile, SemanticDensity
from ragger_engine.analyzer.service import AnalyzerService
from ragger_engine.ingestion.service import IngestionService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def ingestion_and_analyzer(tmp_path):
    """Initializes isolated ingestion and analyzer services with temporary storage."""
    ingest = IngestionService(storage_dir=tmp_path / "ingest_storage")
    analyzer = AnalyzerService(ingestion_service=ingest, storage_dir=tmp_path / "analyzer_storage")
    return ingest, analyzer


@pytest.mark.asyncio
async def test_analyze_real_pdf_hierarchical_document(ingestion_and_analyzer):
    """Real PDF must be observed with hierarchical heading depth and narrative structure."""
    ingest, analyzer = ingestion_and_analyzer
    pdf_path = FIXTURES_DIR / "sample.pdf"

    # Step 1: Ingest via Phase 2
    ingest_result = ingest.ingest(pdf_path)
    source_id = ingest_result.source.source_id

    # Step 2: Analyze via Phase 3
    profile = await analyzer.analyze_source(source_id, provider_name="heuristic_offline")

    assert isinstance(profile, FileAnalysisProfile)
    assert profile.source_id == source_id
    assert profile.original_filename == "sample.pdf"

    # Authoritative structural facts from Phase 2
    assert profile.structural_facts.heading_depth >= 2
    assert profile.structural_facts.page_count == 2
    assert profile.structural_facts.tabular_ratio < 0.5
    assert profile.structural_facts.has_hierarchical_headings is True

    # Semantic observations
    assert profile.primary_modality in (ContentModality.HIERARCHICAL_DOCUMENT, ContentModality.NARRATIVE_TEXT)
    assert profile.semantic_density in (SemanticDensity.LOW, SemanticDensity.MEDIUM, SemanticDensity.HIGH)
    assert len(profile.semantic_observations.observed_characteristics) >= 2
    assert profile.semantic_observations.extraction_quality_score >= 0.8

    # Objective summary without recommendations
    summary = profile.summary_description
    assert len(summary) > 20
    assert "should use" not in summary.lower()
    assert "rag" not in summary.lower()


@pytest.mark.asyncio
async def test_analyze_real_xlsx_tabular_dataset(ingestion_and_analyzer):
    """Real XLSX must be observed strictly as tabular dataset with numerical metrics."""
    ingest, analyzer = ingestion_and_analyzer
    xlsx_path = FIXTURES_DIR / "sample.xlsx"

    ingest_result = ingest.ingest(xlsx_path)
    source_id = ingest_result.source.source_id

    profile = await analyzer.analyze_source(source_id, provider_name="heuristic_offline")

    assert profile.primary_modality == ContentModality.TABULAR_DATASET
    assert profile.structural_facts.tabular_ratio == 1.0
    assert profile.structural_facts.has_numerical_columns is True
    assert profile.structural_facts.table_count == 2
    assert profile.structural_facts.total_rows == 5  # 3 rows Sales + 2 rows Regions

    # Telemetry check
    assert profile.telemetry.requested_provider == "heuristic_offline"
    assert profile.telemetry.actual_provider == "heuristic_offline"
    assert profile.telemetry.fallback_used is False


@pytest.mark.asyncio
async def test_analyze_csv_and_markdown(ingestion_and_analyzer):
    """Validates structural and semantic observation for CSV and Markdown."""
    ingest, analyzer = ingestion_and_analyzer

    csv_res = ingest.ingest(FIXTURES_DIR / "sample.csv")
    csv_prof = await analyzer.analyze_source(csv_res.source.source_id)
    assert csv_prof.primary_modality == ContentModality.TABULAR_DATASET

    md_res = ingest.ingest(FIXTURES_DIR / "sample.md")
    md_prof = await analyzer.analyze_source(md_res.source.source_id)
    assert md_prof.structural_facts.heading_depth >= 1
    assert md_prof.primary_modality in (ContentModality.HIERARCHICAL_DOCUMENT, ContentModality.NARRATIVE_TEXT)
