"""
Orchestrator Service for Phase 5 RAG Builder & Pipeline Execution Engine.
Enforces the approved contract: single build lock, cryptographic verification,
scratch execution, self-consistency retrieval sanity test, source drift revalidation,
and atomic pointer activation.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Any, Dict, List, Optional
import uuid

from ragger_engine.ingestion.models import DatasetModel, DocumentModel
from ragger_engine.ingestion.service import IngestionService
from ragger_engine.recommendation.models import (
    ApprovedBuildConfig,
    ChunkingStrategyType,
    RagArchitectureId,
)
from ragger_engine.recommendation.service import RecommendationService
from ragger_engine.recommendation.validation import compute_canonical_config_hash

from .chunking.base import BaseChunker, split_into_token_safe_subchunks
from .chunking.boundary import BoundaryParagraphChunker
from .chunking.hierarchical import ParentChildHierarchicalChunker
from .chunking.registry import get_chunker_for_strategy
from .chunking.tabular import TabularSchemaChunker
from .embeddings.base import BaseEmbeddingProvider
from .embeddings.factory import get_embedding_provider
from .exceptions import (
    ArchitectureNotBuildableError,
    BuildAlreadyRunningError,
    BuilderError,
    BuildGateError,
    ChunkingError,
    EmbeddingError,
    IndexingError,
    ModelNotAvailableError,
    RetrievalSanityError,
    SourceDriftError,
    VectorDbUnavailableError,
)
from .models import (
    BuildManifest,
    BuildProgress,
    BuildStage,
    Chunk,
    SourceSnapshot,
)
from .storage.base import BaseVectorStore
from .storage.factory import get_vector_store


def compute_file_sha256(path: Path) -> str:
    """Computes SHA-256 checksum of a file on disk."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class BuilderService:
    """
    Supervises end-to-end knowledge base construction.
    Guarantees that builds run in isolated scratch space and activate atomically.
    """

    def __init__(
        self,
        workspace_dir: Path,
        ingestion_service: IngestionService,
        recommendation_service: RecommendationService,
        embedding_provider_override: Optional[BaseEmbeddingProvider] = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.ingestion_service = ingestion_service
        self.recommendation_service = recommendation_service
        self._embedding_provider_override = embedding_provider_override

        self._lock = threading.Lock()
        self._active_build_id: Optional[str] = None
        self._cancel_requested: bool = False
        self._active_thread: Optional[threading.Thread] = None

        self._progress = BuildProgress(
            build_id=None,
            status="idle",
            current_stage=BuildStage.IDLE,
        )

    @property
    def progress(self) -> BuildProgress:
        """Thread-safe snapshot of current build progress."""
        with self._lock:
            return self._progress.model_copy()

    def get_active_build_id(self) -> Optional[str]:
        with self._lock:
            return self._active_build_id

    def get_active_manifest(self) -> Optional[BuildManifest]:
        """Loads the current atomically activated BuildManifest, if any exists."""
        active_pointer_file = self.workspace_dir / "active_build.json"
        if not active_pointer_file.exists():
            return None

        try:
            with open(active_pointer_file, "r", encoding="utf-8") as f:
                pointer_data = json.load(f)
            active_build_id = pointer_data.get("active_build_id")
            if not active_build_id:
                return None

            manifest_file = self.workspace_dir / "builds" / active_build_id / "manifest.json"
            if not manifest_file.exists():
                return None

            with open(manifest_file, "r", encoding="utf-8") as f:
                return BuildManifest.model_validate_json(f.read())
        except Exception:
            return None

    def validate_preflight(self) -> tuple[ApprovedBuildConfig, List[SourceSnapshot], BaseEmbeddingProvider, BaseVectorStore]:
        """
        Independent build gate verification.
        Validates existence, frozen state, canonical hash, source synchronization,
        source disk integrity, architecture buildability, and provider availability.
        """
        # 1. Load ApprovedBuildConfig
        config_path = self.workspace_dir / "approved_build_config.json"
        if not config_path.exists():
            raise BuildGateError("No approved_build_config.json snapshot found on disk.")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            config = ApprovedBuildConfig.model_validate(raw_data)
        except Exception as e:
            raise BuildGateError(f"Corrupt approved configuration snapshot: {str(e)}")

        if not config.is_frozen:
            raise BuildGateError("Approved configuration is not marked as frozen.")

        # 2. Enforce Option B: Graph RAG is non-buildable in Phase 5
        if config.approved_architecture == RagArchitectureId.GRAPH_RAG:
            raise ArchitectureNotBuildableError(
                "Graph RAG indexing requires entity-relationship graph pipelines scheduled for future phases. "
                "Current buildable architectures: document_rag, knowledge_rag, structured_data_rag, hybrid_rag, research_rag."
            )

        # 3. Canonical hash verification (excluding config_hash)
        expected_hash = compute_canonical_config_hash(
            architecture_id=config.approved_architecture,
            chunking_config=config.chunking_config,
            embedding_config=config.embedding_config,
            vector_db_config=config.vector_db_config,
            retrieval_config=config.retrieval_config,
            source_ids=config.source_ids,
        )
        if config.config_hash != expected_hash:
            raise BuildGateError(
                f"Configuration hash mismatch. Stored: '{config.config_hash}', Recomputed: '{expected_hash}'. "
                "Snapshot was modified outside approved workflow."
            )

        # 4. Source synchronization & disk snapshot verification
        snapshots: List[SourceSnapshot] = []
        for sid in config.source_ids:
            src = self.ingestion_service.registry.get_source(sid)
            if not src:
                raise SourceDriftError(
                    f"Source drift detected: approved source '{sid}' is missing from registry."
                )
            path_str = getattr(src, "file_path", None)
            candidates = [
                Path(path_str) if path_str else None,
                self.ingestion_service._file_paths.get(src.source_id) if hasattr(self.ingestion_service, "_file_paths") else None,
                self.workspace_dir / "sources" / src.original_filename,
                self.workspace_dir / src.original_filename,
                Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / src.original_filename,
                Path.cwd() / "engine" / "tests" / "fixtures" / src.original_filename,
                Path.cwd() / "tests" / "fixtures" / src.original_filename,
            ]
            path = None
            for c in candidates:
                if c and c.exists():
                    path = c
                    break
            if not path:
                path = Path(path_str or (self.workspace_dir / src.original_filename))

            if not path.exists():
                raise SourceDriftError(f"Registered source file missing on disk: '{path}'.")
            disk_sha = compute_file_sha256(path)
            if disk_sha != src.sha256_checksum:
                raise SourceDriftError(
                    f"Source content modified on disk: '{src.original_filename}' ({src.source_id}) hash changed."
                )
            snapshots.append(
                SourceSnapshot(
                    source_id=src.source_id,
                    sha256=src.sha256_checksum,
                    model_type=src.detected_format,
                    file_path=str(path.resolve()),
                )
            )

        # 5. Embedding Provider check (production model manager gate)
        if self._embedding_provider_override is not None:
            embedding_provider = self._embedding_provider_override
        else:
            embedding_provider = get_embedding_provider(config.embedding_config)

        # 6. Vector Store Provider check
        vector_store = get_vector_store(config.vector_db_config)

        return config, snapshots, embedding_provider, vector_store

    def start_build(self) -> str:
        """
        Initiates the asynchronous build pipeline.
        Returns the unique build_id.
        Raises BuildAlreadyRunningError (HTTP 409) if a build is active.
        """
        with self._lock:
            if self._active_build_id is not None:
                raise BuildAlreadyRunningError(
                    message="A build is currently active in this workspace.",
                    active_build_id=self._active_build_id,
                )

            # Preflight validation runs synchronously to fail early
            config, snapshots, embedding_provider, vector_store = self.validate_preflight()

            build_id = f"bld_{uuid.uuid4().hex[:8]}"
            self._active_build_id = build_id
            self._cancel_requested = False

            self._progress = BuildProgress(
                build_id=build_id,
                status="running",
                current_stage=BuildStage.PREFLIGHT,
                chunks_total=0,
                chunks_processed=0,
                vectors_total=0,
                vectors_processed=0,
                embedding_dimension=embedding_provider.dimension,
                elapsed_seconds=0.0,
                log_messages=[f"Preflight passed for {len(snapshots)} sources. Build ID: {build_id}"],
            )

        # Launch background execution
        self._active_thread = threading.Thread(
            target=self._run_pipeline,
            args=(build_id, config, snapshots, embedding_provider, vector_store),
            daemon=True,
        )
        self._active_thread.start()
        return build_id

    def cancel_build(self, build_id: str) -> None:
        """Requests graceful cancellation of the active build."""
        with self._lock:
            if self._active_build_id == build_id:
                self._cancel_requested = True
                self._progress.status = "cancel_requested"
                self._progress.current_stage = BuildStage.CANCEL_REQUESTED
                self._progress.log_messages.append("Cancellation requested by user.")

    def wait_for_completion(self, timeout: float = 10.0) -> bool:
        """Helper for testing: waits for background build execution thread to terminate."""
        thread = self._active_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
            return not thread.is_alive()
        return True

    def _update_progress(
        self,
        stage: BuildStage,
        chunks_total: Optional[int] = None,
        chunks_processed: Optional[int] = None,
        vectors_total: Optional[int] = None,
        vectors_processed: Optional[int] = None,
        log_message: Optional[str] = None,
        error_code: Optional[str] = None,
        message: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._progress.current_stage = stage
            if chunks_total is not None:
                self._progress.chunks_total = chunks_total
            if chunks_processed is not None:
                self._progress.chunks_processed = chunks_processed
            if vectors_total is not None:
                self._progress.vectors_total = vectors_total
            if vectors_processed is not None:
                self._progress.vectors_processed = vectors_processed
            if log_message:
                self._progress.log_messages.append(log_message)
            if error_code:
                self._progress.error_code = error_code
            if message:
                self._progress.message = message

    def _run_pipeline(
        self,
        build_id: str,
        config: ApprovedBuildConfig,
        snapshots: List[SourceSnapshot],
        embedding_provider: BaseEmbeddingProvider,
        vector_store: BaseVectorStore,
    ) -> None:
        start_time = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        scratch_dir = self.workspace_dir / "builds" / f"{build_id}_scratch"

        try:
            scratch_dir.mkdir(parents=True, exist_ok=True)

            # -----------------------------------------------------------------
            # Stage 1: CHUNKING
            # -----------------------------------------------------------------
            self._update_progress(BuildStage.CHUNKING, log_message="Starting format-specific chunking.")
            all_chunks: List[Chunk] = []

            for snap in snapshots:
                if self._cancel_requested:
                    raise BuilderError("Build cancelled during chunking.", code="CANCELLED")

                # Resolve normalized model from ingestion service
                source_record = self.ingestion_service.registry.get_source(snap.source_id)
                if not source_record:
                    raise SourceDriftError(f"Source {snap.source_id} missing from registry.")

                # Retrieve or parse normalized representation
                model = self.ingestion_service.get_normalized_model(source_record.source_id)
                if model is None:
                    model = self.ingestion_service.parse_only(
                        file_path=Path(snap.file_path),
                        source_id=source_record.source_id,
                    )

                # Architecture-specific dispatch preserving Document vs Dataset models
                if config.approved_architecture == RagArchitectureId.HYBRID_RAG:
                    if isinstance(model, DatasetModel):
                        chunker = TabularSchemaChunker()
                    elif config.chunking_config.strategy == ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL:
                        chunker = ParentChildHierarchicalChunker()
                    else:
                        chunker = BoundaryParagraphChunker()
                else:
                    chunker = get_chunker_for_strategy(config.chunking_config.strategy)

                chunks = chunker.chunk(
                    model=model,
                    source_id=source_record.source_id,
                    source_name=source_record.original_filename,
                    config=config.chunking_config,
                )
                all_chunks.extend(chunks)
                self._update_progress(
                    BuildStage.CHUNKING,
                    chunks_total=len(all_chunks),
                    chunks_processed=len(all_chunks),
                    log_message=f"Chunked {source_record.original_filename}: produced {len(chunks)} chunks.",
                )

            if not all_chunks:
                raise ChunkingError("No searchable chunks produced from ingested sources.")

            # Model token limit guard: split any oversized chunk into token-safe subchunks
            model_max_tokens = getattr(embedding_provider, "max_tokens", 512)
            safe_chunks: List[Chunk] = []
            for c in all_chunks:
                safe_chunks.extend(split_into_token_safe_subchunks(c, max_tokens=model_max_tokens, overlap_tokens=50))
            all_chunks = safe_chunks

            # -----------------------------------------------------------------
            # Stage 2: EMBEDDING
            # -----------------------------------------------------------------
            self._update_progress(
                BuildStage.EMBEDDING,
                chunks_total=len(all_chunks),
                chunks_processed=len(all_chunks),
                vectors_total=len(all_chunks),
                vectors_processed=0,
                log_message=f"Generating dense vector embeddings ({embedding_provider.model_name}) for {len(all_chunks)} chunks.",
            )

            all_vectors: List[List[float]] = []
            batch_size = 16

            for i in range(0, len(all_chunks), batch_size):
                if self._cancel_requested:
                    raise BuilderError("Build cancelled during embedding.", code="CANCELLED")

                batch_chunks = all_chunks[i : i + batch_size]
                batch_texts = [c.text for c in batch_chunks]
                batch_vectors = embedding_provider.embed_batch(batch_texts)

                all_vectors.extend(batch_vectors)
                elapsed = time.monotonic() - start_mono
                with self._lock:
                    self._progress.vectors_processed = len(all_vectors)
                    self._progress.elapsed_seconds = elapsed

            # -----------------------------------------------------------------
            # Stage 3: INDEXING
            # -----------------------------------------------------------------
            self._update_progress(BuildStage.INDEXING, log_message="Persisting vector index to scratch storage.")
            if self._cancel_requested:
                raise BuilderError("Build cancelled during indexing.", code="CANCELLED")

            vector_store.add_chunks(all_chunks, all_vectors)
            index_dir = scratch_dir / "index"
            vector_store.persist(index_dir)

            # -----------------------------------------------------------------
            # Stage 4: VERIFYING (Reload + Retrieval Sanity Test + Revalidation)
            # -----------------------------------------------------------------
            self._update_progress(BuildStage.VERIFYING, log_message="Verifying index reload and self-consistency.")
            if self._cancel_requested:
                raise BuilderError("Build cancelled during verification.", code="CANCELLED")

            # 1. Reload index from scratch storage
            reloaded_store = get_vector_store(config.vector_db_config)
            reloaded_store.reload(index_dir)

            # 2. Self-Consistency Retrieval Sanity Test:
            # Query reloaded store with sample chunk to confirm zero corruption upon persistence
            sample_chunk = all_chunks[0]
            sample_query_vec = embedding_provider.embed_text(sample_chunk.text)
            hits = reloaded_store.query_by_vector(sample_query_vec, top_k=3)

            if not hits:
                raise RetrievalSanityError("Self-consistency check failed: reloaded store returned zero results.")

            top_hit_chunk, sim = hits[0]
            # Verify cosine score >= 0.70 for exact self-query
            if sim < 0.70:
                raise RetrievalSanityError(
                    f"Self-consistency check failed: cosine similarity {sim:.4f} < 0.70 threshold."
                )
            if top_hit_chunk.chunk_id != sample_chunk.chunk_id:
                raise RetrievalSanityError(
                    f"Self-consistency check failed: expected chunk {sample_chunk.chunk_id}, got {top_hit_chunk.chunk_id}."
                )

            # 3. Re-verify source files on disk against preflight snapshot
            for snap in snapshots:
                p = Path(snap.file_path)
                if not p.exists() or compute_file_sha256(p) != snap.sha256:
                    raise SourceDriftError(
                        f"Source integrity broken during build: file '{snap.file_path}' was modified or deleted."
                    )

            # -----------------------------------------------------------------
            # Stage 5: COMPLETED (Manifest Issuance + Atomic Activation)
            # -----------------------------------------------------------------
            completed_time = datetime.now(timezone.utc)
            duration_ms = (time.monotonic() - start_mono) * 1000.0

            manifest_dict = {
                "manifest_id": f"man_{build_id}",
                "workspace_id": self.workspace_dir.name,
                "build_id": build_id,
                "config_id": config.config_id,
                "config_version": config.config_version,
                "config_hash": config.config_hash,
                "source_ids": config.source_ids,
                "source_hashes": {s.source_id: s.sha256 for s in snapshots},
                "approved_architecture": config.approved_architecture.value,
                "chunking_config": config.chunking_config.model_dump(),
                "embedding_config": config.embedding_config.model_dump(),
                "vector_db_config": config.vector_db_config.model_dump(),
                "retrieval_config": config.retrieval_config.model_dump(),
                "chunk_count": len(all_chunks),
                "vector_count": len(all_vectors),
                "embedding_dimension": embedding_provider.dimension,
                "embedding_model": embedding_provider.model_name,
                "vector_store": config.vector_db_config.provider,
                "started_at": start_time,
                "completed_at": completed_time,
                "build_duration_ms": duration_ms,
                "status": "completed",
            }
            manifest_hash = BuildManifest.compute_manifest_hash(manifest_dict)
            manifest = BuildManifest(manifest_hash=manifest_hash, **manifest_dict)

            # Write manifest to scratch directory
            with open(scratch_dir / "manifest.json", "w", encoding="utf-8") as f:
                f.write(manifest.model_dump_json(indent=2))

            # Atomic directory promotion: rename scratch to final build directory
            final_build_dir = self.workspace_dir / "builds" / build_id
            if final_build_dir.exists():
                shutil.rmtree(final_build_dir)
            os.rename(str(scratch_dir), str(final_build_dir))

            # Atomic activation pointer: write active_build.json.tmp, flush & fsync, os.replace
            active_pointer_tmp = self.workspace_dir / "active_build.json.tmp"
            active_pointer_final = self.workspace_dir / "active_build.json"

            pointer_content = {
                "active_build_id": build_id,
                "manifest_id": manifest.manifest_id,
                "manifest_hash": manifest.manifest_hash,
                "activated_at": completed_time.isoformat(),
            }
            with open(active_pointer_tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(pointer_content, indent=2))
                f.flush()
                os.fsync(f.fileno())

            os.replace(str(active_pointer_tmp), str(active_pointer_final))

            with self._lock:
                self._progress.status = "completed"
                self._progress.current_stage = BuildStage.COMPLETED
                self._progress.elapsed_seconds = (time.monotonic() - start_mono)
                self._progress.log_messages.append(
                    f"Build {build_id} completed successfully in {duration_ms:.1f}ms. Manifest: {manifest_hash[:12]}."
                )

        except Exception as err:
            # Clean up scratch directory on failure or cancellation
            if scratch_dir.exists():
                try:
                    shutil.rmtree(scratch_dir)
                except Exception:
                    pass

            is_cancelled = self._cancel_requested or (isinstance(err, BuilderError) and err.code == "CANCELLED")
            with self._lock:
                if is_cancelled:
                    self._progress.status = "cancelled"
                    self._progress.current_stage = BuildStage.CANCELLED
                    self._progress.error_code = "BUILD_CANCELLED"
                    self._progress.message = "Build execution was cancelled."
                else:
                    self._progress.status = "failed"
                    self._progress.current_stage = BuildStage.FAILED
                    err_code = getattr(err, "code", "BUILD_FAILED")
                    self._progress.error_code = err_code
                    self._progress.message = str(err)
                    self._progress.log_messages.append(f"Build failed with {err_code}: {str(err)}")
        finally:
            with self._lock:
                self._active_build_id = None
                self._cancel_requested = False
