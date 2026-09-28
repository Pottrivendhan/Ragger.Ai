"""JSON parser deterministically routing between DatasetModel and DocumentModel."""

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Union

from ragger_engine.ingestion.exceptions import ParserError
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


class JSONParser(BaseParser):
    """Parses JSON content, deterministically producing DatasetModel or DocumentModel."""

    def parse(self, file_path: Path, source: SourceRecord) -> Union[DatasetModel, DocumentModel]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
        except Exception as e:
            raise ParserError(f"Invalid JSON content: {e}", parser_name="JSONParser")

        # Deterministic Decision:
        # If data is an array of dicts -> Tabular Dataset
        if isinstance(data, list) and len(data) > 0 and all(isinstance(item, dict) for item in data[:50]):
            return self._parse_as_dataset(data, file_path, source)

        # Otherwise -> Structured Document
        return self._parse_as_document(data, file_path, source)

    def _parse_as_dataset(self, records: List[Dict[str, Any]], file_path: Path, source: SourceRecord) -> DatasetModel:
        # Collect union of all keys from first 100 records
        keys_set = []
        for r in records[:100]:
            for k in r.keys():
                if k not in keys_set:
                    keys_set.append(k)

        columns_data: Dict[str, List[Any]] = {k: [] for k in keys_set}
        for r in records:
            for k in keys_set:
                columns_data[k].append(r.get(k))

        col_schemas: List[ColumnSchema] = []
        for k in keys_set:
            vals = columns_data[k]
            non_nulls = [v for v in vals if v is not None]
            null_count = len(vals) - len(non_nulls)
            distinct_count = len(set(str(v) for v in non_nulls))

            dom_type = "string"
            if non_nulls:
                first = non_nulls[0]
                if isinstance(first, bool):
                    dom_type = "boolean"
                elif isinstance(first, int):
                    dom_type = "integer"
                elif isinstance(first, float):
                    dom_type = "float"
                elif isinstance(first, (dict, list)):
                    dom_type = "json_object"

            num_vals = [v for v in non_nulls if isinstance(v, (int, float)) and not isinstance(v, bool)]
            col_schemas.append(
                ColumnSchema(
                    name=k,
                    inferred_type=dom_type,
                    null_count=null_count,
                    distinct_count=distinct_count,
                    sample_values=non_nulls[:5],
                    min_value=min(num_vals) if num_vals else None,
                    max_value=max(num_vals) if num_vals else None,
                    mean_value=round(sum(num_vals) / len(num_vals), 2) if num_vals else None,
                )
            )

        sheet = TableSheet(
            sheet_name=file_path.stem,
            columns=col_schemas,
            rows=records[:1000],
            total_rows=len(records),
            total_columns=len(keys_set),
        )

        return DatasetModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="json",
            metadata={"record_count": len(records)},
            sheets=[sheet],
            total_sheets=1,
            total_rows_across_sheets=len(records),
        )

    def _parse_as_document(self, data: Any, file_path: Path, source: SourceRecord) -> DocumentModel:
        blocks: List[DocumentBlock] = []
        block_idx = 0
        total_words = 0

        def traverse(node: Any, prefix: str = "", level: int = 1):
            nonlocal block_idx, total_words
            if isinstance(node, dict):
                for k, v in node.items():
                    path_key = f"{prefix}.{k}" if prefix else k
                    if isinstance(v, (dict, list)):
                        blocks.append(
                            DocumentBlock(
                                block_id=f"blk_{uuid.uuid4().hex[:8]}",
                                type="heading",
                                content=str(k),
                                level=min(level, 6),
                                location=SourceLocation(block_index=block_idx),
                                metadata={"key_path": path_key},
                            )
                        )
                        block_idx += 1
                        total_words += len(str(k).split())
                        traverse(v, path_key, level + 1)
                    else:
                        line = f"{k}: {v}"
                        blocks.append(
                            DocumentBlock(
                                block_id=f"blk_{uuid.uuid4().hex[:8]}",
                                type="paragraph",
                                content=line,
                                location=SourceLocation(block_index=block_idx),
                                metadata={"key_path": path_key},
                            )
                        )
                        block_idx += 1
                        total_words += len(line.split())

            elif isinstance(node, list):
                for i, item in enumerate(node):
                    elem_prefix = f"{prefix}[{i}]"
                    traverse(item, elem_prefix, level)

            else:
                line = str(node)
                blocks.append(
                    DocumentBlock(
                        block_id=f"blk_{uuid.uuid4().hex[:8]}",
                        type="paragraph",
                        content=line,
                        location=SourceLocation(block_index=block_idx),
                        metadata={"key_path": prefix},
                    )
                )
                block_idx += 1
                total_words += len(line.split())

        traverse(data)

        return DocumentModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="json",
            metadata={"is_hierarchical_object": True},
            blocks=blocks,
            total_blocks=len(blocks),
            total_words=total_words,
        )
