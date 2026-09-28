"""
Parent-child hierarchical chunking for Knowledge RAG (Architecture 2).
Generates granular child chunks optimized for vector search, linked to encompassing
parent chunks that provide complete contextual windows to the LLM during retrieval.
"""

from typing import List, Union
from ragger_engine.ingestion.models import DatasetModel, DocumentModel
from ragger_engine.recommendation.models import ChunkingConfig
from ..exceptions import ChunkingError
from ..models import Chunk, ChunkMetadata, ChunkType
from .base import BaseChunker, compute_deterministic_chunk_id, estimate_token_count


class ParentChildHierarchicalChunker(BaseChunker):
    """
    Splits DocumentModel into hierarchical parent-child relationships.
    Parent chunks encompass complete section boundaries (or parent_chunk_size tokens).
    Child chunks partition parent chunks into granular windows (child_chunk_size tokens)
    carrying parent_chunk_id references for context expansion.
    """

    def chunk(
        self,
        model: Union[DocumentModel, DatasetModel],
        source_id: str,
        source_name: str,
        config: ChunkingConfig,
    ) -> List[Chunk]:
        if not isinstance(model, DocumentModel):
            raise ChunkingError(
                f"ParentChildHierarchicalChunker expects DocumentModel, received {type(model).__name__}"
            )

        child_size = config.child_chunk_size or 192
        parent_size = config.parent_chunk_size or 768

        all_chunks: List[Chunk] = []
        current_heading_path: List[str] = []
        current_parent_parts: List[str] = []
        current_parent_tokens = 0
        last_page_number = 1
        parent_idx = 0
        child_idx = 0

        def flush_parent(parts: List[str], heading: List[str], page: int) -> None:
            nonlocal parent_idx, child_idx
            if not parts:
                return

            parent_text = "\n\n".join(parts)
            p_tokens = estimate_token_count(parent_text)
            parent_id = compute_deterministic_chunk_id(source_id, "par", parent_idx, parent_text)
            parent_chunk = Chunk(
                chunk_id=parent_id,
                source_id=source_id,
                text=parent_text,
                chunk_type=ChunkType.PARENT_CHUNK,
                metadata=ChunkMetadata(
                    source_id=source_id,
                    source_name=source_name,
                    chunk_index=parent_idx,
                    token_count=p_tokens,
                    page_number=page,
                    heading_path=list(heading),
                    parent_chunk_id=None,
                    model_type="document",
                ),
                token_count=p_tokens,
            )
            all_chunks.append(parent_chunk)
            parent_idx += 1

            # Generate child chunks inside this parent
            # Split parent text into sentences or sub-paragraphs
            child_parts: List[str] = []
            child_tokens = 0

            for part in parts:
                p_tok = estimate_token_count(part)
                if child_tokens + p_tok > child_size and child_parts:
                    child_text = "\n\n".join(child_parts)
                    c_tokens = estimate_token_count(child_text)
                    cid = compute_deterministic_chunk_id(source_id, "chi", child_idx, child_text)
                    all_chunks.append(
                        Chunk(
                            chunk_id=cid,
                            source_id=source_id,
                            text=child_text,
                            chunk_type=ChunkType.CHILD_CHUNK,
                            metadata=ChunkMetadata(
                                source_id=source_id,
                                source_name=source_name,
                                chunk_index=child_idx,
                                token_count=c_tokens,
                                page_number=page,
                                heading_path=list(heading),
                                parent_chunk_id=parent_id,
                                model_type="document",
                            ),
                            token_count=c_tokens,
                        )
                    )
                    child_idx += 1
                    child_parts = []
                    child_tokens = 0

                child_parts.append(part)
                child_tokens += p_tok

            if child_parts:
                child_text = "\n\n".join(child_parts)
                c_tokens = estimate_token_count(child_text)
                cid = compute_deterministic_chunk_id(source_id, "chi", child_idx, child_text)
                all_chunks.append(
                    Chunk(
                        chunk_id=cid,
                        source_id=source_id,
                        text=child_text,
                        chunk_type=ChunkType.CHILD_CHUNK,
                        metadata=ChunkMetadata(
                            source_id=source_id,
                            source_name=source_name,
                            chunk_index=child_idx,
                            token_count=c_tokens,
                            page_number=page,
                            heading_path=list(heading),
                            parent_chunk_id=parent_id,
                            model_type="document",
                        ),
                        token_count=c_tokens,
                    )
                )
                child_idx += 1

        for block in model.blocks:
            if block.location and block.location.page_number:
                last_page_number = block.location.page_number

            if block.type == "heading":
                # Flush previous parent on major heading change
                if current_parent_parts:
                    flush_parent(current_parent_parts, current_heading_path, last_page_number)
                    current_parent_parts = []
                    current_parent_tokens = 0

                heading_level = block.level or 1
                heading_text = block.content.strip()
                if heading_level <= len(current_heading_path):
                    current_heading_path = current_heading_path[: heading_level - 1]
                current_heading_path.append(heading_text)

            content = block.content.strip()
            if not content:
                continue

            block_tokens = estimate_token_count(content)
            if current_parent_tokens + block_tokens > parent_size and current_parent_parts:
                flush_parent(current_parent_parts, current_heading_path, last_page_number)
                current_parent_parts = []
                current_parent_tokens = 0

            current_parent_parts.append(content)
            current_parent_tokens += block_tokens

        # Flush final parent
        if current_parent_parts:
            flush_parent(current_parent_parts, current_heading_path, last_page_number)

        # Fallback if empty
        if not all_chunks and model.title:
            t_tokens = estimate_token_count(model.title)
            pid = compute_deterministic_chunk_id(source_id, "par", 0, model.title)
            cid = compute_deterministic_chunk_id(source_id, "chi", 0, model.title)
            all_chunks.append(
                Chunk(
                    chunk_id=pid,
                    source_id=source_id,
                    text=model.title,
                    chunk_type=ChunkType.PARENT_CHUNK,
                    metadata=ChunkMetadata(
                        source_id=source_id,
                        source_name=source_name,
                        chunk_index=0,
                        token_count=t_tokens,
                        page_number=1,
                        heading_path=[model.title],
                        parent_chunk_id=None,
                        model_type="document",
                    ),
                    token_count=t_tokens,
                )
            )
            all_chunks.append(
                Chunk(
                    chunk_id=cid,
                    source_id=source_id,
                    text=model.title,
                    chunk_type=ChunkType.CHILD_CHUNK,
                    metadata=ChunkMetadata(
                        source_id=source_id,
                        source_name=source_name,
                        chunk_index=0,
                        token_count=t_tokens,
                        page_number=1,
                        heading_path=[model.title],
                        parent_chunk_id=pid,
                        model_type="document",
                    ),
                    token_count=t_tokens,
                )
            )

        return all_chunks
