"""
Zero-dependency, file-backed flat cosine vector store adapter.
Explicitly designated as the baseline local development adapter (local_flat_index).
Stores chunks in chunks.jsonl and normalized vectors in vectors.json with index_meta.json.
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple
from ..exceptions import IndexingError
from ..models import Chunk
from .base import BaseVectorStore


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Computes cosine similarity between two float vectors."""
    if len(v1) != len(v2) or not v1:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class LocalFlatVectorStore(BaseVectorStore):
    """
    Flat cosine vector store persisting into disk files.
    Self-contained, reliable, and easily inspectable.
    """

    def __init__(self, metric: str = "cosine"):
        self.metric = metric
        self.chunks: List[Chunk] = []
        self.vectors: List[List[float]] = []
        self.dimension: int = 0

    def add_chunks(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        if len(chunks) != len(vectors):
            raise IndexingError(
                f"Mismatch between chunk count ({len(chunks)}) and vector count ({len(vectors)})."
            )
        if vectors and self.dimension == 0:
            self.dimension = len(vectors[0])

        for c, v in zip(chunks, vectors):
            if len(v) != self.dimension:
                raise IndexingError(
                    f"Inconsistent vector dimension: expected {self.dimension}, got {len(v)}."
                )
            self.chunks.append(c)
            self.vectors.append(v)

    def persist(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)

        chunks_file = directory / "chunks.jsonl"
        vectors_file = directory / "vectors.json"
        meta_file = directory / "index_meta.json"

        # 1. Write chunks.jsonl
        with open(chunks_file, "w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(c.model_dump_json() + "\n")

        # 2. Write vectors.json
        with open(vectors_file, "w", encoding="utf-8") as f:
            json.dump(self.vectors, f)

        # 3. Write index_meta.json
        meta = {
            "provider": "local_flat_index",
            "metric": self.metric,
            "dimension": self.dimension,
            "chunk_count": len(self.chunks),
            "vector_count": len(self.vectors),
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        return directory

    def reload(self, directory: Path) -> None:
        chunks_file = directory / "chunks.jsonl"
        vectors_file = directory / "vectors.json"
        meta_file = directory / "index_meta.json"

        if not (chunks_file.exists() and vectors_file.exists() and meta_file.exists()):
            raise IndexingError(f"Missing required vector store files in '{directory}'.")

        # Load meta
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
            self.dimension = meta.get("dimension", 0)
            self.metric = meta.get("metric", "cosine")

        # Load chunks
        reloaded_chunks: List[Chunk] = []
        with open(chunks_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    reloaded_chunks.append(Chunk.model_validate_json(line))
        self.chunks = reloaded_chunks

        # Load vectors
        with open(vectors_file, "r", encoding="utf-8") as f:
            self.vectors = json.load(f)

        if len(self.chunks) != len(self.vectors):
            raise IndexingError("Corrupted index: reloaded chunk count does not match vector count.")

    def query_by_vector(self, query_vector: List[float], top_k: int = 5) -> List[Tuple[Chunk, float]]:
        if not self.chunks or not self.vectors:
            return []

        scored: List[Tuple[Chunk, float]] = []
        for chunk, vec in zip(self.chunks, self.vectors):
            sim = cosine_similarity(query_vector, vec)
            scored.append((chunk, sim))

        # Sort descending by similarity
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "provider": "local_flat_index",
            "dimension": self.dimension,
            "chunk_count": len(self.chunks),
            "vector_count": len(self.vectors),
        }
