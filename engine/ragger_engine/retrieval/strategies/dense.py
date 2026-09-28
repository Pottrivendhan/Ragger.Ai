"""
Dense Vector Top-K retrieval strategy (Document RAG).
"""

from typing import List, Optional

from ragger_engine.builder.models import BuildManifest
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


class DenseVectorStrategy(BaseRetrievalStrategy):
    """Executes dense vector similarity search against active vector store."""

    def __init__(self, vector_store: BaseVectorStore, manifest: BuildManifest):
        self.vector_store = vector_store
        self.manifest = manifest

    def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
        # Retrieve excess candidates to accommodate post-filtering if filters exist
        fetch_k = top_k * 4 if filters else top_k
        candidates = self.vector_store.query_by_vector(query_vector, top_k=fetch_k)

        results: List[RetrievedChunk] = []
        for chunk, sim in candidates:
            if not passes_filter(chunk, filters):
                continue

            provenance = build_provenance(chunk, self.manifest)
            citation = format_citation(provenance)

            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    score=float(sim),
                    score_type=ScoreType.COSINE_SIMILARITY,
                    provenance=provenance,
                    parent_chunk_id=chunk.metadata.parent_chunk_id,
                    citation=citation,
                )
            )

            if len(results) >= top_k:
                break

        return results
