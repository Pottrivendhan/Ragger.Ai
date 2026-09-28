"""
Factory for resolving vector store implementations based on approved VectorDbConfig.
"""

from ragger_engine.recommendation.models import VectorDbConfig
from ..exceptions import VectorDbUnavailableError
from .base import BaseVectorStore
from .lancedb_store import LanceDbVectorStore
from .local_flat_store import LocalFlatVectorStore


def get_vector_store(config: VectorDbConfig) -> BaseVectorStore:
    """
    Resolves the vector store adapter corresponding to the approved configuration.
    Safely falls back to LocalFlatVectorStore if LanceDB is not available in the environment.
    """
    provider = config.provider.lower().strip()

    if provider in ("local_flat_index", "flat", "local"):
        return LocalFlatVectorStore(metric=config.metric)
    elif provider == "lancedb":
        try:
            return LanceDbVectorStore(metric=config.metric)
        except VectorDbUnavailableError:
            # Safe zero-dependency fallback for uninterrupted local operation
            import logging
            logging.getLogger("ragger-engine").warning(
                "LanceDB not available in environment; seamlessly falling back to local_flat_index."
            )
            return LocalFlatVectorStore(metric=config.metric)
    else:
        raise VectorDbUnavailableError(
            f"Unsupported vector DB provider: '{config.provider}'. "
            "Supported providers: 'local_flat_index', 'lancedb'."
        )
