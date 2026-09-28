"""Safe XML parser using defusedxml to block XXE attacks."""

import uuid
from pathlib import Path
from typing import List, Union
import defusedxml.ElementTree as ET
from defusedxml.common import DefusedXmlException

from ragger_engine.ingestion.exceptions import ParserError, SecurityLimitExceededError
from ragger_engine.ingestion.models import (
    ColumnSchema,
    DatasetModel,
    DocumentBlock,
    DocumentModel,
    SourceLocation,
    SourceRecord,
    TableSheet,
)
from ragger_engine.ingestion.parsers.base import BaseParser


class XMLParser(BaseParser):
    """Safely parses XML documents with defusedxml, defending against XXE and entity bombs."""

    def parse(self, file_path: Path, source: SourceRecord) -> Union[DocumentModel, DatasetModel]:
        try:
            tree = ET.parse(str(file_path))
            root = tree.getroot()
        except DefusedXmlException as e:
            raise SecurityLimitExceededError(f"XML Security Exception (possible XXE attack): {e}", code="XML_SECURITY_ERROR")
        except Exception as e:
            raise ParserError(f"Failed to parse XML: {e}", parser_name="XMLParser")

        # Check if XML is tabular (repeating children under root with uniform sub-elements)
        children = list(root)
        if len(children) >= 2 and all(len(c) > 0 and len(c) == len(children[0]) for c in children[:10]):
            return self._parse_as_dataset(root, children, file_path, source)

        return self._parse_as_document(root, file_path, source)

    def _parse_as_dataset(self, root, records, file_path: Path, source: SourceRecord) -> DatasetModel:
        headers = []
        for child in records[0]:
            tag_name = child.tag.split("}")[-1]
            if tag_name not in headers:
                headers.append(tag_name)

        rows = []
        for rec in records:
            row_dict = {}
            for elem in rec:
                tag_name = elem.tag.split("}")[-1]
                row_dict[tag_name] = elem.text.strip() if elem.text else None
            rows.append(row_dict)

        col_schemas = [
            ColumnSchema(
                name=h,
                inferred_type="string",
                null_count=sum(1 for r in rows if r.get(h) is None),
                distinct_count=len(set(r.get(h) for r in rows if r.get(h) is not None)),
                sample_values=[r.get(h) for r in rows if r.get(h) is not None][:5],
            )
            for h in headers
        ]

        sheet = TableSheet(
            sheet_name=root.tag.split("}")[-1],
            columns=col_schemas,
            rows=rows[:1000],
            total_rows=len(rows),
            total_columns=len(headers),
        )

        return DatasetModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="xml",
            metadata={"root_tag": root.tag},
            sheets=[sheet],
            total_sheets=1,
            total_rows_across_sheets=len(rows),
        )

    def _parse_as_document(self, root, file_path: Path, source: SourceRecord) -> DocumentModel:
        blocks: List[DocumentBlock] = []
        block_idx = 0
        total_words = 0

        def traverse(elem, level: int = 1):
            nonlocal block_idx, total_words
            tag = elem.tag.split("}")[-1]

            has_children = len(elem) > 0
            text = (elem.text or "").strip()

            if has_children:
                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type="heading",
                        content=tag,
                        level=min(level, 6),
                        location=SourceLocation(block_index=block_idx),
                        metadata={"tag": tag},
                    )
                )
                block_idx += 1
                total_words += len(tag.split())

                for child in elem:
                    traverse(child, level + 1)

            elif text:
                content = f"{tag}: {text}"
                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type="paragraph",
                        content=content,
                        location=SourceLocation(block_index=block_idx),
                        metadata={"tag": tag},
                    )
                )
                block_idx += 1
                total_words += len(content.split())

        traverse(root)

        return DocumentModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="xml",
            metadata={"root_tag": root.tag},
            blocks=blocks,
            total_blocks=len(blocks),
            total_words=total_words,
        )
