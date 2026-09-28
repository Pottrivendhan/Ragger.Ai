"""Determinism tests verifying identical raw bytes yield identical models and samples."""

from pathlib import Path
from ragger_engine.ingestion.service import IngestionService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_document_ingestion_determinism():
    """Two independent ingestion runs on the same PDF must produce identical normalized models and samples."""
    service1 = IngestionService()
    service2 = IngestionService()
    pdf_path = FIXTURES_DIR / "sample.pdf"

    res1 = service1.ingest(pdf_path, custom_source_id="src_fixed_1")
    res2 = service2.ingest(pdf_path, custom_source_id="src_fixed_1")

    # Verify identical detection
    assert res1.detected_type.format == res2.detected_type.format
    assert res1.detected_type.confidence == res2.detected_type.confidence

    # Verify identical normalized document structure
    doc1 = res1.normalized_model
    doc2 = res2.normalized_model
    assert doc1.total_blocks == doc2.total_blocks
    assert doc1.total_words == doc2.total_words
    assert [b.content for b in doc1.blocks] == [b.content for b in doc2.blocks]
    assert [b.type for b in doc1.blocks] == [b.type for b in doc2.blocks]

    # Verify identical analysis sample
    assert res1.sample.heading_outline == res2.sample.heading_outline
    assert res1.sample.head_sample == res2.sample.head_sample
    assert res1.sample.token_count_estimate == res2.sample.token_count_estimate


def test_dataset_ingestion_determinism():
    """Two independent ingestion runs on the same XLSX must yield identical sheets and deterministic row samples."""
    service = IngestionService()
    xlsx_path = FIXTURES_DIR / "sample.xlsx"

    res1 = service.ingest(xlsx_path, custom_source_id="src_fixed_2")
    res2 = service.ingest(xlsx_path, custom_source_id="src_fixed_2")

    ds1 = res1.normalized_model
    ds2 = res2.normalized_model

    assert ds1.total_sheets == ds2.total_sheets
    assert [s.sheet_name for s in ds1.sheets] == [s.sheet_name for s in ds2.sheets]
    assert [c.name for c in ds1.sheets[0].columns] == [c.name for c in ds2.sheets[0].columns]
    assert [c.inferred_type for c in ds1.sheets[0].columns] == [c.inferred_type for c in ds2.sheets[0].columns]

    # Verify seeded random row samples are 100% identical
    assert res1.sample.sampled_rows == res2.sample.sampled_rows
    assert res1.sample.token_count_estimate == res2.sample.token_count_estimate
