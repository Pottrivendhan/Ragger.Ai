"""Security tests verifying path traversal guards, XXE prevention, and quota limits."""

import pytest
from pathlib import Path
from ragger_engine.ingestion.exceptions import (
    FileTooLargeError,
    PathTraversalError,
    SecurityLimitExceededError,
)
from ragger_engine.ingestion.security import (
    ArchiveSecurityValidator,
    FileQuotaValidator,
    PathSecurityValidator,
)
from ragger_engine.ingestion.parsers.xml_parser import XMLParser
from ragger_engine.ingestion.models import SourceRecord

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def test_path_traversal_prevention():
    """PathSecurityValidator must reject paths resolving outside allowed roots."""
    allowed_root = FIXTURES_DIR.resolve()
    outside_file = Path(__file__).resolve()  # Outside fixtures/

    with pytest.raises(PathTraversalError):
        PathSecurityValidator.validate_safe_path(outside_file, allowed_roots=[allowed_root])


def test_file_quota_enforcement():
    """FileQuotaValidator must reject files exceeding maximum permitted bytes."""
    sample_file = FIXTURES_DIR / "sample.txt"
    # Set cap lower than sample file size (e.g. 10 bytes)
    with pytest.raises(FileTooLargeError) as exc_info:
        FileQuotaValidator.validate_size(sample_file, max_bytes=10)
    assert exc_info.value.code == "FILE_TOO_LARGE"


def test_xxe_entity_expansion_blocked():
    """Safe XML parser must reject or block entity resolution for external DTDs."""
    xxe_file = FIXTURES_DIR / "xxe_attack.xml"
    parser = XMLParser()
    source = SourceRecord(
        source_id="src_sec_test",
        original_filename="xxe_attack.xml",
        detected_format="xml",
        mime_type="application/xml",
        file_size_bytes=xxe_file.stat().st_size,
        sha256_checksum="abc",
    )

    # defusedxml will either raise DefusedXmlException -> SecurityLimitExceededError
    # or sanitize the external entity without leaking filesystem files
    try:
        model = parser.parse(xxe_file, source)
        # Verify /etc/passwd contents are NOT present in parsed text
        all_text = " ".join(b.content for b in model.blocks)
        assert "root:x:" not in all_text
    except SecurityLimitExceededError as sec_err:
        assert sec_err.code == "XML_SECURITY_ERROR"


def test_empty_archive_rejected():
    """ArchiveSecurityValidator must reject 0-byte archives."""
    empty_path = FIXTURES_DIR / "empty.txt"
    with pytest.raises(SecurityLimitExceededError):
        ArchiveSecurityValidator.validate_zip_archive(empty_path)
