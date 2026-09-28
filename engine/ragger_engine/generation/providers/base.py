"""
Base LLM Provider abstraction for Grounded Generation.
"""

from abc import ABC, abstractmethod
import asyncio
from typing import AsyncGenerator


class BaseLLMProvider(ABC):
    """Abstract base provider for local LLM inference."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    @abstractmethod
    def validate_availability(self) -> None:
        """
        Validates that the model is present and ready for local inference.
        Must raise ModelNotAvailableError (HTTP 424) if missing.
        Must NEVER initiate downloads, pulls, or external network fetch.
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        cancel_event: asyncio.Event = None,
    ) -> AsyncGenerator[str, None]:
        """
        Asynchronously streams generated tokens from the local LLM.
        Must monitor cancel_event and abort immediately if set.
        """
        pass

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        cancel_event: asyncio.Event = None,
    ) -> str:
        """Accumulates streamed tokens into a complete answer string."""
        tokens = []
        async for token in self.generate_stream(prompt, max_tokens, temperature, cancel_event):
            tokens.append(token)
        return "".join(tokens)
