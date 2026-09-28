"""
Test Deterministic Evaluation Judge for Phase 8 automated testing and CI.
Strictly gated by RAGGER_ALLOW_TEST_EVAL=1.
"""

import os
import re
from typing import List, Tuple

from ..exceptions import EvaluationError
from .base import BaseEvalJudge


class TestDeterministicEvalJudge(BaseEvalJudge):
    """Deterministic evaluation judge for test suites and CI environments."""

    __test__ = False

    def __init__(self):
        self._check_gate()

    def _check_gate(self) -> None:
        if os.environ.get("RAGGER_ALLOW_TEST_EVAL") != "1":
            raise EvaluationError(
                "TestDeterministicEvalJudge is disabled. Set RAGGER_ALLOW_TEST_EVAL=1 to enable.",
                code="TEST_EVAL_FORBIDDEN",
            )

    def validate_availability(self) -> None:
        """Enforces environment gate on availability check."""
        self._check_gate()

    async def evaluate_claims(
        self,
        query: str,
        answer: str,
        context_chunks: List[str],
    ) -> Tuple[int, int, int]:
        """
        Deterministically evaluates claims: extracts declarative sentences from answer
        and checks key word overlap against context chunks.
        """
        self._check_gate()
        combined_context = " ".join(context_chunks).lower()

        # Split into non-empty sentences
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", answer)
            if len(s.strip()) > 15
        ]

        # Ignore generic disclaimer phrases from claim counting
        disclaimer_markers = [
            "could not find",
            "insufficient",
            "not found",
            "does not contain",
            "no information",
        ]
        claim_sentences = [
            s for s in sentences
            if not any(dm in s.lower() for dm in disclaimer_markers)
        ]

        if not claim_sentences:
            return 0, 0, 0

        supported = 0
        for s in claim_sentences:
            # Extract content words (4+ chars)
            words = [w.lower() for w in re.findall(r"\b\w{4,}\b", s)]
            if not words:
                continue
            matching = sum(1 for w in words if w in combined_context)
            if matching / len(words) >= 0.3:
                supported += 1

        total = len(claim_sentences)
        unsupported = total - supported
        return total, supported, unsupported

    async def evaluate_disclaimer(
        self,
        query: str,
        answer: str,
        is_out_of_domain: bool,
    ) -> bool:
        """
        Deterministically verifies disclaimer compliance based on keyword markers.
        """
        self._check_gate()
        disclaimer_markers = [
            "could not find information",
            "insufficient information",
            "insufficient evidence",
            "not found in the provided",
            "does not contain information",
            "no information",
            "cannot find",
            "cannot answer",
        ]
        lower_ans = answer.lower()
        has_disclaimer = any(m in lower_ans for m in disclaimer_markers)

        if is_out_of_domain:
            return has_disclaimer
        else:
            return not has_disclaimer
