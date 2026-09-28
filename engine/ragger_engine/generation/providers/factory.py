"""
Factory for resolving LLM generation providers based on approved GenerationConfig.
"""

from typing import Optional

from ..exceptions import ModelNotAvailableError
from ..models import GenerationConfig
from .base import BaseLLMProvider
from .gguf import LocalGGUFLLMProvider
from .ollama import OllamaLLMProvider
from .testing import TestDeterministicLLMProvider


def get_llm_provider(
    config: GenerationConfig,
    provider_override: Optional[BaseLLMProvider] = None,
) -> BaseLLMProvider:
    """
    Resolves the LLM generation provider adapter.
    """
    if provider_override is not None:
        return provider_override

    provider = config.provider.lower().strip()

    if provider in ("test_deterministic", "test"):
        return TestDeterministicLLMProvider(model_name=config.model_name)
    elif provider == "ollama":
        return OllamaLLMProvider(model_name=config.model_name)
    elif provider in ("local_gguf", "gguf"):
        return LocalGGUFLLMProvider(model_name=config.model_name)
    else:
        raise ModelNotAvailableError(
            f"Unsupported generation provider: '{config.provider}'. "
            "Supported providers: 'local_gguf', 'ollama', 'test_deterministic'."
        )
