"""Plain text parser with multi-encoding detection and paragraph preservation."""

import uuid
from pathlib import Path
from typing import List
import charset_normalizer

from ragger_engine.ingestion.exceptions import ParserError
from ragger_engine.ingestion.models import (
    DocumentBlock,
    DocumentModel,
    SourceLocation,
    SourceRecord,
)
from ragger_engine.ingestion.parsers.base import BaseParser


class TXTParser(BaseParser):
    """Parses plain text files with robust encoding detection into DocumentModel."""

    def parse(self, file_path: Path, source: SourceRecord) -> DocumentModel:
        warnings: List[str] = []

        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
        except Exception as e:
            raise ParserError(f"Failed to read TXT file: {e}", parser_name="TXTParser")

        # Detect encoding using charset-normalizer
        detected = charset_normalizer.from_bytes(raw_bytes).best()
        encoding = detected.encoding if detected else "utf-8"

        try:
            text_content = raw_bytes.decode(encoding)
        except Exception:
            warnings.append(f"Primary encoding '{encoding}' failed; falling back to UTF-8 with replacement.")
            text_content = raw_bytes.decode("utf-8", errors="replace")

        blocks: List[DocumentBlock] = []
        total_words = 0
        block_idx = 0
        char_offset = 0

        # Split on double newlines to isolate paragraphs
        raw_paras = text_content.split("\n\n")

        for para in raw_paras:
            clean_para = para.strip()
            if not clean_para:
                char_offset += len(para) + 2
                continue

            words = clean_para.split()
            word_count = len(words)
            total_words += word_count

            # Simple heading heuristic: short line, titlecase or uppercase, without period
            is_heading = (
                word_count <= 8
                and "\n" not in clean_para
                and not clean_para.endswith((".", ":", ";"))
                and (clean_para.isupper() or clean_para.istitle())
            )

            blocks.append(
                DocumentBlock(
                    block_id=f"blk_{uuid.uuid4().hex[:8]}",
                    type="heading" if is_heading else "paragraph",
                    content=clean_para,
                    level=2 if is_heading else None,
                    location=SourceLocation(block_index=block_idx, char_offset=char_offset),
                    metadata={"word_count": word_count},
                )
            )
            block_idx += 1
            char_offset += len(para) + 2

        return DocumentModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="txt",
            metadata={"detected_encoding": encoding, "file_size": len(raw_bytes)},
            blocks=blocks,
            total_blocks=len(blocks),
            total_words=total_words,
            warnings=warnings,
        )
