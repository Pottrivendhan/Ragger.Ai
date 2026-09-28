"""HTML parser stripping boilerplate and preserving headings, paragraphs, and tables."""

import uuid
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup
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


class HTMLParser(BaseParser):
    """Parses HTML documents with BeautifulSoup, stripping scripts and boilerplate."""

    def parse(self, file_path: Path, source: SourceRecord) -> DocumentModel:
        try:
            with open(file_path, "rb") as f:
                raw_bytes = f.read()
        except Exception as e:
            raise ParserError(f"Failed to read HTML file: {e}", parser_name="HTMLParser")

        detected = charset_normalizer.from_bytes(raw_bytes).best()
        encoding = detected.encoding if detected else "utf-8"
        html_text = raw_bytes.decode(encoding, errors="replace")

        soup = BeautifulSoup(html_text, "html.parser")

        # Strip non-content and unsafe tags (prevent JS execution / DOM injection)
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg", "iframe"]):
            tag.decompose()

        title = file_path.stem
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        blocks: List[DocumentBlock] = []
        tables: List[DocumentTable] = []
        total_words = 0
        block_idx = 0

        # Traverse content elements in body
        body = soup.body or soup

        for elem in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table", "blockquote", "pre"]):
            tag_name = elem.name.lower()

            if tag_name.startswith("h") and len(tag_name) == 2 and tag_name[1].isdigit():
                level = int(tag_name[1])
                text = elem.get_text(strip=True)
                if text:
                    words = text.split()
                    total_words += len(words)
                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="heading",
                            content=text,
                            level=level,
                            location=SourceLocation(block_index=block_idx),
                            metadata={"tag": tag_name, "word_count": len(words)},
                        )
                    )
                    block_idx += 1

            elif tag_name in ("p", "blockquote"):
                text = elem.get_text(strip=True)
                if text:
                    words = text.split()
                    total_words += len(words)
                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="quote" if tag_name == "blockquote" else "paragraph",
                            content=text,
                            location=SourceLocation(block_index=block_idx),
                            metadata={"word_count": len(words)},
                        )
                    )
                    block_idx += 1

            elif tag_name == "li":
                text = elem.get_text(strip=True)
                if text:
                    words = text.split()
                    total_words += len(words)
                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="list_item",
                            content=text,
                            location=SourceLocation(block_index=block_idx),
                            metadata={"word_count": len(words)},
                        )
                    )
                    block_idx += 1

            elif tag_name == "pre":
                text = elem.get_text()
                if text.strip():
                    words = text.split()
                    total_words += len(words)
                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="code",
                            content=text.strip(),
                            location=SourceLocation(block_index=block_idx),
                            metadata={"word_count": len(words)},
                        )
                    )
                    block_idx += 1

            elif tag_name == "table":
                # Extract HTML table
                table_rows: List[List[str]] = []
                for tr in elem.find_all("tr"):
                    cells = [td.get_text(strip=True).replace("\n", " ") for td in tr.find_all(["th", "td"])]
                    if cells:
                        table_rows.append(cells)

                if table_rows:
                    headers = table_rows[0]
                    data_rows = table_rows[1:] if len(table_rows) > 1 else []

                    tables.append(
                        DocumentTable(
                            headers=headers,
                            rows=data_rows,
                            location=SourceLocation(block_index=block_idx),
                        )
                    )

                    md_lines = [" | ".join(headers), " | ".join(["---"] * len(headers))]
                    for r in data_rows:
                        md_lines.append(" | ".join(r))

                    blocks.append(
                        DocumentBlock(
                            block_id=f"blk_{uuid.uuid4().hex[:8]}",
                            type="table",
                            content="\n".join(md_lines),
                            location=SourceLocation(block_index=block_idx),
                            metadata={"rows": len(table_rows), "cols": len(headers)},
                        )
                    )
                    block_idx += 1

        return DocumentModel(
            source_id=source.source_id,
            title=str(title),
            format="html",
            metadata={"extracted_tables": len(tables)},
            blocks=blocks,
            tables=tables,
            total_blocks=len(blocks),
            total_words=total_words,
        )
