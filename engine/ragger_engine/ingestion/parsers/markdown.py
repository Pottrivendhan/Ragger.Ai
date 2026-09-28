"""Markdown parser preserving AST heading hierarchy, code fences, lists, and tables."""

import re
import uuid
from pathlib import Path
from typing import List
import charset_normalizer

from ragger_engine.ingestion.exceptions import ParserError
from ragger_engine.ingestion.models import (
    DocumentBlock,
    DocumentModel,
    DocumentTable,
    SourceLocation,
    SourceRecord,
)
from ragger_engine.ingestion.parsers.base import BaseParser


class MarkdownParser(BaseParser):
    """Parses Markdown documents preserving native hierarchy without flattening."""

    def parse(self, file_path: Path, source: SourceRecord) -> DocumentModel:
        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
        except Exception as e:
            raise ParserError(f"Failed to read Markdown file: {e}", parser_name="MarkdownParser")

        detected = charset_normalizer.from_bytes(raw_bytes).best()
        encoding = detected.encoding if detected else "utf-8"
        text = raw_bytes.decode(encoding, errors="replace")

        lines = text.splitlines()
        blocks: List[DocumentBlock] = []
        tables: List[DocumentTable] = []
        warnings: List[str] = []
        total_words = 0
        block_idx = 0

        in_code_block = False
        code_buffer: List[str] = []
        code_lang = ""

        in_table = False
        table_buffer: List[str] = []

        para_buffer: List[str] = []

        def flush_paragraph():
            nonlocal block_idx, total_words
            if para_buffer:
                content = " ".join(para_buffer).strip()
                if content:
                    words = content.split()
                    total_words += len(words)
                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="paragraph",
                            content=content,
                            location=SourceLocation(block_index=block_idx),
                            metadata={"word_count": len(words)},
                        )
                    )
                    block_idx += 1
                para_buffer.clear()

        def flush_table():
            nonlocal block_idx, total_words
            if table_buffer:
                parsed_rows = []
                for tline in table_buffer:
                    cells = [c.strip() for c in tline.strip("|").split("|")]
                    # Skip separator line (e.g. ---|---)
                    if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                        continue
                    if cells:
                        parsed_rows.append(cells)

                if parsed_rows:
                    headers = parsed_rows[0]
                    rows = parsed_rows[1:] if len(parsed_rows) > 1 else []
                    tables.append(
                        DocumentTable(
                            headers=headers,
                            rows=rows,
                            location=SourceLocation(block_index=block_idx),
                        )
                    )
                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="table",
                            content="\n".join(table_buffer),
                            location=SourceLocation(block_index=block_idx),
                            metadata={"rows": len(parsed_rows), "cols": len(headers)},
                        )
                    )
                    block_idx += 1
                table_buffer.clear()

        for line in lines:
            stripped = line.strip()

            # Handle fenced code block
            if stripped.startswith("```"):
                if in_code_block:
                    # End code block
                    code_content = "\n".join(code_buffer)
                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="code",
                            content=code_content,
                            location=SourceLocation(block_index=block_idx),
                            metadata={"language": code_lang},
                        )
                    )
                    block_idx += 1
                    total_words += len(code_content.split())
                    code_buffer.clear()
                    in_code_block = False
                else:
                    flush_paragraph()
                    flush_table()
                    in_code_block = True
                    code_lang = stripped[3:].strip()
                continue

            if in_code_block:
                code_buffer.append(line)
                continue

            # Handle Markdown table lines (| ... |)
            if stripped.startswith("|") and stripped.endswith("|"):
                flush_paragraph()
                in_table = True
                table_buffer.append(stripped)
                continue
            elif in_table:
                flush_table()
                in_table = False

            # Empty line -> flush paragraph
            if not stripped:
                flush_paragraph()
                continue

            # Handle ATX Headings (# Heading)
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
            if heading_match:
                flush_paragraph()
                level = len(heading_match.group(1))
                h_text = heading_match.group(2).strip()
                words = h_text.split()
                total_words += len(words)

                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type="heading",
                        content=h_text,
                        level=level,
                        location=SourceLocation(block_index=block_idx),
                        metadata={"level": level, "word_count": len(words)},
                    )
                )
                block_idx += 1
                continue

            # Handle Blockquotes (> Quote)
            if stripped.startswith(">"):
                flush_paragraph()
                quote_text = stripped.lstrip("> ").strip()
                words = quote_text.split()
                total_words += len(words)

                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type="quote",
                        content=quote_text,
                        location=SourceLocation(block_index=block_idx),
                        metadata={"word_count": len(words)},
                    )
                )
                block_idx += 1
                continue

            # Handle List Items (- item, * item, 1. item)
            list_match = re.match(r"^([-*+]|\d+\.)\s+(.+)$", stripped)
            if list_match:
                flush_paragraph()
                item_text = list_match.group(2).strip()
                words = item_text.split()
                total_words += len(words)

                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type="list_item",
                        content=item_text,
                        location=SourceLocation(block_index=block_idx),
                        metadata={"word_count": len(words)},
                    )
                )
                block_idx += 1
                continue

            # Normal paragraph text accumulation
            para_buffer.append(stripped)

        # Final flushes
        flush_paragraph()
        flush_table()

        return DocumentModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="md",
            metadata={"total_lines": len(lines)},
            blocks=blocks,
            tables=tables,
            total_blocks=len(blocks),
            total_words=total_words,
            warnings=warnings,
        )
