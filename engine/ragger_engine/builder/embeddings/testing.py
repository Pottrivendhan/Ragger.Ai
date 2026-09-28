"""
Test-only deterministic embedding provider.
STRICT INVARIANT: This class is an isolated test double for unit/contract tests only.
It must NEVER be instantiated by the production factory or presented as a production model.
"""

import hashlib
import math
from typing import List
from .base import BaseEmbeddingProvider


class TestDeterministicEmbeddingProvider(BaseEmbeddingProvider):
    """
    Produces deterministic, unit-normalized synthetic float vectors for testing.
    Guarantees consistent vector output for testing index self-consistency and persistence.
    """

    __test__ = False
    is_test_double: bool = True

    def __init__(self, dimension: int = 384, model_name: str = "test-deterministic-synthetic"):
        self._dimension = dimension
        self._model_name = model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed_text(self, text: str) -> List[float]:
        # Generate deterministic pseudo-random float vector from text hash
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand or project digest into target dimensions
        raw_values = []
        for i in range(self._dimension):
            byte_val = digest[(i * 7) % len(digest)]
            float_val = ((byte_val / 255.0) * 2.0) - 1.0  # Range [-1.0, 1.0]
            raw_values.append(float_val)

        # Normalize to unit length (L2 norm)
        norm = math.sqrt(sum(v * v for v in raw_values)) or 1.0
        return [v / norm for v in raw_values]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]
