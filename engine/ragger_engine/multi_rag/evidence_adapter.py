"""
Multi-RAG Evidence Adapter for Phase 16.
Wraps the existing, verified _evaluate_evidence_sufficiency logic without modifying its core behavior.
Ensures Phase 14/15 verified evidence gate invariants remain strictly protected.
"""

from typing import List, Tuple
from ragger_engine.multi_rag.models import MultiRAGCandidate
from ragger_engine.retrieval.models import RetrievedChunk, CitationProvenance, ScoreType
from ragger_engine.builder.models import ChunkType


class MultiRAGEvidenceAdapter:
    """
    Adapter that converts MultiRAGCandidate objects into standard RetrievedChunk
    representations expected by the existing GenerationService._evaluate_evidence_sufficiency().
    """

    @staticmethod
    def candidates_to_retrieved_chunks(candidates: List[MultiRAGCandidate]) -> List[RetrievedChunk]:
        """
        Maps multi-RAG candidates to RetrievedChunk instances so the protected single-RAG
        evidence sufficiency gate can evaluate combined cross-RAG evidence.
        """
        retrieved_chunks: List[RetrievedChunk] = []
        for c in candidates:
            # Reconstruct CitationProvenance
            prov = CitationProvenance(
                source_id=c.source_id,
                source_name=c.source_name,
                source_sha256="",
                chunk_id=c.chunk_id,
                chunk_type=ChunkType.STANDARD_PARAGRAPH,
                page_number=c.page_number,
                heading_path=c.heading_path,
                token_count=len(c.text.split()),
            )

            chunk = RetrievedChunk(
                chunk_id=c.chunk_id,
                text=c.text,
                score=c.rrf_score if c.rrf_score > 0.0 else c.raw_score,
                score_type=ScoreType.RRF if c.rrf_score > 0.0 else ScoreType.COSINE_SIMILARITY,
                citation=f"[{c.source_name}, p. {c.page_number}]" if c.page_number else f"[{c.source_name}]",
                provenance=prov,
            )
            retrieved_chunks.append(chunk)
        return retrieved_chunks


    @classmethod
    def evaluate_sufficiency(
        cls,
        generation_service,
        query: str,
        candidates: List[MultiRAGCandidate],
    ) -> Tuple[bool, str]:
        """
        Passes combined candidate evidence through the protected GenerationService evidence gate.
        Returns: (is_sufficient: bool, disclaimer_message: str)
        """
        retrieved_chunks = cls.candidates_to_retrieved_chunks(candidates)
        return generation_service._evaluate_evidence_sufficiency(
            query=query,
            retrieved_chunks=retrieved_chunks,
        )
