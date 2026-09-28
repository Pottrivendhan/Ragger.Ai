"""
Local GGUF LLM provider for Phase 7 Grounded Generation and Real Local LLM Inference.
Executes directly against local GGUF weights via llama-cpp-python without external daemons.
Strictly local-only boundary: zero network calls, zero automatic model downloads.
"""

import asyncio
import os
from pathlib import Path
from typing import AsyncGenerator, Optional

from ..exceptions import GenerationCancelledError, ModelNotAvailableError
from .base import BaseLLMProvider


class LocalGGUFLLMProvider(BaseLLMProvider):
    """
    Local GGUF generation provider using llama-cpp-python.
    Supports in-process CPU/GPU token streaming, early cancellation, and strict offline operation.
    """

    def __init__(self, model_name: str):
        super().__init__(model_name)
        self.provider_name = "local_gguf"
        self._llm = None
        self._loaded_model_path: Optional[str] = None
        self._lock = asyncio.Lock()

    def _resolve_model_path(self) -> Path:
        """Resolves the canonical local path for the specified model reference."""
        path = Path(self.model_name)
        if path.is_file():
            return path.resolve()

        # Check canonical storage roots
        from ragger_engine.core.storage import get_storage_root
        storage_root = get_storage_root()

        # Check installed_direct.json inventory first
        installed_file = storage_root / "models" / "installed_direct.json"
        if installed_file.is_file():
            try:
                import json
                with open(installed_file, "r", encoding="utf-8") as f:
                    inventory = json.load(f)
                # Match by key, model_id, or filename
                for k, v in inventory.items():
                    if k == self.model_name or v.get("model_id") == self.model_name:
                        ref = v.get("runtime_model_ref") or v.get("file_path")
                        if ref and Path(ref).is_file():
                            return Path(ref).resolve()
            except Exception:
                pass

        candidates = [
            storage_root / "models" / "generation" / path.name,
            storage_root / "models" / path.name,
            storage_root / path,
            Path("storage") / "models" / "generation" / path.name,
            Path("storage") / "models" / path,
            Path("storage") / path,
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

        return path.resolve()

    def validate_availability(self) -> None:
        """
        Validates that llama_cpp is installed and the target GGUF file exists locally.
        Raises ModelNotAvailableError if missing or unreadable.
        Strictly ZERO network downloads or pulls.
        """
        try:
            import llama_cpp  # noqa: F401
        except ImportError as e:
            raise ModelNotAvailableError(
                f"llama-cpp-python runtime is not installed: {str(e)}. "
                "Ensure llama-cpp-python is installed in the local environment."
            )

        resolved_path = self._resolve_model_path()
        if not resolved_path.exists():
            raise ModelNotAvailableError(
                f"Local GGUF model file not found at '{resolved_path}'. "
                f"Model '{self.model_name}' must be downloaded via the Model Manager before triggering generation. "
                "The Generation Engine never downloads models automatically."
            )

        if not resolved_path.is_file() or resolved_path.stat().st_size == 0:
            raise ModelNotAvailableError(
                f"Local GGUF model file '{resolved_path}' is empty or invalid."
            )

        if not resolved_path.name.lower().endswith(".gguf"):
            raise ModelNotAvailableError(
                f"Local model file '{resolved_path}' is not a valid .gguf format."
            )

    def _get_or_load_llama(self):
        """Loads llama-cpp-python Llama instance with resource safeguards."""
        self.validate_availability()
        resolved_path = str(self._resolve_model_path())

        if self._llm is not None and self._loaded_model_path == resolved_path:
            return self._llm

        import llama_cpp

        # Determine CPU thread allocation (leave at least 1 core free)
        cpu_count = os.cpu_count() or 4
        threads = max(1, min(cpu_count - 1, 8))

        self._llm = llama_cpp.Llama(
            model_path=resolved_path,
            n_ctx=8192,
            n_threads=threads,
            verbose=False,
        )
        self._loaded_model_path = resolved_path
        return self._llm

    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.1,
        cancel_event: asyncio.Event = None,
    ) -> AsyncGenerator[str, None]:
        """
        Streams generated tokens from the local GGUF model.
        Monitors cancel_event and aborts immediately if set.
        """
        self.validate_availability()

        async with self._lock:
            # Check for immediate cancellation before loading/evaluating
            if cancel_event is not None and cancel_event.is_set():
                raise GenerationCancelledError("Generation cancelled by user before GGUF execution.")

            llama = await asyncio.to_thread(self._get_or_load_llama)

            # Format prompt with ChatML tokens for instruct models (Qwen2.5 / ChatML)
            formatted_prompt = (
                f"<|im_start|>system\nYou are Ragger.ai Assistant. You answer user queries concisely in 1-3 sentences using ONLY factual evidence from the provided context, citing each fact with its [chk_...] ID. Stop when finished.<|im_end|>\n"
                f"<|im_start|>user\n{prompt}\n<|im_end|>\n"
                f"<|im_start|>assistant\n"
            )

            # Generate via llama-cpp-python streaming iterator
            def _create_stream():
                return llama.create_completion(
                    prompt=formatted_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    repeat_penalty=1.25,
                    stream=True,
                    stop=[
                        "<|im_end|>",
                        "<|endoftext|>",
                        "<|im_start|>",
                        "User:",
                        "\n\nUser:",
                        "\n\nAssistant:",
                        "\nAssistant:",
                        "</grounding_context>",
                        "</untrusted_chunk>",
                        "<user_query>",
                    ],
                )

            stream_iter = await asyncio.to_thread(_create_stream)

            # Iterate through stream chunks in worker thread to prevent event loop starvation
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise GenerationCancelledError("Generation cancelled by user during GGUF stream.")

                def _next_chunk():
                    try:
                        return next(stream_iter)
                    except StopIteration:
                        return None

                chunk = await asyncio.to_thread(_next_chunk)
                if chunk is None:
                    break

                choices = chunk.get("choices", [])
                if choices:
                    token_text = choices[0].get("text", "")
                    if token_text:
                        yield token_text
