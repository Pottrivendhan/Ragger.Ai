"""
Reciprocal Rank Fusion (RRF) Hybrid retrieval strategy (Hybrid RAG).
Combines dense vector similarity with sparse in-memory BM25 lexical search.
"""

from typing import Dict, List, Optional, Set

from ragger_engine.builder.models import BuildManifest, Chunk
from ragger_engine.builder.storage.base import BaseVectorStore
from ..models import (
    RetrievalFilter,
    RetrievedChunk,
    ScoreType,
)
from ..sparse.bm25 import InvertedBM25Index
from .base import (
    BaseRetrievalStrategy,
    build_provenance,
    format_citation,
    passes_filter,
)


class RrfHybridStrategy(BaseRetrievalStrategy):
    """
    Executes parallel Dense Vector Retrieval and in-memory BM25 lexical search.
    Fuses rankings via Reciprocal Rank Fusion (RRF):
    RRF(d) = sum(1 / (k + rank(r, d))) where k is configured in retrieval_config (default 60).
    """

    def __init__(
        self,
        vector_store: BaseVectorStore,
        bm25_index: InvertedBM25Index,
        chunks_by_id: Dict[str, Chunk],
        manifest: BuildManifest,
    ):
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.chunks_by_id = chunks_by_id
        self.manifest = manifest
        # Extract approved rrf_k or default to 60
        retrieval_cfg = manifest.retrieval_config or {}
        self.rrf_k = retrieval_cfg.get("rrf_k") or 60

    def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
        candidate_pool_size = max(top_k * 4, 30)

        # 1. Dense Vector Search
        dense_candidates = self.vector_store.query_by_vector(
            query_vector, top_k=candidate_pool_size
        )
        dense_ranks: Dict[str, int] = {}
        curr_rank = 1
        for chk, _ in dense_candidates:
            if passes_filter(chk, filters):
                dense_ranks[chk.chunk_id] = curr_rank
                curr_rank += 1

        # 2. Sparse BM25 Search
        bm25_candidates = self.bm25_index.score_query(query)
        sparse_ranks: Dict[str, int] = {}
        curr_rank = 1
        for cid, _ in bm25_candidates:
            chk = self.chunks_by_id.get(cid)
            if chk and passes_filter(chk, filters):
                sparse_ranks[cid] = curr_rank
                curr_rank += 1
                if curr_rank > candidate_pool_size:
                    break

        # 3. Reciprocal Rank Fusion
        all_ids: Set[str] = set(dense_ranks.keys()) | set(sparse_ranks.keys())
        scored: List[tuple[str, float]] = []

        for cid in all_ids:
            score = 0.0
            if cid in dense_ranks:
                score += 1.0 / (self.rrf_k + dense_ranks[cid])
            if cid in sparse_ranks:
                score += 1.0 / (self.rrf_k + sparse_ranks[cid])
            scored.append((cid, round(score, 6)))

        # Sort descending by RRF score
        scored.sort(key=lambda x: x[1], reverse=True)

        results: List[RetrievedChunk] = []
        for cid, score in scored[:top_k]:
            chunk = self.chunks_by_id[cid]
            provenance = build_provenance(chunk, self.manifest)
            citation = format_citation(provenance)

            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    score=score,
                    score_type=ScoreType.RRF,
                    provenance=provenance,
                    parent_chunk_id=chunk.metadata.parent_chunk_id,
                    citation=citation,
                )
            )

        return results
