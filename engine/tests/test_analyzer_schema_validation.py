"""Tests for Schema validation, repair retry loops, and provider fallback telemetry."""

import pytest
from unittest.mock import AsyncMock, patch
from ragger_engine.analyzer.models import StructuralFacts
from ragger_engine.analyzer.providers.ollama import OllamaAnalyzerProvider
from ragger_engine.ingestion.models import AnalysisSample, SourceRecord


@pytest.fixture
def mock_source_and_facts():
    source = SourceRecord(
        source_id="src_val_test",
        original_filename="financial_report.pdf",
        detected_format="pdf",
        mime_type="application/pdf",
        file_size_bytes=1024,
        sha256_checksum="abc",
    )
    facts = StructuralFacts(
        source_id="src_val_test",
        detected_format="pdf",
        file_size_bytes=1024,
        heading_depth=2,
        table_count=1,
        tabular_ratio=0.2,
        page_count=3,
        total_words=450,
        has_hierarchical_headings=True,
    )
    sample = AnalysisSample(
        source_id="src_val_test",
        sample_type="document",
        token_count_estimate=200,
        head_sample="Executive Summary. Financial performance increased by 14 percent across divisions.",
    )
    return source, facts, sample


@pytest.mark.asyncio
async def test_ollama_unreachable_fallback_telemetry(mock_source_and_facts):
    """When Ollama cannot be contacted, provider must explicitly record fallback in telemetry."""
    source, facts, sample = mock_source_and_facts
    # Points to an unallocated port to trigger immediate connection error
    provider = OllamaAnalyzerProvider(base_url="http://127.0.0.1:59999", enable_fallback=True)

    observations, telemetry = await provider.analyze(source, facts, sample)

    # Telemetry must show that Ollama was requested but fallback was used
    assert telemetry.requested_provider == "ollama"
    assert telemetry.actual_provider == "heuristic_offline"
    assert telemetry.fallback_used is True
    assert telemetry.fallback_reason is not None
    assert "connection" in telemetry.fallback_reason.lower() or "59999" in telemetry.fallback_reason

    # Observations should still be valid and populated via heuristic baseline
    assert observations.detected_domain == "finance"
    assert observations.primary_modality.value in ("hierarchical_document", "narrative_text")


@pytest.mark.asyncio
async def test_json_markdown_fence_cleaning(mock_source_and_facts):
    """Verifies that markdown code fences around JSON are safely parsed."""
    source, facts, sample = mock_source_and_facts
    provider = OllamaAnalyzerProvider()

    raw_markdown = """```json
    {
      "detected_domain": "technology",
      "primary_modality": "hierarchical_document",
      "secondary_modalities": [],
      "semantic_density": "high",
      "entity_relationship_density": "medium",
      "key_entities": ["Kubernetes", "Docker"],
      "primary_language": "en",
      "extraction_quality_score": 1.0,
      "observed_characteristics": ["Contains technical specs"],
      "summary_description": "Technical specification document describing containerized infrastructure."
    }
    ```"""

    extracted = provider._extract_json(raw_markdown)
    assert extracted["detected_domain"] == "technology"
    assert extracted["key_entities"] == ["Kubernetes", "Docker"]
