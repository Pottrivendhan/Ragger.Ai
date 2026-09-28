"""
Core Retrieval Service for Phase 6 RAG Retrieval Subsystem.
Enforces read-only index access, independent canonical manifest verification,
single-flight thread-safe hot reload, model manager boundary compliance,
and safe instruction-delimited grounded context assembly.
"""

from datetime import datetime
import json
from pathlib import Path
import threading
import time
from typing import Dict, List, Optional

from ragger_engine.builder.embeddings.base import BaseEmbeddingProvider
from ragger_engine.builder.embeddings.factory import get_embedding_provider
from ragger_engine.builder.models import BuildManifest, Chunk
from ragger_engine.builder.storage.factory import get_vector_store
from ragger_engine.builder.storage.base import BaseVectorStore
from ragger_engine.recommendation.models import EmbeddingConfig, VectorDbConfig

from .exceptions import (
    ArchitectureNotRetrievableError,
    BuildIncompleteError,
    BuildUnavailableError,
    InvalidTopKError,
    ManifestCorruptedError,
    NoActiveBuildError,
    QueryEmbeddingError,
    RetrievalEngineError,
)
from .models import (
    RetrievalQuery,
    RetrievalResponse,
    RetrievalStatus,
    RetrievedChunk,
)
from .sparse.bm25 import InvertedBM25Index
from .strategies.base import BaseRetrievalStrategy
from .strategies.dense import DenseVectorStrategy
from .strategies.hierarchical import ParentExpansionStrategy
from .strategies.hybrid import RrfHybridStrategy
from .strategies.research import SectionAwareRerankStrategy
from .strategies.structured import DualQueryRoutingStrategy


class BuildRuntimeCache:
    """Immutable in-memory cache holding loaded index structures for a specific compiled build."""

    def __init__(
        self,
        build_id: str,
        manifest_hash: str,
        manifest: BuildManifest,
        vector_store: BaseVectorStore,
        chunks: List[Chunk],
        chunks_by_id: Dict[str, Chunk],
        embedding_provider: BaseEmbeddingProvider,
        strategy: BaseRetrievalStrategy,
    ):
        self.build_id = build_id
        self.manifest_hash = manifest_hash
        self.manifest = manifest
        self.vector_store = vector_store
        self.chunks = chunks
        self.chunks_by_id = chunks_by_id
        self.embedding_provider = embedding_provider
        self.strategy = strategy


# Retain ActiveBuildCache as alias for backward compatibility with existing tests
ActiveBuildCache = BuildRuntimeCache


class RetrievalService:
    """
    Supervises search and context assembly against verified build runtimes.
    Supports both RAG-scoped execution (explicit build_id) and legacy workspace fallback.
    Strictly read-only against build artifacts. Thread-safe single-flight loading per build.
    """

    def __init__(
        self,
        workspace_dir: Path,
        embedding_provider_override: Optional[BaseEmbeddingProvider] = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self._embedding_provider_override = embedding_provider_override

        # Per-build single-flight locks and immutable runtime cache registry
        self._registry_lock = threading.Lock()
        self._build_locks: Dict[str, threading.Lock] = {}
        self._build_runtimes: Dict[str, BuildRuntimeCache] = {}

    @property
    def _active_cache(self) -> Optional[BuildRuntimeCache]:
        """Backward-compatibility property returning currently active build cache if present."""
        active_pointer_file = self.workspace_dir / "active_build.json"
        if not active_pointer_file.exists():
            return None
        try:
            with open(active_pointer_file, "r", encoding="utf-8") as f:
                b_id = json.load(f).get("active_build_id")
            if b_id and b_id in self._build_runtimes:
                return self._build_runtimes[b_id]
        except Exception:
            pass
        return None

    @_active_cache.setter
    def _active_cache(self, value: Optional[BuildRuntimeCache]):
        """Backward-compatibility setter for clearing or updating the active cache in tests."""
        if value is None:
            with self._registry_lock:
                self._build_runtimes.clear()
        elif hasattr(value, "build_id"):
            with self._registry_lock:
                self._build_runtimes[value.build_id] = value

    def get_status(self) -> RetrievalStatus:
        """Returns the current diagnostic status of the active build."""
        active_pointer_file = self.workspace_dir / "active_build.json"
        if not active_pointer_file.exists():
            return RetrievalStatus(has_active_build=False)

        try:
            with open(active_pointer_file, "r", encoding="utf-8") as f:
                pointer = json.load(f)
            active_build_id = pointer.get("active_build_id")
            if not active_build_id:
                return RetrievalStatus(has_active_build=False)

            manifest_path = self.workspace_dir / "builds" / active_build_id / "manifest.json"
            if not manifest_path.exists():
                return RetrievalStatus(has_active_build=False)

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_dict = json.load(f)
            manifest = BuildManifest.model_validate(manifest_dict)

            retrieval_cfg = manifest.retrieval_config or {}
            return RetrievalStatus(
                has_active_build=True,
                active_build_id=manifest.build_id,
                manifest_id=manifest.manifest_id,
                manifest_hash=manifest.manifest_hash,
                approved_architecture=manifest.approved_architecture,
                chunk_count=manifest.chunk_count,
                vector_count=manifest.vector_count,
                embedding_model=manifest.embedding_model,
                vector_store=manifest.vector_store,
                retrieval_strategy=retrieval_cfg.get("strategy"),
            )
        except Exception:
            return RetrievalStatus(has_active_build=False)

    def _get_build_lock(self, build_id: str) -> threading.Lock:
        """Returns or instantiates a dedicated single-flight Lock for the specified build_id."""
        with self._registry_lock:
            if build_id not in self._build_locks:
                self._build_locks[build_id] = threading.Lock()
            return self._build_locks[build_id]

    def reload_active_cache(self) -> BuildRuntimeCache:
        """
        Forces reload of the build defined in active_build.json.
        Preserved for backward compatibility.
        """
        active_pointer_file = self.workspace_dir / "active_build.json"
        if not active_pointer_file.exists():
            raise NoActiveBuildError("No active_build.json found in workspace.")
        with open(active_pointer_file, "r", encoding="utf-8") as f:
            b_id = json.load(f).get("active_build_id")
        if not b_id:
            raise NoActiveBuildError("active_build.json does not specify an active_build_id.")
        return self.get_or_load_build_runtime(b_id, is_scoped_call=False, force_reload=True)

    def _get_or_load_active_cache(self) -> BuildRuntimeCache:
        """Retrieves cached active build; falls back to active_build.json if unscoped."""
        active_pointer_file = self.workspace_dir / "active_build.json"
        if not active_pointer_file.exists():
            raise NoActiveBuildError("No active_build.json found in workspace.")

        pointer = None
        for attempt in range(10):
            try:
                with open(active_pointer_file, "r", encoding="utf-8") as f:
                    pointer = json.load(f)
                break
            except (PermissionError, json.JSONDecodeError) as e:
                if attempt == 9:
                    raise NoActiveBuildError(f"Corrupted active_build.json: {str(e)}")
                time.sleep(0.01)
            except Exception as e:
                raise NoActiveBuildError(f"Corrupted active_build.json: {str(e)}")

        target_build_id = pointer.get("active_build_id") if pointer else None
        target_hash = pointer.get("manifest_hash") if pointer else None

        if not target_build_id or not target_hash:
            raise NoActiveBuildError("active_build.json is missing required build_id or manifest_hash.")

        return self.get_or_load_build_runtime(target_build_id, is_scoped_call=False)

    def get_or_load_build_runtime(
        self,
        build_id: str,
        is_scoped_call: bool = True,
        force_reload: bool = False,
    ) -> BuildRuntimeCache:
        """
        Retrieves or initializes an immutable BuildRuntimeCache for a specific build_id.
        Enforces:
        1. Per-build atomic single-flight lock: duplicate simultaneous calls for build_id execute ONE disk load.
        2. Strict verification: folder exists, manifest.build_id matches, canonical hash matches,
           status == completed, architecture supported.
        3. Strict no-fallback on scoped calls: if build is missing or corrupt, raises BuildUnavailableError / ManifestCorruptedError.
           Zero silent fallback to active_build.json.
        """
        if not build_id or not build_id.strip():
            raise BuildUnavailableError(build_id, "build_id must be a non-empty string.")

        # Check existing immutable runtime without waiting for lock if not forcing reload
        if not force_reload and build_id in self._build_runtimes:
            return self._build_runtimes[build_id]

        build_lock = self._get_build_lock(build_id)
        with build_lock:
            # Double-check cache inside per-build lock
            if not force_reload and build_id in self._build_runtimes:
                return self._build_runtimes[build_id]

            build_dir = self.workspace_dir / "builds" / build_id
            manifest_file = build_dir / "manifest.json"

            if not build_dir.exists() or not manifest_file.exists():
                msg = f"Build directory or manifest missing for build '{build_id}'."
                if is_scoped_call:
                    raise BuildUnavailableError(build_id, msg)
                else:
                    raise NoActiveBuildError(msg)

            # 1. Load manifest and verify status
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    raw_manifest_dict = json.load(f)
            except Exception as e:
                msg = f"Corrupted manifest JSON for build '{build_id}': {str(e)}"
                if is_scoped_call:
                    raise BuildUnavailableError(build_id, msg)
                else:
                    raise NoActiveBuildError(msg)

            manifest = BuildManifest.model_validate(raw_manifest_dict)

            # Strict verification: manifest build_id must match requested build_id
            if manifest.build_id != build_id:
                raise BuildUnavailableError(
                    build_id,
                    f"Integrity check failed: manifest declared build_id '{manifest.build_id}', expected '{build_id}'.",
                )

            if manifest.status != "completed":
                raise BuildIncompleteError(status=manifest.status)

            # 2. Canonical SHA-256 manifest hash verification (reusing exact Phase 5 contract)
            recomputed_hash = BuildManifest.compute_manifest_hash(manifest.model_dump())
            if recomputed_hash != manifest.manifest_hash:
                raise ManifestCorruptedError(
                    stored_hash=manifest.manifest_hash,
                    computed_hash=recomputed_hash,
                )

            # 3. Check architecture support (Graph RAG is non-retrievable Option B)
            if manifest.approved_architecture == "graph_rag":
                raise ArchitectureNotRetrievableError(
                    architecture="graph_rag",
                    message=(
                        "Graph RAG indexing and retrieval are scheduled for future development (Option B). "
                        "Supported retrievable architectures: document_rag, knowledge_rag, structured_data_rag, "
                        "hybrid_rag, research_rag."
                    ),
                )

            # 4. Read-only reload of Vector Store
            index_dir = build_dir / "index"
            vector_db_cfg = (
                manifest.vector_db_config
                if isinstance(manifest.vector_db_config, VectorDbConfig)
                else VectorDbConfig.model_validate(manifest.vector_db_config)
            )
            vector_store = get_vector_store(vector_db_cfg)
            vector_store.reload(index_dir)

            # 5. Read-only reload of Chunks from chunks.jsonl
            chunks_file = index_dir / "chunks.jsonl"
            chunks: List[Chunk] = []
            chunks_by_id: Dict[str, Chunk] = {}
            if chunks_file.exists():
                with open(chunks_file, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            chk = Chunk.model_validate_json(line)
                            chunks.append(chk)
                            chunks_by_id[chk.chunk_id] = chk

            # 6. Embedding provider check
            if self._embedding_provider_override is not None:
                embedding_provider = self._embedding_provider_override
            else:
                embedding_cfg = (
                    manifest.embedding_config
                    if isinstance(manifest.embedding_config, EmbeddingConfig)
                    else EmbeddingConfig.model_validate(manifest.embedding_config)
                )
                embedding_provider = get_embedding_provider(embedding_cfg)

            # 7. Assemble architecture-specific strategy
            arch = manifest.approved_architecture
            strategy: BaseRetrievalStrategy

            if arch == "document_rag":
                strategy = DenseVectorStrategy(vector_store=vector_store, manifest=manifest)
            elif arch == "knowledge_rag":
                strategy = ParentExpansionStrategy(
                    vector_store=vector_store,
                    chunks_by_id=chunks_by_id,
                    manifest=manifest,
                )
            elif arch == "structured_data_rag":
                strategy = DualQueryRoutingStrategy(
                    vector_store=vector_store,
                    chunks=chunks,
                    manifest=manifest,
                )
            elif arch == "hybrid_rag":
                bm25 = InvertedBM25Index(chunks)
                strategy = RrfHybridStrategy(
                    vector_store=vector_store,
                    bm25_index=bm25,
                    chunks_by_id=chunks_by_id,
                    manifest=manifest,
                )
            elif arch == "research_rag":
                bm25 = InvertedBM25Index(chunks)
                strategy = SectionAwareRerankStrategy(
                    vector_store=vector_store,
                    bm25_index=bm25,
                    chunks_by_id=chunks_by_id,
                    manifest=manifest,
                )
            else:
                raise ArchitectureNotRetrievableError(architecture=arch)

            runtime = BuildRuntimeCache(
                build_id=build_id,
                manifest_hash=manifest.manifest_hash,
                manifest=manifest,
                vector_store=vector_store,
                chunks=chunks,
                chunks_by_id=chunks_by_id,
                embedding_provider=embedding_provider,
                strategy=strategy,
            )

            # Cache immutable runtime in registry
            self._build_runtimes[build_id] = runtime
            return runtime

    def retrieve(self, query: RetrievalQuery, build_id: Optional[str] = None) -> RetrievalResponse:
        """
        Executes grounded retrieval query against a verified build.
        If build_id is supplied: scoped retrieval directly against build_id's immutable runtime.
        If build_id is None: legacy workspace retrieval resolving active_build.json.
        Measures execution latency and constructs delimited grounded context.
        """
        start_time = time.monotonic()
        if build_id:
            cache = self.get_or_load_build_runtime(build_id, is_scoped_call=True)
        else:
            cache = self._get_or_load_active_cache()

        # Validate top_k against manifest approved boundaries
        retrieval_cfg = cache.manifest.retrieval_config or {}
        default_top_k = retrieval_cfg.get("top_k", 5)
        max_allowed_top_k = min(default_top_k * 4, 50)

        effective_top_k = query.top_k if query.top_k is not None else default_top_k
        if effective_top_k > max_allowed_top_k:
            raise InvalidTopKError(
                f"Requested top_k ({effective_top_k}) exceeds maximum permitted limit ({max_allowed_top_k})."
            )

        # Generate query embedding
        try:
            vectors = cache.embedding_provider.embed_batch([query.query])
            if not vectors or not vectors[0]:
                raise QueryEmbeddingError("Embedding provider returned empty vector for query.")
            query_vector = vectors[0]
        except Exception as e:
            if isinstance(e, RetrievalEngineError):
                raise
            raise QueryEmbeddingError(f"Failed to embed query: {str(e)}")

        # Execute architecture strategy
        raw_results: List[RetrievedChunk] = cache.strategy.retrieve(
            query=query.query,
            query_vector=query_vector,
            top_k=effective_top_k,
            filters=query.filters,
        )

        from .deduplication import deduplicate_retrieved_chunks
        results: List[RetrievedChunk] = deduplicate_retrieved_chunks(raw_results)

        latency_ms = round((time.monotonic() - start_time) * 1000, 2)

        # Assemble safe instruction-delimited grounded context prompt
        grounded_prompt = self._assemble_grounded_context(query.query, results)

        return RetrievalResponse(
            query=query.query,
            architecture=cache.manifest.approved_architecture,
            strategy=retrieval_cfg.get("strategy", "unknown"),
            results=results,
            total_candidates=len(results),
            latency_ms=latency_ms,
            manifest_id=cache.manifest.manifest_id,
            manifest_hash=cache.manifest.manifest_hash,
            grounded_context_prompt=grounded_prompt,
        )

    def _assemble_grounded_context(
        self, query: str, chunks: List[RetrievedChunk]
    ) -> str:
        """
        Constructs standard instruction-delimited grounded context prompt.
        Delimited to prevent document content from masquerading as system policy.
        """
        lines = [
            "<<<BEGIN SYSTEM GROUNDING CONTEXT>>>",
            "You are an expert technical assistant answering questions based strictly on the provided context.",
            "If the provided context does not contain sufficient evidence to answer the question, state clearly:",
            '"Based on the provided sources, there is insufficient information to answer this question."',
            "Do not speculate or extrapolate beyond the explicit facts in the context.",
            "Every factual statement must cite its source using the format [Source: <filename>, Page: <p>].",
            "",
            "<<<BEGIN RETRIEVED SOURCES>>>",
        ]

        for c in chunks:
            lines.append("---")
            lines.append(c.citation)
            lines.append(f"[Chunk ID: {c.chunk_id}]")
            lines.append(c.text.strip())
            lines.append("---")

        lines.extend([
            "<<<END RETRIEVED SOURCES>>>",
            "",
            "<<<USER QUERY>>>",
            query,
            "<<<END USER QUERY>>>",
        ])

        return "\n".join(lines)
