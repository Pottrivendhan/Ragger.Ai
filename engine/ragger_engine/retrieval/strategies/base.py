"""
Base interface and shared utilities for retrieval strategies.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ragger_engine.builder.models import BuildManifest, Chunk
from ..models import (
    CitationProvenance,
    RetrievalFilter,
    RetrievedChunk,
    ScoreType,
)


def format_citation(provenance: CitationProvenance) -> str:
    """Deterministically formats human-readable bracketed citation string from provenance metadata."""
    parts = [f"Source: {provenance.source_name}"]
    if provenance.page_number is not None:
        parts.append(f"Page: {provenance.page_number}")
    if provenance.heading_path:
        parts.append(f"Section: {provenance.heading_path[-1]}")
    return f"[{', '.join(parts)}]"


def build_provenance(chunk: Chunk, manifest: BuildManifest) -> CitationProvenance:
    """Extracts authoritative raw provenance fields from chunk and manifest."""
    source_sha = manifest.source_hashes.get(chunk.source_id, "")
    return CitationProvenance(
        source_id=chunk.source_id,
        source_name=chunk.metadata.source_name,
        source_sha256=source_sha,
        chunk_id=chunk.chunk_id,
        chunk_type=chunk.chunk_type,
        page_number=chunk.metadata.page_number,
        paragraph_index=getattr(chunk.metadata, "chunk_index", 0),
        heading_path=list(chunk.metadata.heading_path),
        token_count=chunk.token_count,
    )


def passes_filter(chunk: Chunk, filters: Optional[RetrievalFilter]) -> bool:
    """Evaluates whether a chunk satisfies all configured filter constraints."""
    if not filters:
        return True

    if filters.source_ids and chunk.source_id not in filters.source_ids:
        return False

    if filters.source_name and chunk.metadata.source_name != filters.source_name:
        return False

    if filters.page_numbers and chunk.metadata.page_number not in filters.page_numbers:
        return False

    if filters.chunk_types and chunk.chunk_type not in filters.chunk_types:
        return False

    if filters.heading_contains:
        term = filters.heading_contains.lower()
        if not any(term in h.lower() for h in chunk.metadata.heading_path):
            return False

    return True


class BaseRetrievalStrategy(ABC):
    """Abstract contract for architecture-specific retrieval mechanics."""

    @abstractmethod
    def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
        """Executes retrieval against loaded active build index."""
        pass
