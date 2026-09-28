"""
LanceDB vector store adapter.
Directly interfaces with LanceDB dataset tables when the lancedb library is present.
Raises VectorDbUnavailableError if the dependency is missing.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple
from ..exceptions import IndexingError, VectorDbUnavailableError
from ..models import Chunk, ChunkMetadata, ChunkType
from .base import BaseVectorStore


class LanceDbVectorStore(BaseVectorStore):
    """LanceDB vector store adapter."""

    def __init__(self, metric: str = "cosine"):
        self.metric = metric
        self.chunks: List[Chunk] = []
        self.vectors: List[List[float]] = []
        self.dimension: int = 0
        self._db = None

        self._validate_available()

    def _validate_available(self) -> None:
        try:
            import lancedb  # noqa: F401
        except ImportError:
            raise VectorDbUnavailableError(
                "LanceDB library is not installed in the current environment. "
                "Install lancedb or configure 'local_flat_index' as vector_db in ApprovedBuildConfig."
            )

    def add_chunks(self, chunks: List[Chunk], vectors: List[List[float]]) -> None:
        if len(chunks) != len(vectors):
            raise IndexingError("Chunks and vectors count mismatch.")
        if vectors and self.dimension == 0:
            self.dimension = len(vectors[0])
        self.chunks.extend(chunks)
        self.vectors.extend(vectors)

    def persist(self, directory: Path) -> Path:
        import lancedb
        directory.mkdir(parents=True, exist_ok=True)

        # Write chunks.jsonl for unified archival and retrieval compatibility
        chunks_file = directory / "chunks.jsonl"
        with open(chunks_file, "w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(c.model_dump_json() + "\n")

        self._db = lancedb.connect(str(directory))
        data = []
        for c, v in zip(self.chunks, self.vectors):
            data.append({
                "id": c.chunk_id,
                "source_id": c.source_id,
                "text": c.text,
                "chunk_type": c.chunk_type.value if hasattr(c.chunk_type, "value") else str(c.chunk_type),
                "vector": v,
                "metadata": c.metadata.model_dump_json(),
                "token_count": c.token_count,
            })
        self._db.create_table("knowledge_chunks", data=data, mode="overwrite")
        return directory

    def reload(self, directory: Path) -> None:
        import lancedb
        if not directory.exists():
            raise IndexingError(f"LanceDB directory '{directory}' does not exist.")
        self._db = lancedb.connect(str(directory))
        table = self._db.open_table("knowledge_chunks")
        df = table.to_pandas()
        self.chunks = []
        self.vectors = []
        for _, row in df.iterrows():
            raw_meta = row.get("metadata", "{}")
            if isinstance(raw_meta, str):
                meta_obj = ChunkMetadata.model_validate_json(raw_meta)
            elif isinstance(raw_meta, dict):
                meta_obj = ChunkMetadata.model_validate(raw_meta)
            else:
                meta_obj = ChunkMetadata(
                    source_id=str(row.get("source_id", "")),
                    source_name="document",
                    chunk_index=0,
                    token_count=int(row.get("token_count", 1)),
                )

            c = Chunk(
                chunk_id=str(row["id"]),
                source_id=str(row.get("source_id", meta_obj.source_id)),
                text=str(row["text"]),
                chunk_type=ChunkType(row.get("chunk_type", "standard_paragraph")),
                metadata=meta_obj,
                token_count=int(row.get("token_count", meta_obj.token_count or 1)),
            )
            self.chunks.append(c)
            self.vectors.append(list(row["vector"]))
        if self.vectors:
            self.dimension = len(self.vectors[0])

    def query_by_vector(self, query_vector: List[float], top_k: int = 5) -> List[Tuple[Chunk, float]]:
        if self._db is None:
            raise IndexingError("LanceDB not connected or persisted.")
        table = self._db.open_table("knowledge_chunks")
        results = table.search(query_vector).limit(top_k).to_pandas()
        chunks_by_id = {c.chunk_id: c for c in self.chunks}
        matched = []
        for _, row in results.iterrows():
            chunk_id = str(row["id"])
            chunk_obj = chunks_by_id.get(chunk_id)
            if chunk_obj:
                sim = 1.0 - float(row.get("_distance", 0.0))
                matched.append((chunk_obj, sim))
        return matched

    def get_stats(self) -> Dict[str, Any]:
        return {
            "provider": "lancedb",
            "dimension": self.dimension,
            "chunk_count": len(self.chunks),
            "vector_count": len(self.vectors),
        }
