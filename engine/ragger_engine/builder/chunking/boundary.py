"""
Boundary-aware paragraph chunking with sliding token window and overlap.
Implements the boundary_paragraph strategy for Document RAG (Architecture 1).
"""

from typing import List, Union
from ragger_engine.ingestion.models import DatasetModel, DocumentModel
from ragger_engine.recommendation.models import ChunkingConfig
from ..exceptions import ChunkingError
from ..models import Chunk, ChunkMetadata, ChunkType
from .base import BaseChunker, compute_deterministic_chunk_id, estimate_token_count


class BoundaryParagraphChunker(BaseChunker):
    """
    Splits DocumentModel blocks into cohesive paragraph chunks respecting sentence
    and heading boundaries, maintaining token size bounds and sliding overlap.
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
                f"BoundaryParagraphChunker expects DocumentModel, received {type(model).__name__}"
            )

        chunk_size = config.chunk_size
        chunk_overlap = config.chunk_overlap

        chunks: List[Chunk] = []
        current_heading_path: List[str] = []
        accumulated_text_parts: List[str] = []
        current_tokens = 0
        last_page_number = 1
        chunk_idx = 0

        for block in model.blocks:
            if block.location and block.location.page_number:
                last_page_number = block.location.page_number

            # Heading blocks update current hierarchy context
            if block.type == "heading":
                heading_level = block.level or 1
                heading_text = block.content.strip()
                if heading_level <= len(current_heading_path):
                    current_heading_path = current_heading_path[: heading_level - 1]
                current_heading_path.append(heading_text)

            content = block.content.strip()
            if not content:
                continue

            block_tokens = estimate_token_count(content)

            # If adding this block exceeds chunk_size and we already have text, emit current chunk
            if current_tokens + block_tokens > chunk_size and accumulated_text_parts:
                chunk_text = "\n\n".join(accumulated_text_parts)
                final_tokens = estimate_token_count(chunk_text)
                chunk_id = compute_deterministic_chunk_id(source_id, "bnd", chunk_idx, chunk_text)

                chunks.append(
                    Chunk(
                        chunk_id=chunk_id,
                        source_id=source_id,
                        text=chunk_text,
                        chunk_type=ChunkType.STANDARD_PARAGRAPH,
                        metadata=ChunkMetadata(
                            source_id=source_id,
                            source_name=source_name,
                            chunk_index=chunk_idx,
                            token_count=final_tokens,
                            page_number=last_page_number,
                            heading_path=list(current_heading_path),
                            model_type="document",
                        ),
                        token_count=final_tokens,
                    )
                )
                chunk_idx += 1

                # Calculate overlap: retain tail portion of text if chunk_overlap > 0
                if chunk_overlap > 0:
                    overlap_parts: List[str] = []
                    overlap_tokens = 0
                    for part in reversed(accumulated_text_parts):
                        pt_tokens = estimate_token_count(part)
                        if overlap_tokens + pt_tokens <= chunk_overlap:
                            overlap_parts.insert(0, part)
                            overlap_tokens += pt_tokens
                        else:
                            break
                    accumulated_text_parts = overlap_parts
                    current_tokens = overlap_tokens
                else:
                    accumulated_text_parts = []
                    current_tokens = 0

            accumulated_text_parts.append(content)
            current_tokens += block_tokens

        # Flush remaining accumulated text
        if accumulated_text_parts:
            chunk_text = "\n\n".join(accumulated_text_parts)
            final_tokens = estimate_token_count(chunk_text)
            chunk_id = compute_deterministic_chunk_id(source_id, "bnd", chunk_idx, chunk_text)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_id=source_id,
                    text=chunk_text,
                    chunk_type=ChunkType.STANDARD_PARAGRAPH,
                    metadata=ChunkMetadata(
                        source_id=source_id,
                        source_name=source_name,
                        chunk_index=chunk_idx,
                        token_count=final_tokens,
                        page_number=last_page_number,
                        heading_path=list(current_heading_path),
                        model_type="document",
                    ),
                    token_count=final_tokens,
                )
            )

        # Fallback for empty blocks when title is present
        if not chunks and model.title:
            title_tokens = estimate_token_count(model.title)
            chunk_id = compute_deterministic_chunk_id(source_id, "bnd", 0, model.title)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_id=source_id,
                    text=model.title,
                    chunk_type=ChunkType.STANDARD_PARAGRAPH,
                    metadata=ChunkMetadata(
                        source_id=source_id,
                        source_name=source_name,
                        chunk_index=0,
                        token_count=title_tokens,
                        page_number=1,
                        heading_path=[model.title],
                        model_type="document",
                    ),
                    token_count=title_tokens,
                )
            )

        return chunks
