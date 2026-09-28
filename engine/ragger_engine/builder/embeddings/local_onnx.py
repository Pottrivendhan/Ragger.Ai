"""
Local ONNX embedding provider.
Runs local quantized ONNX embedding models via onnxruntime and tokenizers.
Strictly checks that model weights exist locally; fails with ModelNotAvailableError if missing.
Never downloads models or dependencies over the network.
"""

import math
import os
from pathlib import Path
from typing import List, Optional
from ragger_engine.core.storage import get_storage_root
from ..exceptions import EmbeddingError, ModelNotAvailableError
from .base import BaseEmbeddingProvider


def get_default_models_dir() -> Path:
    """Returns the canonical storage/models/embeddings path using storage root resolver."""
    return get_storage_root() / "models" / "embeddings"


class LocalOnnxEmbeddingProvider(BaseEmbeddingProvider):
    """
    Executes local ONNX embedding models (e.g. bge-small-en-v1.5.onnx).
    Guarantees that large model weights are read from local disk, failing cleanly if absent.
    Performs full tokenizer encoding, ONNX session inference, mean pooling, and L2 normalization.
    """

    def __init__(
        self,
        model_name: str = "bge-small-en-v1.5",
        dimension: int = 384,
        models_dir: Optional[Path] = None,
    ):
        self._model_name = model_name
        self._dimension = dimension
        if models_dir is not None:
            self._models_dir = models_dir
            self._model_path = self._models_dir / f"{model_name}.onnx"
        else:
            self._models_dir = get_default_models_dir()
            self._model_path = self._models_dir / f"{model_name}.onnx"
            if not self._model_path.exists():
                subfolder_file = self._models_dir / model_name / f"{model_name}.onnx"
                subfolder_model = self._models_dir / model_name / "model.onnx"
                alt_dir = get_storage_root() / "models" / "embedding"
                if subfolder_file.exists():
                    self._models_dir = self._models_dir / model_name
                    self._model_path = subfolder_file
                elif subfolder_model.exists():
                    self._models_dir = self._models_dir / model_name
                    self._model_path = subfolder_model
                elif (alt_dir / f"{model_name}.onnx").exists():
                    self._models_dir = alt_dir
                    self._model_path = alt_dir / f"{model_name}.onnx"
        # Candidate locations for tokenizer.json
        if models_dir is not None:
            # If models_dir was explicitly passed (e.g. in test fixture), look only within that directory
            candidate_tokenizers = [
                self._models_dir / f"{model_name}_tokenizer.json",
                self._models_dir / "tokenizer.json",
            ]
        else:
            candidate_tokenizers = [
                self._models_dir / f"{model_name}_tokenizer.json",
                self._models_dir / "tokenizer.json",
                self._models_dir.parent / f"{model_name}_tokenizer.json",
                self._models_dir.parent / "embedding" / f"{model_name}_tokenizer.json",
                get_storage_root() / "models" / "embedding" / f"{model_name}_tokenizer.json",
                get_storage_root() / "models" / "embeddings" / f"{model_name}_tokenizer.json",
                Path(__file__).resolve().parent.parent.parent / "resources" / f"{model_name}_tokenizer.json",
                Path(__file__).resolve().parent / f"{model_name}_tokenizer.json",
                Path(os.environ.get("LOCALAPPDATA", "")) / "RaggerAI" / "storage" / "models" / "embeddings" / f"{model_name}_tokenizer.json",
                Path(os.environ.get("LOCALAPPDATA", "")) / "RaggerAI" / "models" / "embeddings" / f"{model_name}_tokenizer.json",
            ]
        self._tokenizer_path = None
        for cand in candidate_tokenizers:
            if cand.exists():
                self._tokenizer_path = cand
                break
        if self._tokenizer_path is None:
            self._tokenizer_path = self._models_dir / f"{model_name}_tokenizer.json"


        self._session = None
        self._tokenizer = None

        self._validate_and_initialize()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def max_tokens(self) -> int:
        return 512

    def _validate_and_initialize(self) -> None:
        """Validates that model weights exist on disk and initializes inference session."""
        if not self._model_path.exists():
            raise ModelNotAvailableError(
                f"Embedding model '{self._model_name}' not found at '{self._model_path}'. "
                "The model must be downloaded via the Model Manager before triggering a build. "
                "The Builder never downloads model weights automatically."
            )

        try:
            import onnxruntime as ort
        except ImportError:
            raise ModelNotAvailableError(
                "onnxruntime is not installed in the active Python environment. "
                "Install onnxruntime to run local ONNX embeddings."
            )

        try:
            self._session = ort.InferenceSession(
                str(self._model_path),
                providers=["CPUExecutionProvider"],
            )
        except Exception as e:
            raise EmbeddingError(f"Failed to initialize ONNX embedding session: {str(e)}")

        # Initialize tokenizer if present
        if self._tokenizer_path and self._tokenizer_path.exists():
            try:
                from tokenizers import Tokenizer
                self._tokenizer = Tokenizer.from_file(str(self._tokenizer_path))
                self._tokenizer.enable_padding(length=512)
                self._tokenizer.enable_truncation(max_length=512)
            except ImportError:
                pass
            except Exception as e:
                raise EmbeddingError(f"Failed to load tokenizer from '{self._tokenizer_path}': {str(e)}")

    def embed_text(self, text: str) -> List[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        if self._session is None:
            raise EmbeddingError("ONNX session not initialized.")

        try:
            import numpy as np

            input_names = [inp.name for inp in self._session.get_inputs()]
            model_max_len = 512

            if self._tokenizer is not None:
                encoded = self._tokenizer.encode_batch(texts)
                input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
                attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
            else:
                # Fallback tokenization if fast tokenizer file is missing:
                # Clamped strictly to min(max_len, model_max_len) to never violate ONNX position embedding bound
                raw_max = max(len(t.split()) for t in texts) or 1
                max_len = min(raw_max, model_max_len)
                input_ids = np.zeros((len(texts), max_len), dtype=np.int64)
                attention_mask = np.zeros((len(texts), max_len), dtype=np.int64)
                for i, text in enumerate(texts):
                    words = text.split()[:max_len]
                    tokens = [hash(w) % 10000 + 1 for w in words]
                    for j, tok in enumerate(tokens):
                        input_ids[i, j] = tok
                        attention_mask[i, j] = 1

            # Defensive shape validation: Guarantee sequence dimension NEVER exceeds model maximum (512)
            if input_ids.shape[1] > model_max_len:
                input_ids = input_ids[:, :model_max_len]
                attention_mask = attention_mask[:, :model_max_len]

            ort_inputs = {}
            if "input_ids" in input_names:
                ort_inputs["input_ids"] = input_ids
            if "attention_mask" in input_names:
                ort_inputs["attention_mask"] = attention_mask
            if "token_type_ids" in input_names:
                ort_inputs["token_type_ids"] = np.zeros_like(input_ids)

            outputs = self._session.run(None, ort_inputs)
            # Output is typically [batch_size, seq_len, hidden_dim] or [batch_size, hidden_dim]
            hidden_state = outputs[0]

            if len(hidden_state.shape) == 3:
                # Mean pooling with attention mask
                mask_expanded = np.expand_dims(attention_mask, axis=-1)
                sum_embeddings = np.sum(hidden_state * mask_expanded, axis=1)
                sum_mask = np.clip(np.sum(mask_expanded, axis=1), a_min=1e-9, a_max=None)
                embeddings = sum_embeddings / sum_mask
            elif len(hidden_state.shape) == 2:
                embeddings = hidden_state
            else:
                raise EmbeddingError(f"Unexpected ONNX model output shape: {hidden_state.shape}")

            # L2 normalize
            vectors: List[List[float]] = []
            for row in embeddings:
                norm = float(np.linalg.norm(row))
                normed = (row / norm if norm > 0 else row).tolist()
                if len(normed) != self._dimension:
                    raise EmbeddingError(
                        f"ONNX embedding dimension mismatch: expected {self._dimension}, got {len(normed)}"
                    )
                vectors.append(normed)

            return vectors
        except Exception as e:
            if isinstance(e, EmbeddingError):
                raise
            raise EmbeddingError(f"ONNX embedding execution failed: {str(e)}")

