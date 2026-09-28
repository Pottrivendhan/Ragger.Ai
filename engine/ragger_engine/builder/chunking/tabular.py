"""
Tabular schema and row-level chunking for Structured Data RAG (Architecture 3) and Hybrid RAG.
Transforms tabular datasets into a dual representation:
1. TABULAR_SCHEMA: High-level schema definition, column types, and statistical boundaries.
2. TABULAR_ROW: Natural-language row entity records for semantic vector indexing.
"""

from typing import List, Union
from ragger_engine.ingestion.models import DatasetModel, DocumentModel
from ragger_engine.recommendation.models import ChunkingConfig
from ..exceptions import ChunkingError
from ..models import Chunk, ChunkMetadata, ChunkType
from .base import BaseChunker, compute_deterministic_chunk_id, estimate_token_count


class TabularSchemaChunker(BaseChunker):
    """
    Processes DatasetModel sheets into schema summaries and row-group chunks.
    Ensures that structured datasets can be semantically retrieved without losing
    column provenance or row entity fidelity.
    """

    def chunk(
        self,
        model: Union[DocumentModel, DatasetModel],
        source_id: str,
        source_name: str,
        config: ChunkingConfig,
    ) -> List[Chunk]:
        if not isinstance(model, DatasetModel):
            raise ChunkingError(
                f"TabularSchemaChunker expects DatasetModel, received {type(model).__name__}"
            )

        chunk_size = config.chunk_size
        chunks: List[Chunk] = []
        chunk_idx = 0

        for sheet in model.sheets:
            sheet_name = sheet.sheet_name or "main"
            col_names = [col.name for col in sheet.columns]
            col_types = [f"{col.name} ({col.inferred_type})" for col in sheet.columns]

            # 1. Emit TABULAR_SCHEMA chunk
            schema_lines = [
                f"Dataset: {source_name}",
                f"Sheet: {sheet_name}",
                f"Total Rows: {sheet.total_rows}",
                f"Total Columns: {sheet.total_columns or len(sheet.columns)}",
                f"Columns & Types: {', '.join(col_types)}",
            ]

            schema_text = "\n".join(schema_lines)
            schema_tokens = estimate_token_count(schema_text)
            schema_id = compute_deterministic_chunk_id(source_id, "sch", chunk_idx, schema_text)

            chunks.append(
                Chunk(
                    chunk_id=schema_id,
                    source_id=source_id,
                    text=schema_text,
                    chunk_type=ChunkType.TABULAR_SCHEMA,
                    metadata=ChunkMetadata(
                        source_id=source_id,
                        source_name=source_name,
                        chunk_index=chunk_idx,
                        token_count=schema_tokens,
                        sheet_name=sheet_name,
                        model_type="dataset",
                        extra={
                            "row_count": sheet.total_rows,
                            "column_count": len(sheet.columns),
                            "columns": col_names,
                        },
                    ),
                    token_count=schema_tokens,
                )
            )
            chunk_idx += 1

            # 2. Emit TABULAR_ROW chunks in batches
            current_row_lines: List[str] = []
            current_tokens = 0
            start_row = 1

            for row_num, row_dict in enumerate(sheet.rows, start=1):
                if isinstance(row_dict, dict):
                    row_items = [f"{k}: {v}" for k, v in row_dict.items() if v is not None and str(v).strip()]
                elif isinstance(row_dict, list):
                    row_items = [f"{col_names[i]}: {v}" for i, v in enumerate(row_dict) if i < len(col_names) and v is not None]
                else:
                    row_items = [str(row_dict)]

                row_str = f"Row {row_num}: " + "; ".join(row_items)
                row_tokens = estimate_token_count(row_str)

                if current_tokens + row_tokens > chunk_size and current_row_lines:
                    batch_text = f"Dataset: {source_name} | Sheet: {sheet_name} (Rows {start_row}–{row_num - 1})\n" + "\n".join(current_row_lines)
                    b_tokens = estimate_token_count(batch_text)
                    batch_id = compute_deterministic_chunk_id(source_id, "row", chunk_idx, batch_text)
                    chunks.append(
                        Chunk(
                            chunk_id=batch_id,
                            source_id=source_id,
                            text=batch_text,
                            chunk_type=ChunkType.TABULAR_ROW,
                            metadata=ChunkMetadata(
                                source_id=source_id,
                                source_name=source_name,
                                chunk_index=chunk_idx,
                                token_count=b_tokens,
                                sheet_name=sheet_name,
                                model_type="dataset",
                                extra={
                                    "start_row": start_row,
                                    "end_row": row_num - 1,
                                    "sheet_name": sheet_name,
                                },
                            ),
                            token_count=b_tokens,
                        )
                    )
                    chunk_idx += 1
                    current_row_lines = []
                    current_tokens = 0
                    start_row = row_num

                current_row_lines.append(row_str)
                current_tokens += row_tokens

            # Flush final batch
            if current_row_lines:
                end_row = start_row + len(current_row_lines) - 1
                batch_text = f"Dataset: {source_name} | Sheet: {sheet_name} (Rows {start_row}–{end_row})\n" + "\n".join(current_row_lines)
                b_tokens = estimate_token_count(batch_text)
                batch_id = compute_deterministic_chunk_id(source_id, "row", chunk_idx, batch_text)
                chunks.append(
                    Chunk(
                        chunk_id=batch_id,
                        source_id=source_id,
                        text=batch_text,
                        chunk_type=ChunkType.TABULAR_ROW,
                        metadata=ChunkMetadata(
                            source_id=source_id,
                            source_name=source_name,
                            chunk_index=chunk_idx,
                            token_count=b_tokens,
                            sheet_name=sheet_name,
                            model_type="dataset",
                            extra={
                                "start_row": start_row,
                                "end_row": end_row,
                                "sheet_name": sheet_name,
                            },
                        ),
                        token_count=b_tokens,
                    )
                )
                chunk_idx += 1

        return chunks
