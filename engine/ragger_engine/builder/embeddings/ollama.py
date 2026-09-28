"""
Ollama loopback embedding provider.
Connects to a locally running Ollama instance at http://127.0.0.1:11434.
Strictly checks that the model is already downloaded and present in local tags.
Never initiates network downloads or executes `ollama pull`. Missing models fail with ModelNotAvailableError.
"""

from typing import List
import httpx
from ..exceptions import EmbeddingError, ModelNotAvailableError
from .base import BaseEmbeddingProvider


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """
    Connects to local Ollama server on loopback to generate embeddings.
    Strictly verifies that the daemon is running and the approved model tag exists locally.
    Never executes `ollama pull` or downloads models; that boundary belongs strictly to the Model Manager.
    """

    def __init__(
        self,
        model_name: str = "bge-small-en-v1.5",
        dimension: int = 384,
        base_url: str = "http://127.0.0.1:11434",
    ):
        self._model_name = model_name
        self._dimension = dimension
        self._base_url = base_url.rstrip("/")

        self._validate_available()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    def _validate_available(self) -> None:
        """Verifies local Ollama daemon connectivity and local model tag existence."""
        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.get(f"{self._base_url}/api/tags")
                if res.status_code != 200:
                    raise ModelNotAvailableError(
                        f"Ollama server returned HTTP {res.status_code} when checking tags."
                    )
                data = res.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                # Verify approved model is installed locally
                if not any(self._model_name in m for m in models):
                    raise ModelNotAvailableError(
                        f"Model '{self._model_name}' not found in local Ollama instance. "
                        f"Available models: {models}. "
                        "The model must be downloaded via the Model Manager before triggering a build. "
                        "The Builder never downloads models automatically."
                    )
        except httpx.RequestError as e:
            raise ModelNotAvailableError(
                f"Could not connect to local Ollama server at {self._base_url}: {str(e)}. "
                "Ensure Ollama daemon is running on localhost."
            )

    def embed_text(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        try:
            vectors: List[List[float]] = []
            with httpx.Client(timeout=30.0) as client:
                for text in texts:
                    res = client.post(
                        f"{self._base_url}/api/embeddings",
                        json={"model": self._model_name, "prompt": text},
                    )
                    if res.status_code != 200:
                        raise EmbeddingError(
                            f"Ollama embedding request failed with status {res.status_code}: {res.text}"
                        )
                    vec = res.json().get("embedding", [])
                    if len(vec) != self._dimension:
                        raise EmbeddingError(
                            f"Ollama embedding dimension mismatch: expected {self._dimension}, got {len(vec)}"
                        )
                    # L2 normalize
                    norm = sum(x * x for x in vec) ** 0.5
                    if norm > 0:
                        vec = [x / norm for x in vec]
                    vectors.append(vec)
            return vectors
        except Exception as e:
            if isinstance(e, (EmbeddingError, ModelNotAvailableError)):
                raise
            raise EmbeddingError(f"Ollama embedding computation failed: {str(e)}")
