"""Tests for deterministic Workspace Knowledge Synthesis."""

import pytest
from pathlib import Path
from ragger_engine.analyzer.service import AnalyzerService
from ragger_engine.ingestion.service import IngestionService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def isolated_services(tmp_path):
    ingest = IngestionService(storage_dir=tmp_path / "ingest_storage")
    analyzer = AnalyzerService(ingestion_service=ingest, storage_dir=tmp_path / "analyzer_storage")
    return ingest, analyzer


@pytest.mark.asyncio
async def test_deterministic_workspace_synthesis(isolated_services):
    """Multi-source workspace must be synthesized deterministically with distribution and overlap."""
    ingest, analyzer = isolated_services

    # Ingest PDF (Narrative/Hierarchical) and XLSX (Tabular)
    res_pdf = ingest.ingest(FIXTURES_DIR / "sample.pdf")
    res_xlsx = ingest.ingest(FIXTURES_DIR / "sample.xlsx")

    # Analyze both sources
    prof_pdf = await analyzer.analyze_source(res_pdf.source.source_id)
    prof_xlsx = await analyzer.analyze_source(res_xlsx.source.source_id)

    assert prof_pdf.source_id != prof_xlsx.source_id

    # Synthesize workspace
    workspace = analyzer.synthesize_workspace(workspace_id="test_ws")

    assert workspace.total_sources == 2
    # One is hierarchical/narrative, one is tabular -> heterogeneous!
    assert workspace.is_homogeneous is False
    assert len(workspace.modality_distribution) == 2
    assert "tabular_dataset" in workspace.modality_distribution

    # Modality shares should equal 1.0 in total
    total_share = sum(workspace.modality_distribution.values())
    assert abs(total_share - 1.0) < 0.001

    # Persistence verification: re-instantiate service and check loaded workspace
    reloaded_analyzer = AnalyzerService(ingestion_service=ingest, storage_dir=analyzer.storage_dir)
    cached_ws = reloaded_analyzer.get_workspace_profile()
    assert cached_ws is not None
    assert cached_ws.total_sources == 2
    assert cached_ws.is_homogeneous is False
