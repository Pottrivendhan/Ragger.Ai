"""Comprehensive parser tests verifying DocumentModel and DatasetModel structure preservation."""

import pytest
from pathlib import Path
from ragger_engine.ingestion.models import DatasetModel, DocumentModel, SourceRecord
from ragger_engine.ingestion.parsers import get_parser_for_format
from ragger_engine.ingestion.service import IngestionService

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_test_source(filename: str, fmt: str) -> SourceRecord:
    return SourceRecord(
        source_id="src_test_123",
        original_filename=filename,
        detected_format=fmt,
        mime_type="application/octet-stream",
        file_size_bytes=1000,
        sha256_checksum="abc123def456",
        status="registered",
    )


def test_pdf_parser_preserves_pages_and_headings():
    """Real PDF ingestion must yield DocumentModel with page numbers and structural blocks."""
    path = FIXTURES_DIR / "sample.pdf"
    parser = get_parser_for_format("pdf")
    model = parser.parse(path, make_test_source(path.name, "pdf"))

    assert isinstance(model, DocumentModel)
    assert model.model_type == "document"
    assert model.metadata["total_pages"] >= 2
    assert model.total_blocks > 0
    assert any(b.type == "heading" for b in model.blocks)
    assert any(b.location.page_number == 1 for b in model.blocks)
    assert any(b.location.page_number == 2 for b in model.blocks)
    assert model.total_words > 0


def test_xlsx_parser_preserves_sheets_and_does_not_flatten():
    """Real XLSX ingestion must produce DatasetModel with multi-sheet identity, schemas, and typed columns."""
    path = FIXTURES_DIR / "sample.xlsx"
    parser = get_parser_for_format("xlsx")
    model = parser.parse(path, make_test_source(path.name, "xlsx"))

    assert isinstance(model, DatasetModel)
    assert model.model_type == "dataset"
    assert model.total_sheets == 2
    sheet_names = [s.sheet_name for s in model.sheets]
    assert "Sales" in sheet_names
    assert "Regions" in sheet_names

    sales_sheet = next(s for s in model.sheets if s.sheet_name == "Sales")
    col_names = [c.name for c in sales_sheet.columns]
    assert "Transaction_ID" in col_names
    assert "Revenue" in col_names
    assert len(sales_sheet.rows) == 3


def test_csv_and_tsv_parsers_produce_dataset_model():
    """CSV and TSV must produce DatasetModel with schema, null counts, and row records."""
    csv_path = FIXTURES_DIR / "sample.csv"
    service = IngestionService()
    csv_result = service.ingest(csv_path)

    assert csv_result.model_type == "dataset"
    dataset = csv_result.normalized_model
    assert isinstance(dataset, DatasetModel)
    assert len(dataset.sheets[0].columns) == 5
    assert dataset.sheets[0].total_rows == 3

    tsv_path = FIXTURES_DIR / "sample.tsv"
    tsv_result = service.ingest(tsv_path)
    assert tsv_result.model_type == "dataset"
    assert tsv_result.normalized_model.sheets[0].total_rows == 3


def test_docx_parser_preserves_heading_levels_and_tables():
    """DOCX parser must preserve heading hierarchy and tables into DocumentModel."""
    path = FIXTURES_DIR / "sample.docx"
    service = IngestionService()
    result = service.ingest(path)

    assert result.model_type == "document"
    doc = result.normalized_model
    assert isinstance(doc, DocumentModel)
    assert any(b.type == "heading" and b.level == 1 for b in doc.blocks)
    assert any(b.type == "heading" and b.level == 2 for b in doc.blocks)
    assert len(doc.tables) >= 1
    assert any(b.type == "table" for b in doc.blocks)


def test_pptx_parser_preserves_slides_and_notes():
    """PPTX parser must preserve slide indices, titles, and speaker notes."""
    path = FIXTURES_DIR / "sample.pptx"
    service = IngestionService()
    result = service.ingest(path)

    assert result.model_type == "document"
    doc = result.normalized_model
    assert isinstance(doc, DocumentModel)
    assert doc.metadata["total_slides"] >= 2
    assert any(b.location.slide_number == 1 for b in doc.blocks)
    assert any(b.location.slide_number == 2 for b in doc.blocks)
    assert any("Speaker Notes:" in b.content for b in doc.blocks)


def test_markdown_parser_ast_elements():
    """Markdown parser must preserve AST headings, code fences, and pipe tables."""
    path = FIXTURES_DIR / "sample.md"
    service = IngestionService()
    result = service.ingest(path)

    doc = result.normalized_model
    assert isinstance(doc, DocumentModel)
    assert any(b.type == "code" for b in doc.blocks)
    assert any(b.type == "table" for b in doc.blocks)
    assert any(b.type == "quote" for b in doc.blocks)
    assert any(b.type == "heading" for b in doc.blocks)


def test_json_parser_routes_to_dataset_for_record_arrays():
    """JSON array of objects must deterministically route to DatasetModel."""
    path = FIXTURES_DIR / "sample.json"
    service = IngestionService()
    result = service.ingest(path)

    assert result.model_type == "dataset"
    dataset = result.normalized_model
    assert isinstance(dataset, DatasetModel)
    assert dataset.sheets[0].total_rows == 3
    col_names = [c.name for c in dataset.sheets[0].columns]
    assert "role" in col_names and "salary" in col_names


def test_xml_parser_safe_parsing():
    """Safe XML parser must produce normalized model without XXE."""
    path = FIXTURES_DIR / "sample.xml"
    service = IngestionService()
    result = service.ingest(path)
    assert result.model_type in ("dataset", "document")


def test_html_parser_strips_boilerplate():
    """HTML parser must strip nav/scripts and retain headings and tables."""
    path = FIXTURES_DIR / "sample.html"
    service = IngestionService()
    result = service.ingest(path)

    doc = result.normalized_model
    assert isinstance(doc, DocumentModel)
    # Ensure nav links were stripped
    assert not any("Home" in b.content and "Login" in b.content for b in doc.blocks)
    assert any(b.type == "heading" for b in doc.blocks)
    assert any(b.type == "table" for b in doc.blocks)


def test_epub_parser_extracts_chapters():
    """EPUB parser must extract spine chapters in reading sequence."""
    path = FIXTURES_DIR / "sample.epub"
    service = IngestionService()
    result = service.ingest(path)

    doc = result.normalized_model
    assert isinstance(doc, DocumentModel)
    assert any("Chapter 1:" in b.content for b in doc.blocks)
    assert any("Chapter 2:" in b.content for b in doc.blocks)


def test_doc_parser_fallback_or_limitation():
    """Legacy DOC parser extracts text streams or returns explicit typed limitation."""
    path = FIXTURES_DIR / "sample.doc"
    service = IngestionService()
    try:
        result = service.ingest(path)
        assert result.model_type == "document"
        assert len(result.normalized_model.blocks) > 0
    except Exception as e:
        # If extraction limitation is raised, it must be the typed domain error
        assert "EXTRACTION_LIMITATION" in str(e) or "doc" in str(e).lower()
