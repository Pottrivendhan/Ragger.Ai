"""
Section-aware chunking for Research RAG (Architecture 5).
Preserves academic and technical paper structures by segmenting documents based on
semantic section types (Abstract, Methodology, Results, References, etc.).
"""

import re
from typing import List, Union
from ragger_engine.ingestion.models import DatasetModel, DocumentModel
from ragger_engine.recommendation.models import ChunkingConfig
from ..exceptions import ChunkingError
from ..models import Chunk, ChunkMetadata, ChunkType
from .base import BaseChunker, compute_deterministic_chunk_id, estimate_token_count

SECTION_PATTERNS = [
    (r"(?i)\babstract\b", "abstract"),
    (r"(?i)\bintroduction\b", "introduction"),
    (r"(?i)\b(related work|literature review|background)\b", "related_work"),
    (r"(?i)\b(methodology|methods|system design|architecture)\b", "methodology"),
    (r"(?i)\b(experiments|evaluation|experimental setup)\b", "experiments"),
    (r"(?i)\b(results|findings)\b", "results"),
    (r"(?i)\b(discussion|limitations)\b", "discussion"),
    (r"(?i)\b(conclusion|concluding remarks)\b", "conclusion"),
    (r"(?i)\b(references|bibliography)\b", "references"),
]


def classify_section(heading_text: str) -> str:
    """Detects canonical section type from heading text."""
    for pattern, s_type in SECTION_PATTERNS:
        if re.search(pattern, heading_text):
            return s_type
    return "body"


class SectionAwareChunker(BaseChunker):
    """
    Chunks research papers and technical whitepapers respecting structural section bounds.
    Tags each chunk with its canonical section category for targeted sparse/dense retrieval.
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
                f"SectionAwareChunker expects DocumentModel, received {type(model).__name__}"
            )

        chunk_size = config.chunk_size
        chunk_overlap = config.chunk_overlap

        chunks: List[Chunk] = []
        current_section_type = "preamble"
        current_heading_path: List[str] = []
        accumulated_text_parts: List[str] = []
        current_tokens = 0
        last_page_number = 1
        chunk_idx = 0

        def emit_chunk(parts: List[str]) -> None:
            nonlocal chunk_idx
            chunk_text = "\n\n".join(parts)
            final_tokens = estimate_token_count(chunk_text)
            chunk_id = compute_deterministic_chunk_id(source_id, "sec", chunk_idx, chunk_text)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    source_id=source_id,
                    text=chunk_text,
                    chunk_type=ChunkType.SECTION_BLOCK,
                    metadata=ChunkMetadata(
                        source_id=source_id,
                        source_name=source_name,
                        chunk_index=chunk_idx,
                        token_count=final_tokens,
                        page_number=last_page_number,
                        heading_path=list(current_heading_path),
                        model_type="document",
                        extra={"section_type": current_section_type},
                    ),
                    token_count=final_tokens,
                )
            )
            chunk_idx += 1

        for block in model.blocks:
            if block.location and block.location.page_number:
                last_page_number = block.location.page_number

            if block.type == "heading":
                heading_level = block.level or 1
                heading_text = block.content.strip()

                # On section change, emit accumulated chunk
                if accumulated_text_parts:
                    emit_chunk(accumulated_text_parts)
                    accumulated_text_parts = []
                    current_tokens = 0

                current_section_type = classify_section(heading_text)
                if heading_level <= len(current_heading_path):
                    current_heading_path = current_heading_path[: heading_level - 1]
                current_heading_path.append(heading_text)

            content = block.content.strip()
            if not content:
                continue

            block_tokens = estimate_token_count(content)
            if current_tokens + block_tokens > chunk_size and accumulated_text_parts:
                emit_chunk(accumulated_text_parts)
                if chunk_overlap > 0:
                    overlap_parts: List[str] = []
                    overlap_tokens = 0
                    for part in reversed(accumulated_text_parts):
                        pt = estimate_token_count(part)
                        if overlap_tokens + pt <= chunk_overlap:
                            overlap_parts.insert(0, part)
                            overlap_tokens += pt
                        else:
                            break
                    accumulated_text_parts = overlap_parts
                    current_tokens = overlap_tokens
                else:
                    accumulated_text_parts = []
                    current_tokens = 0

            accumulated_text_parts.append(content)
            current_tokens += block_tokens

        if accumulated_text_parts:
            emit_chunk(accumulated_text_parts)

        return chunks
