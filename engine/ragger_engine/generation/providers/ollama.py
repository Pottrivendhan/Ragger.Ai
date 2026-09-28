"""
Local Ollama LLM provider for Phase 7 Grounded Generation.
Strictly local-only boundary: zero model downloads, zero /api/pull.
"""

import asyncio
import json
from typing import AsyncGenerator
import urllib.error
import urllib.request

import httpx

from ..exceptions import GenerationCancelledError, ModelNotAvailableError
from .base import BaseLLMProvider


class OllamaLLMProvider(BaseLLMProvider):
    """Local Ollama generation provider executing against local daemon at 127.0.0.1:11434."""

    def __init__(self, model_name: str, base_url: str = "http://127.0.0.1:11434"):
        super().__init__(model_name)
        self.base_url = base_url.rstrip("/")

    def validate_availability(self) -> None:
        """
        Validates model presence against GET /api/tags.
        Raises ModelNotAvailableError if Ollama is unreachable or model is absent.
        Strictly zero downloads or pull requests.
        """
        tags_url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(tags_url, headers={"User-Agent": "RaggerEngine/0.1"})
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status != 200:
                    raise ModelNotAvailableError(
                        f"Local Ollama service responded with status {resp.status} on /api/tags."
                    )
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                available_names = [m.get("name", "").lower() for m in models]
                # Match exact name or prefix (e.g., 'llama3' matching 'llama3:latest')
                target = self.model_name.lower().strip()
                matches = any(
                    name == target or name.startswith(f"{target}:") or target.startswith(f"{name}:")
                    for name in available_names
                )
                if not matches:
                    raise ModelNotAvailableError(
                        f"Model '{self.model_name}' not found in local Ollama instance. "
                        "The model must be downloaded via the Model Manager before triggering generation. "
                        "The Generation Engine never downloads models automatically."
                    )
        except urllib.error.URLError as e:
            raise ModelNotAvailableError(
                f"Local Ollama service is not reachable at {self.base_url}: {e.reason}. "
                "Ensure Ollama is running locally."
            )
        except Exception as e:
            if isinstance(e, ModelNotAvailableError):
                raise
            raise ModelNotAvailableError(
                f"Failed to inspect local Ollama models: {str(e)}"
            )

    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        cancel_event: asyncio.Event = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streams generated tokens from local Ollama /api/generate endpoint.
        Aborts upstream HTTP streaming connection immediately if cancel_event fires.
        """
        self.validate_availability()

        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=5.0, pool=5.0)) as client:
            try:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        raise ModelNotAvailableError(
                            f"Ollama generation failed with status {response.status_code}: {err_text.decode('utf-8', errors='ignore')}"
                        )

                    async for line in response.aiter_lines():
                        if cancel_event is not None and cancel_event.is_set():
                            raise GenerationCancelledError("Generation cancelled by user during Ollama stream.")

                        if not line or not line.strip():
                            continue

                        try:
                            chunk_data = json.loads(line)
                            token = chunk_data.get("response", "")
                            if token:
                                yield token
                            if chunk_data.get("done", False):
                                break
                        except json.JSONDecodeError:
                            continue
            except httpx.RequestError as e:
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelledError("Generation cancelled by user during Ollama stream.")
                raise ModelNotAvailableError(f"Ollama generation stream failed: {str(e)}")
