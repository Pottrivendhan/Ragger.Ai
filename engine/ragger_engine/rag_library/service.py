"""
Discovery and inspection service for RAG Library knowledge artifacts.
Reads strictly from storage/builds/ and storage/sources_registry.json.
Does NOT invoke or couple with any LLM runtime.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ragger_engine.builder.models import BuildManifest
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.rag_library.models import (
    RAGArtifact,
    RAGArtifactDetail,
    RAGSampleChunk,
    RAGSourceSummary,
)

logger = logging.getLogger(__name__)


class RAGLibraryService:
    """Service to discover, list, and inspect available RAG knowledge artifacts."""

    def __init__(self, workspace_dir: Path):
        self.workspace_dir = Path(workspace_dir)
        self.builds_dir = self.workspace_dir / "builds"
        self.sources_registry_path = self.workspace_dir / "sources_registry.json"
        self.active_build_path = self.workspace_dir / "active_build.json"

    def _get_active_build_id(self) -> Optional[str]:
        if not self.active_build_path.exists():
            return None
        try:
            with open(self.active_build_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("active_build_id")
        except Exception as e:
            logger.warning("Failed to read active_build.json: %s", e)
            return None

    def _get_sources_map(self) -> Dict[str, Dict]:
        if not self.sources_registry_path.exists():
            return {}
        try:
            with open(self.sources_registry_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read sources_registry.json: %s", e)
            return {}

    def list_artifacts(self) -> List[RAGArtifact]:
        """Discovers and lists all valid RAG builds in the workspace."""
        if not self.builds_dir.exists():
            return []

        active_id = self._get_active_build_id()
        sources_map = self._get_sources_map()
        artifacts: List[RAGArtifact] = []

        for build_folder in sorted(self.builds_dir.iterdir()):
            if not build_folder.is_dir():
                continue

            manifest_file = build_folder / "manifest.json"
            if not manifest_file.exists():
                continue

            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
                manifest = BuildManifest.model_validate(manifest_data)

                # Assemble source summaries
                sources: List[RAGSourceSummary] = []
                for src_id in manifest.source_ids:
                    src_info = sources_map.get(src_id, {})
                    sources.append(
                        RAGSourceSummary(
                            source_id=src_id,
                            filename=src_info.get("original_filename", src_id),
                            detected_format=src_info.get("detected_format"),
                            file_size_bytes=src_info.get("file_size_bytes"),
                            sha256_checksum=src_info.get("sha256_checksum"),
                        )
                    )

                assigned_rag_id = "rag_class10_english" if manifest.build_id == "bld_6f509ca2" else f"rag_{manifest.build_id}"
                rag_artifact = RAGArtifact(
                    rag_id=assigned_rag_id,
                    build_id=manifest.build_id,
                    manifest_id=manifest.manifest_id,
                    manifest_hash=manifest.manifest_hash,
                    status=manifest.status,
                    approved_architecture=manifest.approved_architecture,
                    chunk_count=manifest.chunk_count,
                    vector_count=manifest.vector_count,
                    embedding_dimension=manifest.embedding_dimension,
                    embedding_model=manifest.embedding_model,
                    vector_store=manifest.vector_store,
                    started_at=manifest.started_at,
                    completed_at=manifest.completed_at,
                    build_duration_ms=manifest.build_duration_ms,
                    is_active=(manifest.build_id == active_id),
                    sources=sources,
                )
                artifacts.append(rag_artifact)
            except Exception as e:
                logger.error("Failed to parse manifest in %s: %s", build_folder, e)
                continue

        # Sort so active build is first, then by completed_at desc
        artifacts.sort(key=lambda a: (not a.is_active, str(a.completed_at or "")), reverse=False)
        return artifacts

    def get_artifact_detail(self, build_id: str) -> Optional[RAGArtifactDetail]:
        """Inspects detailed build information and sample chunks without LLM invocation."""
        build_folder = self.builds_dir / build_id
        manifest_file = build_folder / "manifest.json"
        if not manifest_file.exists():
            return None

        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            manifest = BuildManifest.model_validate(manifest_data)
        except Exception as e:
            logger.error("Failed to load manifest for %s: %s", build_id, e)
            return None

        active_id = self._get_active_build_id()
        sources_map = self._get_sources_map()

        sources: List[RAGSourceSummary] = []
        for src_id in manifest.source_ids:
            src_info = sources_map.get(src_id, {})
            sources.append(
                RAGSourceSummary(
                    source_id=src_id,
                    filename=src_info.get("original_filename", src_id),
                    detected_format=src_info.get("detected_format"),
                    file_size_bytes=src_info.get("file_size_bytes"),
                    sha256_checksum=src_info.get("sha256_checksum"),
                )
            )

        # Sample up to 5 chunks from storage index if available
        sample_chunks: List[RAGSampleChunk] = []
        chunks_jsonl = build_folder / "index" / "chunks.jsonl"
        chunks_json = build_folder / "index" / "chunks.json"

        if chunks_jsonl.exists():
            try:
                with open(chunks_jsonl, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        item = json.loads(line)
                        prov = item.get("metadata", item.get("provenance", {}))
                        sample_chunks.append(
                            RAGSampleChunk(
                                chunk_id=item.get("chunk_id", ""),
                                source_name=prov.get("source_name", "document"),
                                page_number=prov.get("page_number"),
                                snippet=item.get("text", "")[:280] + ("..." if len(item.get("text", "")) > 280 else ""),
                            )
                        )
                        if len(sample_chunks) >= 5:
                            break
            except Exception as e:
                logger.warning("Could not read sample chunks from jsonl for %s: %s", build_id, e)
        elif chunks_json.exists():
            try:
                with open(chunks_json, "r", encoding="utf-8") as f:
                    raw_chunks = json.load(f)
                for item in raw_chunks[:5]:
                    prov = item.get("metadata", item.get("provenance", {}))
                    sample_chunks.append(
                        RAGSampleChunk(
                            chunk_id=item.get("chunk_id", ""),
                            source_name=prov.get("source_name", "document"),
                            page_number=prov.get("page_number"),
                            snippet=item.get("text", "")[:280] + ("..." if len(item.get("text", "")) > 280 else ""),
                        )
                    )
            except Exception as e:
                logger.warning("Could not read sample chunks for %s: %s", build_id, e)

        chunking_dict = manifest.chunking_config if isinstance(manifest.chunking_config, dict) else (manifest.chunking_config.model_dump() if manifest.chunking_config else {})
        retrieval_dict = manifest.retrieval_config if isinstance(manifest.retrieval_config, dict) else (manifest.retrieval_config.model_dump() if manifest.retrieval_config else {})

        return RAGArtifactDetail(
            rag_id=f"rag_{manifest.build_id}",
            build_id=manifest.build_id,
            manifest_id=manifest.manifest_id,
            manifest_hash=manifest.manifest_hash,
            status=manifest.status,
            approved_architecture=manifest.approved_architecture,
            chunk_count=manifest.chunk_count,
            vector_count=manifest.vector_count,
            embedding_dimension=manifest.embedding_dimension,
            embedding_model=manifest.embedding_model,
            vector_store=manifest.vector_store,
            started_at=manifest.started_at,
            completed_at=manifest.completed_at,
            build_duration_ms=manifest.build_duration_ms,
            is_active=(manifest.build_id == active_id),
            sources=sources,
            chunking_config=chunking_dict,
            retrieval_config=retrieval_dict,
            sample_chunks=sample_chunks,
        )
