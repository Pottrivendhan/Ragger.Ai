"""
Embeddings subsystem exports.
"""

from .base import BaseEmbeddingProvider
from .factory import get_embedding_provider
from .local_onnx import LocalOnnxEmbeddingProvider
from .ollama import OllamaEmbeddingProvider
from .testing import TestDeterministicEmbeddingProvider

__all__ = [
    "BaseEmbeddingProvider",
    "LocalOnnxEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "TestDeterministicEmbeddingProvider",
    "get_embedding_provider",
]
