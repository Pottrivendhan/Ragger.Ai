"""
Base interface and utilities for format- and architecture-specific chunking strategies.
"""

from abc import ABC, abstractmethod
import hashlib
from typing import List, Union
from ragger_engine.ingestion.models import DatasetModel, DocumentModel
from ragger_engine.recommendation.models import ChunkingConfig
from ..models import Chunk, ChunkMetadata


def estimate_token_count(text: str) -> int:
    """
    Fast, deterministic token count estimation.
    Approximates standard BPE tokenization (~4 characters per token in English).
    Guarantees at least 1 token for non-empty text.
    """
    if not text:
        return 0
    words = text.split()
    return max(1, int(len(words) * 1.33))


def compute_deterministic_chunk_id(
    source_id: str,
    strategy_prefix: str,
    chunk_index: int,
    text: str,
) -> str:
    """
    Generates a deterministic, reproducible Chunk ID based on source, strategy, ordinal, and content hash.
    Invariant: Identical content with identical chunking parameters always generates identical IDs.
    """
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:8]
    clean_src = source_id[:8].replace("-", "")
    return f"chk_{clean_src}_{strategy_prefix}_{chunk_index:05d}_{content_hash}"


def split_into_token_safe_subchunks(
    chunk: Chunk,
    max_tokens: int = 512,
    overlap_tokens: int = 50,
) -> List[Chunk]:
    """
    Guarantees that a chunk does not exceed the model's supported token limit.
    If the chunk is already within limit, returns [chunk] unchanged.
    If over limit, splits deterministically on paragraph or sentence boundaries
    into model-safe subchunks, preserving full provenance, metadata, page numbers,
    and heading paths without discarding any text.
    """
    text = chunk.text.strip()
    if not text:
        return [chunk]

    est_tokens = estimate_token_count(text)
    if est_tokens <= max_tokens:
        return [chunk]

    # Split text into natural sentence or paragraph units
    raw_units: List[str] = []
    paragraphs = text.split("\n\n")
    for para in paragraphs:
        para_clean = para.strip()
        if not para_clean:
            continue
        # If single paragraph is very long, split on sentence terminators (.!?)
        if estimate_token_count(para_clean) > max_tokens // 2:
            import re
            sentences = re.split(r"(?<=[.!?])\s+", para_clean)
            for s in sentences:
                s_clean = s.strip()
                if s_clean:
                    raw_units.append(s_clean)
        else:
            raw_units.append(para_clean)

    if not raw_units:
        return [chunk]

    subchunks: List[Chunk] = []
    current_units: List[str] = []
    current_tokens = 0
    sub_idx = 0

    for unit in raw_units:
        unit_tokens = estimate_token_count(unit)

        # Handle edge case where a single sentence/word token exceeds max_tokens
        if unit_tokens > max_tokens:
            words = unit.split()
            word_batch = []
            word_tokens = 0
            for w in words:
                wt = max(1, int(len(w) * 0.35))
                if word_tokens + wt > max_tokens and word_batch:
                    batch_text = " ".join(word_batch)
                    b_tok = estimate_token_count(batch_text)
                    cid = compute_deterministic_chunk_id(
                        chunk.metadata.source_id,
                        f"sub{chunk.metadata.chunk_index}",
                        sub_idx,
                        batch_text,
                    )
                    subchunks.append(
                        Chunk(
                            chunk_id=cid,
                            source_id=chunk.source_id,
                            text=batch_text,
                            chunk_type=chunk.chunk_type,
                            metadata=ChunkMetadata(
                                source_id=chunk.metadata.source_id,
                                source_name=chunk.metadata.source_name,
                                chunk_index=sub_idx,
                                token_count=b_tok,
                                page_number=chunk.metadata.page_number,
                                sheet_name=chunk.metadata.sheet_name,
                                heading_path=list(chunk.metadata.heading_path),
                                parent_chunk_id=chunk.metadata.parent_chunk_id,
                                model_type=chunk.metadata.model_type,
                                extra=dict(chunk.metadata.extra),
                            ),
                            token_count=b_tok,
                        )
                    )
                    sub_idx += 1
                    word_batch = []
                    word_tokens = 0
                word_batch.append(w)
                word_tokens += wt
            if word_batch:
                unit = " ".join(word_batch)
                unit_tokens = estimate_token_count(unit)
            else:
                continue

        if current_tokens + unit_tokens > max_tokens and current_units:
            sub_text = "\n\n".join(current_units)
            final_sub_tokens = estimate_token_count(sub_text)
            cid = compute_deterministic_chunk_id(
                chunk.metadata.source_id,
                f"sub{chunk.metadata.chunk_index}",
                sub_idx,
                sub_text,
            )
            subchunks.append(
                Chunk(
                    chunk_id=cid,
                    source_id=chunk.source_id,
                    text=sub_text,
                    chunk_type=chunk.chunk_type,
                    metadata=ChunkMetadata(
                        source_id=chunk.metadata.source_id,
                        source_name=chunk.metadata.source_name,
                        chunk_index=sub_idx,
                        token_count=final_sub_tokens,
                        page_number=chunk.metadata.page_number,
                        sheet_name=chunk.metadata.sheet_name,
                        heading_path=list(chunk.metadata.heading_path),
                        parent_chunk_id=chunk.metadata.parent_chunk_id,
                        model_type=chunk.metadata.model_type,
                        extra=dict(chunk.metadata.extra),
                    ),
                    token_count=final_sub_tokens,
                )
            )
            sub_idx += 1

            if overlap_tokens > 0:
                overlap_units: List[str] = []
                overlap_count = 0
                for u in reversed(current_units):
                    u_tok = estimate_token_count(u)
                    if overlap_count + u_tok <= overlap_tokens:
                        overlap_units.insert(0, u)
                        overlap_count += u_tok
                    else:
                        break
                current_units = overlap_units
                current_tokens = overlap_count
            else:
                current_units = []
                current_tokens = 0

        current_units.append(unit)
        current_tokens += unit_tokens

    if current_units:
        sub_text = "\n\n".join(current_units)
        final_sub_tokens = estimate_token_count(sub_text)
        cid = compute_deterministic_chunk_id(
            chunk.metadata.source_id,
            f"sub{chunk.metadata.chunk_index}",
            sub_idx,
            sub_text,
        )
        subchunks.append(
            Chunk(
                chunk_id=cid,
                source_id=chunk.source_id,
                text=sub_text,
                chunk_type=chunk.chunk_type,
                metadata=ChunkMetadata(
                    source_id=chunk.metadata.source_id,
                    source_name=chunk.metadata.source_name,
                    chunk_index=sub_idx,
                    token_count=final_sub_tokens,
                    page_number=chunk.metadata.page_number,
                    sheet_name=chunk.metadata.sheet_name,
                    heading_path=list(chunk.metadata.heading_path),
                    parent_chunk_id=chunk.metadata.parent_chunk_id,
                    model_type=chunk.metadata.model_type,
                    extra=dict(chunk.metadata.extra),
                ),
                token_count=final_sub_tokens,
            )
        )

    return subchunks


class BaseChunker(ABC):
    """Abstract strategy for converting normalized models into typed chunks."""

    @abstractmethod
    def chunk(
        self,
        model: Union[DocumentModel, DatasetModel],
        source_id: str,
        source_name: str,
        config: ChunkingConfig,
    ) -> List[Chunk]:
        """Splits a normalized DocumentModel or DatasetModel into discrete searchable Chunk objects."""
        pass
