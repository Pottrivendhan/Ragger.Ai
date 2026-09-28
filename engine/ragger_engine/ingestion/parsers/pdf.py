"""PDF format parser preserving page boundaries, headings, and paragraphs."""

import uuid
from pathlib import Path
from typing import List
from pypdf import PdfReader

from ragger_engine.ingestion.exceptions import ParserError
from ragger_engine.ingestion.models import (
    DocumentBlock,
    DocumentModel,
    SourceLocation,
    SourceRecord,
)
from ragger_engine.ingestion.parsers.base import BaseParser


class PDFParser(BaseParser):
    """Parses PDF documents into a structured DocumentModel."""

    def parse(self, file_path: Path, source: SourceRecord) -> DocumentModel:
        try:
            reader = PdfReader(str(file_path))
        except Exception as e:
            raise ParserError(f"Failed to read PDF file: {e}", parser_name="PDFParser")

        blocks: List[DocumentBlock] = []
        warnings: List[str] = []
        total_words = 0
        block_idx = 0

        total_pages = len(reader.pages)
        if total_pages == 0:
            warnings.append("PDF contains 0 pages.")

        for page_num, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception as e:
                warnings.append(f"Failed to extract text from page {page_num}: {e}")
                continue

            lines = [line.strip() for line in page_text.splitlines() if line.strip()]

            # Group lines into paragraphs, but isolate headings as distinct blocks
            elements: List[tuple[str, bool]] = []
            current_paragraph_lines: List[str] = []

            for line in lines:
                words = line.split()
                is_heading = (
                    len(words) <= 12
                    and not line.endswith((".", ":", ";", ","))
                    and (line.isupper() or line.istitle())
                )
                if is_heading:
                    if current_paragraph_lines:
                        elements.append((" ".join(current_paragraph_lines), False))
                        current_paragraph_lines = []
                    elements.append((line, True))
                else:
                    current_paragraph_lines.append(line)

            if current_paragraph_lines:
                elements.append((" ".join(current_paragraph_lines), False))

            for content, is_heading in elements:
                words = content.split()
                word_count = len(words)
                total_words += word_count

                block_type = "heading" if is_heading else "paragraph"
                level = 2 if is_heading else None

                location = SourceLocation(
                    page_number=page_num,
                    block_index=block_idx,
                )

                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type=block_type,
                        content=content,
                        level=level,
                        location=location,
                        metadata={"page": page_num, "word_count": word_count},
                    )
                )
                block_idx += 1

            # Insert page break marker
            if page_num < total_pages:
                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type="page_break",
                        content=f"--- Page {page_num} End ---",
                        location=SourceLocation(page_number=page_num, block_index=block_idx),
                        metadata={"page": page_num},
                    )
                )
                block_idx += 1

        title = reader.metadata.title if reader.metadata and reader.metadata.title else file_path.stem

        return DocumentModel(
            source_id=source.source_id,
            title=str(title),
            format="pdf",
            metadata={
                "total_pages": total_pages,
                "author": reader.metadata.author if reader.metadata else None,
                "producer": reader.metadata.producer if reader.metadata else None,
            },
            blocks=blocks,
            total_blocks=len(blocks),
            total_words=total_words,
            warnings=warnings,
        )
