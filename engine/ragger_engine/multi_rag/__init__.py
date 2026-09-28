"""
Multi-RAG Module for Phase 16.
Exports models, coordinator, and evidence adapter.
"""

from ragger_engine.multi_rag.models import (
    ResolvedRAGTarget,
    MultiRAGClientTarget,
    MultiRAGRetrievalResult,
    MultiRAGCandidate,
    MultiRAGFusedContext,
)
from ragger_engine.multi_rag.evidence_adapter import MultiRAGEvidenceAdapter
from ragger_engine.multi_rag.coordinator import (
    MultiRAGCoordinator,
    MultiRAGRetrievalError,
)

__all__ = [
    "ResolvedRAGTarget",
    "MultiRAGClientTarget",
    "MultiRAGRetrievalResult",
    "MultiRAGCandidate",
    "MultiRAGFusedContext",
    "MultiRAGEvidenceAdapter",
    "MultiRAGCoordinator",
    "MultiRAGRetrievalError",
]
