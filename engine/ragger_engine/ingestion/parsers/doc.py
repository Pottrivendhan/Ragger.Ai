"""Legacy Microsoft Word (.doc) binary format parser with explicit extraction limitations."""

import re
import uuid
from pathlib import Path
from typing import List

from ragger_engine.ingestion.exceptions import ExtractionLimitationError, ParserError
from ragger_engine.ingestion.models import (
    DocumentBlock,
    DocumentModel,
    SourceLocation,
    SourceRecord,
)
from ragger_engine.ingestion.parsers.base import BaseParser


class DOCParser(BaseParser):
    """Parses legacy binary Microsoft Word (.doc) documents.

    Note: As per architecture specifications, modern pure-Python runtimes do not
    natively support full proprietary CFBF Word formatting. If reliable continuous
    text cannot be extracted, it raises ExtractionLimitationError to prevent silent corruption.
    """

    def parse(self, file_path: Path, source: SourceRecord) -> DocumentModel:
        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
        except Exception as e:
            raise ParserError(f"Failed to read .doc file: {e}", parser_name="DOCParser")

        if not raw_bytes.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
            raise ParserError("File lacks valid Compound File Binary (CFBF) header for legacy Word format.", parser_name="DOCParser")

        # Attempt to recover continuous UTF-16LE or ASCII text runs from the binary stream
        blocks: List[DocumentBlock] = []
        warnings: List[str] = [
            "Legacy binary Word (.doc) format parsed via fallback stream extraction. For full formatting and table preservation, convert to modern .docx."
        ]

        # Extract UTF-16LE text runs (common in Word 97-2003)
        utf16_runs = re.findall(b"(?:[\x20-\x7E\r\n\t]\x00){4,}", raw_bytes)
        recovered_texts = []
        for run in utf16_runs:
            try:
                decoded = run.decode("utf-16le", errors="ignore").strip()
                if len(decoded) > 15 and not re.match(r"^[0-9a-fA-F_\-\s]+$", decoded):
                    recovered_texts.append(decoded)
            except Exception:
                pass

        # If UTF-16LE produced little, look for clean ASCII runs
        if len(recovered_texts) < 2:
            ascii_runs = re.findall(b"[\x20-\x7E\r\n\t]{20,}", raw_bytes)
            for run in ascii_runs:
                decoded = run.decode("latin-1", errors="ignore").strip()
                # Filter out obvious binary metadata headers
                if not decoded.startswith(("WordDocument", "Root Entry", "CompObj", "SummaryInformation")):
                    recovered_texts.append(decoded)

        # If no reliable text could be extracted, raise ExtractionLimitationError per requirement
        if not recovered_texts or sum(len(t) for t in recovered_texts) < 30:
            raise ExtractionLimitationError(
                "Legacy binary Word (.doc) format contains proprietary binary streams that cannot be reliably extracted without external converters. Please convert this file to modern .docx format.",
                format_name="doc",
            )

        block_idx = 0
        total_words = 0
        for text in recovered_texts:
            words = text.split()
            word_count = len(words)
            total_words += word_count

            blocks.append(
                DocumentBlock(
                    block_id=f"blk_{uuid.uuid4().hex[:8]}",
                    type="paragraph",
                    content=text,
                    location=SourceLocation(block_index=block_idx),
                    metadata={"word_count": word_count},
                )
            )
            block_idx += 1

        return DocumentModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="doc",
            metadata={"parser_mode": "cfbf_stream_fallback"},
            blocks=blocks,
            total_blocks=len(blocks),
            total_words=total_words,
            warnings=warnings,
        )
