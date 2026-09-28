"""
Abstract base interface for Phase 8 Evaluation Judges.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple


class BaseEvalJudge(ABC):
    """Abstract interface for LLM-based RAG evaluation judges."""

    @abstractmethod
    def validate_availability(self) -> None:
        """Validates that the judge backend and model are locally available without triggering downloads."""
        pass

    @abstractmethod
    async def evaluate_claims(
        self,
        query: str,
        answer: str,
        context_chunks: List[str],
    ) -> Tuple[int, int, int]:
        """
        Analyzes answer claims against retrieved contexts.
        Returns: (total_claims, supported_claims, unsupported_claims)
        """
        pass

    @abstractmethod
    async def evaluate_disclaimer(
        self,
        query: str,
        answer: str,
        is_out_of_domain: bool,
    ) -> bool:
        """
        Evaluates whether the system appropriately emitted a disclaimer for out-of-domain queries
        or appropriately answered for in-domain queries.
        Returns: True if correct disclaimer behavior, False otherwise.
        """
        pass
