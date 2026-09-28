"""Comprehensive detection tests across all 14 supported formats and edge cases."""

import pytest
from pathlib import Path
from ragger_engine.ingestion.detector import FileDetector

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize(
    "filename,expected_format",
    [
        ("sample.pdf", "pdf"),
        ("sample.docx", "docx"),
        ("sample.pptx", "pptx"),
        ("sample.xlsx", "xlsx"),
        ("sample.xls", "xls"),
        ("sample.csv", "csv"),
        ("sample.tsv", "tsv"),
        ("sample.txt", "txt"),
        ("sample.md", "md"),
        ("sample.json", "json"),
        ("sample.xml", "xml"),
        ("sample.html", "html"),
        ("sample.epub", "epub"),
        ("sample.doc", "doc"),
    ],
)
def test_detection_all_supported_formats(filename: str, expected_format: str):
    """Verifies that all 14 real test fixtures are accurately detected."""
    path = FIXTURES_DIR / filename
    assert path.exists(), f"Fixture {filename} does not exist."
    result = FileDetector.detect_file(path)
    assert result.format == expected_format
    assert result.confidence >= 0.8
    assert result.mime_type != "application/octet-stream"


def test_detection_disguised_file_extension():
    """Verifies that detection identifies true file format even when extension is deceptive."""
    # A CSV file with .pdf extension should be detected as CSV via magic bytes / text sniffing
    csv_bytes = b"col1,col2,col3\nval1,val2,val3\n"
    fake_pdf = FIXTURES_DIR / "fake_extension.pdf"
    try:
        with open(fake_pdf, "wb") as f:
            f.write(csv_bytes)
        result = FileDetector.detect_file(fake_pdf)
        assert result.format == "csv"
        assert any("Extension '.pdf' does not match" in w for w in result.warnings)
    finally:
        if fake_pdf.exists():
            fake_pdf.unlink()


def test_detection_empty_file():
    """Verifies that 0-byte files are flagged as empty."""
    empty_path = FIXTURES_DIR / "empty.txt"
    result = FileDetector.detect_file(empty_path)
    assert result.format == "empty"
    assert "empty" in result.warnings[0].lower()


def test_detection_nonexistent_file():
    """Verifies that nonexistent files return unknown with error detection method."""
    nonexistent = FIXTURES_DIR / "does_not_exist.xyz"
    result = FileDetector.detect_file(nonexistent)
    assert result.format == "unknown"
    assert result.detection_method == "error"
