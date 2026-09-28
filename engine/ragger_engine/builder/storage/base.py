"""
Base interface for vector database storage adapters.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Tuple
from ..models import Chunk


class BaseVectorStore(ABC):
    """Abstract vector store interface for indexing and querying chunks."""

    @abstractmethod
    def add_chunks(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        """Adds a batch of chunks and their corresponding dense vectors."""
        pass

    @abstractmethod
    def persist(self, directory: Path) -> Path:
        """Persists the in-memory index and chunks to disk in the specified directory."""
        pass

    @abstractmethod
    def reload(self, directory: Path) -> None:
        """Reloads the index and chunks from disk into memory."""
        pass

    @abstractmethod
    def query_by_vector(self, query_vector: List[float], top_k: int = 5) -> List[Tuple[Chunk, float]]:
        """Queries the vector index for the top-k most similar chunks by cosine similarity."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Returns statistics of the index (total chunks, total vectors, dimension)."""
        pass
