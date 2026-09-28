"""
Base interface for RAG Builder vector embedding providers.
"""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbeddingProvider(ABC):
    """Abstract vector embedding provider interface."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Target embedding dimension."""
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the embedding model."""
        pass

    @property
    def max_tokens(self) -> int:
        """Maximum supported sequence token length."""
        return 512


    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Generates a normalized float vector embedding for a single text input."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generates normalized float vector embeddings for a batch of text inputs."""
        pass
