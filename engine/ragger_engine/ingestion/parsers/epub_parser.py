"""EPUB book parser safely extracting spine chapters and headings into DocumentModel."""

import uuid
import zipfile
from pathlib import Path
from typing import List
from bs4 import BeautifulSoup
import defusedxml.ElementTree as ET

from ragger_engine.ingestion.exceptions import ParserError
from ragger_engine.ingestion.models import (
    DocumentBlock,
    DocumentModel,
    SourceLocation,
    SourceRecord,
)
from ragger_engine.ingestion.parsers.base import BaseParser
from ragger_engine.ingestion.security import ArchiveSecurityValidator


class EPUBParser(BaseParser):
    """Safely extracts EPUB books through container and spine manifest parsing."""

    def parse(self, file_path: Path, source: SourceRecord) -> DocumentModel:
        ArchiveSecurityValidator.validate_zip_archive(file_path)

        blocks: List[DocumentBlock] = []
        warnings: List[str] = []
        total_words = 0
        block_idx = 0
        title = file_path.stem

        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                # 1. Locate root OPF file from META-INF/container.xml
                container_bytes = zf.read("META-INF/container.xml")
                container_xml = ET.fromstring(container_bytes)
                rootfile_elem = container_xml.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")

                opf_path = rootfile_elem.get("full-path") if rootfile_elem is not None else "content.opf"
                opf_bytes = zf.read(opf_path)
                opf_xml = ET.fromstring(opf_bytes)

                opf_dir = Path(opf_path).parent

                # Extract title if present in metadata
                title_elem = opf_xml.find(".//{http://purl.org/dc/elements/1.1/}title")
                if title_elem is not None and title_elem.text:
                    title = title_elem.text.strip()

                # Build manifest map (id -> href)
                manifest = {}
                for item in opf_xml.findall(".//{http://www.idpf.org/2007/opf}item"):
                    manifest[item.get("id")] = item.get("href")

                # Read spine in sequence
                spine_items = []
                for itemref in opf_xml.findall(".//{http://www.idpf.org/2007/opf}itemref"):
                    idref = itemref.get("idref")
                    if idref in manifest:
                        spine_items.append(manifest[idref])

                # Process each chapter XHTML
                for chapter_idx, href in enumerate(spine_items, start=1):
                    full_href = (opf_dir / href).as_posix() if str(opf_dir) != "." else href
                    try:
                        chapter_bytes = zf.read(full_href)
                    except KeyError:
                        continue

                    soup = BeautifulSoup(chapter_bytes, "html.parser")
                    # Clean scripts/styles
                    for tag in soup(["script", "style"]):
                        tag.decompose()

                    # Extract headings and paragraphs
                    for elem in soup.find_all(["h1", "h2", "h3", "h4", "p"]):
                        tag_name = elem.name.lower()
                        text = elem.get_text(strip=True)
                        if not text:
                            continue

                        words = text.split()
                        total_words += len(words)

                        if tag_name.startswith("h") and tag_name[1].isdigit():
                            level = int(tag_name[1])
                            blocks.append(
                                DocumentBlock(
                                    block_id=f"blk_{uuid.uuid4().hex[:8]}",
                                    type="heading",
                                    content=text,
                                    level=level,
                                    location=SourceLocation(block_index=block_idx),
                                    metadata={"chapter": chapter_idx, "file": href},
                                )
                            )
                            block_idx += 1
                        elif tag_name == "p":
                            blocks.append(
                                DocumentBlock(
                                    block_id=f"blk_{uuid.uuid4().hex[:8]}",
                                    type="paragraph",
                                    content=text,
                                    location=SourceLocation(block_index=block_idx),
                                    metadata={"chapter": chapter_idx, "file": href, "word_count": len(words)},
                                )
                            )
                            block_idx += 1

                    # Chapter break marker
                    if chapter_idx < len(spine_items):
                        blocks.append(
                            DocumentBlock(
                                block_id=f"blk_{uuid.uuid4().hex[:8]}",
                                type="page_break",
                                content=f"--- Chapter {chapter_idx} End ---",
                                location=SourceLocation(block_index=block_idx),
                                metadata={"chapter": chapter_idx},
                            )
                        )
                        block_idx += 1

        except Exception as e:
            raise ParserError(f"Failed to parse EPUB container: {e}", parser_name="EPUBParser")

        return DocumentModel(
            source_id=source.source_id,
            title=str(title),
            format="epub",
            metadata={"chapter_count": len(spine_items) if 'spine_items' in locals() else 0},
            blocks=blocks,
            total_blocks=len(blocks),
            total_words=total_words,
            warnings=warnings,
        )
