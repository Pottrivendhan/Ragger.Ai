"""
Production factory for resolving embedding providers from approved EmbeddingConfig.
Enforces that models must be genuinely available locally; raises ModelNotAvailableError if not.
Strictly prohibits silent fallback to synthetic or test doubles.
"""

from pathlib import Path
from typing import Optional
from ragger_engine.recommendation.models import EmbeddingConfig
from ..exceptions import ModelNotAvailableError
from .base import BaseEmbeddingProvider
from .local_onnx import LocalOnnxEmbeddingProvider
from .ollama import OllamaEmbeddingProvider


def get_embedding_provider(
    config: EmbeddingConfig,
    models_dir: Optional[Path] = None,
) -> BaseEmbeddingProvider:
    """
    Resolves the approved production embedding provider.
    Verifies that real model weights or daemons exist before returning.
    Raises ModelNotAvailableError immediately if unavailable.
    """
    provider_name = config.provider.lower().strip()

    if provider_name in ("local_onnx", "onnx"):
        return LocalOnnxEmbeddingProvider(
            model_name=config.model_name,
            dimension=config.dimension,
            models_dir=models_dir,
        )
    elif provider_name == "ollama":
        return OllamaEmbeddingProvider(
            model_name=config.model_name,
            dimension=config.dimension,
        )
    elif provider_name in ("test_deterministic", "testing"):
        import os
        if os.environ.get("RAGGER_ALLOW_TEST_EMBEDDINGS") != "1":
            raise ModelNotAvailableError(
                "Test embedding provider is strictly restricted to automated test runs "
                "via RAGGER_ALLOW_TEST_EMBEDDINGS=1."
            )
        from .testing import TestDeterministicEmbeddingProvider
        return TestDeterministicEmbeddingProvider(dimension=config.dimension)
    else:
        raise ModelNotAvailableError(
            f"Unsupported embedding provider: '{config.provider}'. "
            "Supported production providers: 'local_onnx', 'ollama'."
        )
