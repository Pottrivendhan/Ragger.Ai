"""
Parent-Child Hierarchical expansion retrieval strategy (Knowledge RAG).
"""

from typing import Any, Dict, List, Optional

from ragger_engine.builder.models import BuildManifest, Chunk
from ragger_engine.builder.storage.base import BaseVectorStore
from ..models import (
    RetrievalFilter,
    RetrievedChunk,
    ScoreType,
)
from .base import (
    BaseRetrievalStrategy,
    build_provenance,
    format_citation,
    passes_filter,
)


class ParentExpansionStrategy(BaseRetrievalStrategy):
    """
    Executes granular child vector matching and expands to encompassing parent blocks.
    Deduplicates shared parent chunks while accumulating matched child snippets.
    """

    def __init__(
        self,
        vector_store: BaseVectorStore,
        chunks_by_id: Dict[str, Chunk],
        manifest: BuildManifest,
    ):
        self.vector_store = vector_store
        self.chunks_by_id = chunks_by_id
        self.manifest = manifest

    def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
        fetch_k = top_k * 6  # retrieve broader child candidate pool to allow parent grouping
        candidates = self.vector_store.query_by_vector(query_vector, top_k=fetch_k)

        # Group by resolved parent (or child id if standalone)
        # key: parent_id -> {"chunk": Chunk, "score": float, "child_snippets": List[str]}
        grouped: Dict[str, Dict[str, Any]] = {}

        for child_chunk, sim in candidates:
            if not passes_filter(child_chunk, filters):
                continue

            parent_id = child_chunk.metadata.parent_chunk_id
            resolved_chunk = self.chunks_by_id.get(parent_id) if parent_id else None

            target_id = resolved_chunk.chunk_id if resolved_chunk else child_chunk.chunk_id
            target_chunk = resolved_chunk if resolved_chunk else child_chunk

            if target_id not in grouped:
                grouped[target_id] = {
                    "chunk": target_chunk,
                    "score": float(sim),
                    "parent_id": parent_id,
                    "parent_text": resolved_chunk.text if resolved_chunk else None,
                    "child_snippets": [child_chunk.text],
                }
            else:
                # Update max score and append snippet
                if sim > grouped[target_id]["score"]:
                    grouped[target_id]["score"] = float(sim)
                if child_chunk.text not in grouped[target_id]["child_snippets"]:
                    grouped[target_id]["child_snippets"].append(child_chunk.text)

        # Sort grouped candidates by highest child similarity score descending
        sorted_groups = sorted(grouped.values(), key=lambda x: x["score"], reverse=True)

        results: List[RetrievedChunk] = []
        for g in sorted_groups[:top_k]:
            chk = g["chunk"]
            provenance = build_provenance(chk, self.manifest)
            citation = format_citation(provenance)

            results.append(
                RetrievedChunk(
                    chunk_id=chk.chunk_id,
                    text=chk.text,
                    score=g["score"],
                    score_type=ScoreType.COSINE_SIMILARITY,
                    provenance=provenance,
                    parent_chunk_id=g["parent_id"],
                    parent_text=g["parent_text"],
                    matched_child_snippets=g["child_snippets"],
                    citation=citation,
                )
            )

        return results
