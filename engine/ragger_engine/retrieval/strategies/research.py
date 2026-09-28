"""
Research RAG retrieval strategy with deterministic lexical_dense reranking and section boosting.
"""

from typing import Dict, List, Optional

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

# Deterministic section priority boosts strictly conforming to approved Phase 6 contract:
# Abstract: 1.25, Results: 1.20, Methodology: 1.15, Intro: 1.05, Other: 1.00
SECTION_BOOSTS = {
    "abstract": 1.25,
    "results": 1.20,
    "result": 1.20,
    "conclusion": 1.20,
    "finding": 1.20,
    "methodology": 1.15,
    "method": 1.15,
    "experiment": 1.15,
    "intro": 1.05,
    "introduction": 1.05,
    "related": 1.05,
}


def get_section_boost(chunk: Chunk) -> float:
    """Deterministically extracts section priority weight from heading path and metadata."""
    headings_lower = " ".join(chunk.metadata.heading_path).lower()
    section_type = str(chunk.metadata.extra.get("section_type", "")).lower()
    text_check = f"{headings_lower} {section_type}"

    for key, boost in SECTION_BOOSTS.items():
        if key in text_check:
            return boost
    return 1.00


class SectionAwareRerankStrategy(BaseRetrievalStrategy):
    """
    Research RAG Strategy:
    1. Hybrid candidate retrieval (Top 20 candidates).
    2. Deterministic lexical_dense reranking:
       Score = B_sec * (0.6 * S_dense + 0.4 * S_bm25)
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

    def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
        candidate_pool_size = max(top_k * 4, 20)

        # 1. Fetch dense candidates
        dense_candidates = self.vector_store.query_by_vector(
            query_vector, top_k=candidate_pool_size
        )
        dense_map: Dict[str, float] = {}
        for chk, sim in dense_candidates:
            if passes_filter(chk, filters):
                dense_map[chk.chunk_id] = float(sim)

        # 2. Fetch BM25 candidates
        bm25_candidates = self.bm25_index.score_query(query)
        bm25_map: Dict[str, float] = {}
        for cid, b_score in bm25_candidates:
            chk = self.chunks_by_id.get(cid)
            if chk and passes_filter(chk, filters):
                bm25_map[cid] = float(b_score)

        # Candidate union
        candidate_ids = set(dense_map.keys()) | set(bm25_map.keys())
        if not candidate_ids:
            return []

        # Min-max normalize BM25 across candidates
        all_bm25 = [bm25_map.get(cid, 0.0) for cid in candidate_ids]
        min_b = min(all_bm25) if all_bm25 else 0.0
        max_b = max(all_bm25) if all_bm25 else 1.0
        b_range = max_b - min_b if max_b > min_b else 1.0

        scored: List[tuple[str, float]] = []
        for cid in candidate_ids:
            chunk = self.chunks_by_id.get(cid)
            if not chunk:
                continue

            # Normalized dense: mapping [-1, 1] to [0, 1]
            raw_dense = dense_map.get(cid, 0.0)
            s_dense = max(0.0, min(1.0, (raw_dense + 1.0) / 2.0))

            # Normalized BM25: mapping to [0, 1]
            raw_bm25 = bm25_map.get(cid, 0.0)
            s_bm25 = (raw_bm25 - min_b) / b_range if max_b > min_b else 0.5

            # Section boost
            boost = get_section_boost(chunk)

            # Combined formula
            final_score = boost * (0.6 * s_dense + 0.4 * s_bm25)
            scored.append((cid, round(final_score, 4)))

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
                    score_type=ScoreType.LEXICAL_DENSE,
                    provenance=provenance,
                    parent_chunk_id=chunk.metadata.parent_chunk_id,
                    citation=citation,
                )
            )

        return results
