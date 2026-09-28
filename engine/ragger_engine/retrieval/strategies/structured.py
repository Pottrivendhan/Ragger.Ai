"""
Dual-query routing strategy for Structured Data RAG.
Deterministically classifies query as quantitative vs. semantic; routes accordingly.
"""

import re
from typing import List, Optional

from ragger_engine.builder.models import BuildManifest, Chunk, ChunkType
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

# Deterministic regex patterns for quantitative intent detection
QUANTITATIVE_KEYWORD_PATTERN = re.compile(
    r"\b(sum|total|average|avg|count|min|max|minimum|maximum|mean|highest|lowest|"
    r"revenue|profit|loss|sales|price|cost|amount|quantity|budget|volume)\b",
    re.IGNORECASE,
)
COMPARISON_PATTERN = re.compile(
    r"(\b(greater than|less than|more than|at least|at most|above|below|between|exceeding)\b|[><=])",
    re.IGNORECASE,
)
NUMERIC_OR_DATE_PATTERN = re.compile(
    r"([\$\€\£\₹]|\b\d+(\.\d+)?\b|\b(19|20)\d{2}\b|\bQ[1-4]\b)",
    re.IGNORECASE,
)


def is_quantitative_query(query: str) -> bool:
    """
    Deterministically determines if query has quantitative intent.
    Matches aggregation keywords, comparison operators, currency, or numeric bounds.
    Ambiguous queries deterministically evaluate to False (defaulting to semantic vector search).
    """
    has_keyword = bool(QUANTITATIVE_KEYWORD_PATTERN.search(query))
    has_comparison = bool(COMPARISON_PATTERN.search(query))
    has_numeric = bool(NUMERIC_OR_DATE_PATTERN.search(query))

    # Must contain an aggregator/keyword OR (comparison AND number)
    return has_keyword or (has_comparison and has_numeric)


class DualQueryRoutingStrategy(BaseRetrievalStrategy):
    """
    Dual Query Routing Strategy:
    1. Quantitative queries -> deterministic structured schema and row filter execution.
    2. Semantic / Ambiguous queries -> semantic vector search over row/schema summary embeddings.
    """

    def __init__(
        self,
        vector_store: BaseVectorStore,
        chunks: List[Chunk],
        manifest: BuildManifest,
    ):
        self.vector_store = vector_store
        self.chunks = chunks
        self.manifest = manifest

    def retrieve(
        self,
        query: str,
        query_vector: List[float],
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
        if is_quantitative_query(query):
            return self._retrieve_quantitative(query, top_k, filters)
        else:
            return self._retrieve_semantic(query_vector, top_k, filters)

    def _retrieve_semantic(
        self,
        query_vector: List[float],
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
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
                    citation=citation,
                )
            )

            if len(results) >= top_k:
                break

        return results

    def _retrieve_quantitative(
        self,
        query: str,
        top_k: int,
        filters: Optional[RetrievalFilter],
    ) -> List[RetrievedChunk]:
        """
        Executes structured match over schema and tabular row chunks.
        Computes deterministic match score: matching query tokens / total query tokens.
        """
        tokens = set(re.findall(r"\b\w+\b", query.lower()))
        if not tokens:
            return []

        scored_candidates: List[tuple[Chunk, float]] = []

        # Prioritize tabular schemas and rows
        for chunk in self.chunks:
            if not passes_filter(chunk, filters):
                continue

            chunk_text_lower = chunk.text.lower()
            matched_count = sum(1 for t in tokens if t in chunk_text_lower)
            if matched_count == 0:
                continue

            # Deterministic structured match ratio in [0.0, 1.0]
            score = round(matched_count / len(tokens), 4)

            # Extra weight if schema chunk
            if chunk.chunk_type == ChunkType.TABULAR_SCHEMA:
                score = min(1.0, score + 0.1)

            scored_candidates.append((chunk, score))

        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        results: List[RetrievedChunk] = []
        for chunk, score in scored_candidates[:top_k]:
            provenance = build_provenance(chunk, self.manifest)
            citation = format_citation(provenance)

            results.append(
                RetrievedChunk(
                    chunk_id=chunk.chunk_id,
                    text=chunk.text,
                    score=score,
                    score_type=ScoreType.STRUCTURED_MATCH,
                    provenance=provenance,
                    citation=citation,
                )
            )

        return results
