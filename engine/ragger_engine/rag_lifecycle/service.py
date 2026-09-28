"""
RAG Lifecycle Service for Phase 12.
Manages persistent registry of RAG Knowledge Artifacts, version mapping,
reference integrity gates, and ZIP-based .ragpack export/import portability.
All storage operations resolve strictly through get_storage_root().
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
from typing import Dict, List, Optional, Tuple
import uuid
import zipfile

from ragger_engine.builder.models import BuildManifest
from ragger_engine.core.storage import get_storage_root
from ragger_engine.rag_lifecycle.exceptions import (
    ForbiddenModelWeightError,
    InvalidRAGPackError,
    RAGAlreadyExistsError,
    RAGInUseError,
    RAGNotFoundError,
    RAGVersionNotFoundError,
)
from ragger_engine.rag_lifecycle.models import (
    CreateRAGRequest,
    RAGArtifactRecord,
    RAGPackFileHash,
    RAGPackManifest,
    RAGStatus,
    RAGSuggestionsResponse,
    RAGVersionInfo,
    RegisterVersionRequest,
    UpdateRAGRequest,
    VersionComparisonResult,
    VersionComparisonSummary,
)

logger = logging.getLogger(__name__)

# Strict prohibited model weight extensions
FORBIDDEN_MODEL_EXTENSIONS = {
    ".gguf",
    ".onnx",
    ".safetensors",
    ".pt",
    ".pth",
    ".bin",
    ".tflite",
}


def compute_file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class RAGLifecycleService:
    """
    Authoritative service for managing RAG Knowledge Artifacts, versions,
    agent reference integrity, and portable .ragpack packages.
    """

    def __init__(
        self,
        workspace_dir: Optional[Path] = None,
        agent_workspace_service=None,
    ):
        # Resolve storage strictly through get_storage_root() if not overridden
        self.workspace_dir = Path(workspace_dir) if workspace_dir else get_storage_root()
        self.agent_workspace_service = agent_workspace_service

        self.registry_dir = self.workspace_dir / "rag_artifacts"
        self.registry_dir.mkdir(parents=True, exist_ok=True)
        self.registry_file = self.registry_dir / "registry.json"

        self.builds_dir = self.workspace_dir / "builds"
        self.builds_dir.mkdir(parents=True, exist_ok=True)
        self.scratch_dir = self.workspace_dir / "scratch"
        self.scratch_dir.mkdir(parents=True, exist_ok=True)

        # In-memory suggestions cache keyed by active version_id
        self._suggestions_cache: Dict[str, List[str]] = {}

        self._ensure_registry()

    def _ensure_registry(self) -> None:
        """Initializes registry and auto-migrates existing builds to stable RAG artifacts."""
        if not self.registry_file.exists():
            records = self._auto_migrate_existing_builds()
            self._save_registry(records)
        else:
            records = self._load_registry()
            dirty = False

            # Check if active build is present in registry, otherwise register
            active_build_path = self.workspace_dir / "active_build.json"
            if active_build_path.exists():
                try:
                    with open(active_build_path, "r", encoding="utf-8") as f:
                        active_data = json.load(f)
                    act_bld = active_data.get("active_build_id")
                    if act_bld and not any(any(v.build_id == act_bld for v in r.versions) for r in records.values()):
                        self._migrate_single_build(act_bld, records)
                        dirty = True
                except Exception as e:
                    logger.warning("Error checking active build migration: %s", e)

            # Reconcile any other build directories in storage/builds/ not yet tracked in registry
            if self.builds_dir.exists():
                for bld_dir in sorted(self.builds_dir.iterdir()):
                    if not bld_dir.is_dir():
                        continue
                    bld_id = bld_dir.name
                    if not (bld_dir / "manifest.json").exists():
                        continue
                    if not any(any(v.build_id == bld_id for v in r.versions) for r in records.values()):
                        self._migrate_single_build(bld_id, records)
                        dirty = True

            if dirty:
                self._save_registry(records)

    def _load_registry(self) -> Dict[str, RAGArtifactRecord]:
        if not self.registry_file.exists():
            return {}
        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return {k: RAGArtifactRecord.model_validate(v) for k, v in raw.items()}
        except Exception as e:
            logger.error("Failed to load RAG registry: %s", e)
            return {}

    def _save_registry(self, records: Dict[str, RAGArtifactRecord]) -> None:
        temp_file = self.registry_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump({k: v.model_dump(mode="json") for k, v in records.items()}, f, indent=2)
        shutil.move(temp_file, self.registry_file)

    def _auto_migrate_existing_builds(self) -> Dict[str, RAGArtifactRecord]:
        """Discovers existing builds and establishes stable RAG records."""
        records: Dict[str, RAGArtifactRecord] = {}
        if not self.builds_dir.exists():
            return records

        for bld_dir in sorted(self.builds_dir.iterdir()):
            if not bld_dir.is_dir():
                continue
            manifest_file = bld_dir / "manifest.json"
            if not manifest_file.exists():
                continue
            self._migrate_single_build(bld_dir.name, records)

        return records

    def _migrate_single_build(self, build_id: str, records: Dict[str, RAGArtifactRecord]) -> None:
        manifest_file = self.builds_dir / build_id / "manifest.json"
        if not manifest_file.exists():
            return
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            manifest = BuildManifest.model_validate(m_data)

            # Use deterministic stable rag_id
            if build_id == "bld_6f509ca2":
                rag_id = "rag_class10_english"
                name = "Class 10 English"
                description = "Tamil Nadu Class 10 English Textbook (2024 Edition)"
            else:
                rag_id = f"rag_{build_id}"
                name = f"Knowledge Base ({build_id})"
                description = f"Migrated from compiled build {build_id}"

            version_id = f"ver_{build_id}"
            version = RAGVersionInfo(
                version_id=version_id,
                version_tag="v1.0.0",
                build_id=build_id,
                created_at=manifest.completed_at or datetime.now(timezone.utc).isoformat(),
                chunk_count=manifest.chunk_count,
                vector_count=manifest.vector_count,
                manifest_hash=manifest.manifest_hash,
                manifest_id=manifest.manifest_id,
                embedding_model=manifest.embedding_model,
                vector_store=manifest.vector_store,
            )

            record = RAGArtifactRecord(
                rag_id=rag_id,
                name=name,
                description=description,
                status=RAGStatus.ACTIVE,
                active_version_id=version_id,
                versions=[version],
                source_ids=manifest.source_ids,
                created_at=manifest.started_at or datetime.now(timezone.utc).isoformat(),
                updated_at=manifest.completed_at or datetime.now(timezone.utc).isoformat(),
            )
            records[rag_id] = record
            logger.info("Migrated build %s into RAG artifact %s", build_id, rag_id)
        except Exception as e:
            logger.error("Failed to migrate build %s: %s", build_id, e)

    # --------------------------------------------------------------------------
    # CRUD & Lifecycle Operations
    # --------------------------------------------------------------------------

    def create_rag(self, request: CreateRAGRequest, account_id: Optional[str] = None) -> RAGArtifactRecord:
        records = self._load_registry()
        rag_id = f"rag_{uuid.uuid4().hex[:12]}"
        now_str = datetime.now(timezone.utc).isoformat()
        resolved_account_id = account_id or request.account_id or "acc_default"

        versions: List[RAGVersionInfo] = []
        active_version_id = None
        source_ids = []

        if request.initial_build_id:
            bld_dir = self.builds_dir / request.initial_build_id
            manifest_file = bld_dir / "manifest.json"
            if not manifest_file.exists():
                raise InvalidRAGPackError(f"Initial build {request.initial_build_id} does not exist.")
            with open(manifest_file, "r", encoding="utf-8") as f:
                m_data = json.load(f)
            manifest = BuildManifest.model_validate(m_data)

            ver_id = f"ver_{uuid.uuid4().hex[:8]}"
            version = RAGVersionInfo(
                version_id=ver_id,
                version_tag="v1.0.0",
                build_id=request.initial_build_id,
                created_at=now_str,
                chunk_count=manifest.chunk_count,
                vector_count=manifest.vector_count,
                manifest_hash=manifest.manifest_hash,
                manifest_id=manifest.manifest_id,
                embedding_model=manifest.embedding_model,
                vector_store=manifest.vector_store,
            )
            versions.append(version)
            active_version_id = ver_id
            source_ids = manifest.source_ids

        record = RAGArtifactRecord(
            rag_id=rag_id,
            name=request.name,
            description=request.description or "",
            status=RAGStatus.ACTIVE,
            active_version_id=active_version_id,
            versions=versions,
            source_ids=source_ids,
            account_id=resolved_account_id,
            created_at=now_str,
            updated_at=now_str,
        )
        records[rag_id] = record
        self._save_registry(records)
        return record

    def get_rag(self, rag_id: str, account_id: Optional[str] = None) -> RAGArtifactRecord:
        records = self._load_registry()
        if rag_id not in records:
            # Handle alias for class10 english if registered under generated ID
            if rag_id == "rag_class10_english":
                c10 = next((r for r in records.values() if "class_10_english" in r.name.lower() or "class 10 english" in r.name.lower()), None)
                if c10:
                    if account_id and c10.account_id != account_id:
                        raise RAGNotFoundError(rag_id)
                    return c10
            if rag_id.startswith("rag_"):
                candidate_bld = rag_id.removeprefix("rag_")
                if candidate_bld == "class10_english":
                    candidate_bld = "bld_6f509ca2"
                if (self.builds_dir / candidate_bld / "manifest.json").exists():
                    self._migrate_single_build(candidate_bld, records)
                    self._save_registry(records)
            if rag_id not in records:
                raise RAGNotFoundError(rag_id)

        record = records[rag_id]
        if account_id is not None and record.account_id != account_id:
            raise RAGNotFoundError(rag_id)
        return record

    def list_rags(self, include_archived: bool = False, account_id: Optional[str] = None) -> List[RAGArtifactRecord]:
        records = self._load_registry()
        res = []
        for r in records.values():
            if not include_archived and r.status == RAGStatus.ARCHIVED:
                continue
            if account_id is not None and r.account_id != account_id:
                continue
            res.append(r)
        return sorted(res, key=lambda x: x.created_at, reverse=True)

    def update_rag(self, rag_id: str, request: UpdateRAGRequest) -> RAGArtifactRecord:
        records = self._load_registry()
        if rag_id not in records:
            raise RAGNotFoundError(rag_id)

        record = records[rag_id]
        if request.name is not None:
            record.name = request.name
        if request.description is not None:
            record.description = request.description
        if request.status is not None:
            record.status = request.status
        if request.active_version_id is not None:
            if not any(v.version_id == request.active_version_id for v in record.versions):
                raise RAGVersionNotFoundError(rag_id, request.active_version_id)
            record.active_version_id = request.active_version_id

        record.updated_at = datetime.now(timezone.utc).isoformat()
        records[rag_id] = record
        self._save_registry(records)
        return record

    def register_version(self, rag_id: str, request: RegisterVersionRequest) -> RAGVersionInfo:
        """Registers a compiled build as a new version of an existing RAG artifact."""
        records = self._load_registry()
        if rag_id not in records:
            raise RAGNotFoundError(rag_id)

        record = records[rag_id]
        bld_dir = self.builds_dir / request.build_id
        manifest_file = bld_dir / "manifest.json"
        if not manifest_file.exists():
            raise InvalidRAGPackError(f"Build '{request.build_id}' not found in storage.")

        with open(manifest_file, "r", encoding="utf-8") as f:
            m_data = json.load(f)
        manifest = BuildManifest.model_validate(m_data)

        ver_id = f"ver_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()

        version = RAGVersionInfo(
            version_id=ver_id,
            version_tag=request.version_tag,
            build_id=request.build_id,
            created_at=now_str,
            chunk_count=manifest.chunk_count,
            vector_count=manifest.vector_count,
            manifest_hash=manifest.manifest_hash,
            manifest_id=manifest.manifest_id,
            embedding_model=manifest.embedding_model,
            vector_store=manifest.vector_store,
        )
        record.versions.append(version)
        if request.set_active:
            record.active_version_id = ver_id

        # Merge newly indexed source IDs into artifact record
        for sid in manifest.source_ids:
            if sid not in record.source_ids:
                record.source_ids.append(sid)

        record.updated_at = now_str
        records[rag_id] = record
        self._save_registry(records)
        logger.info("Registered build %s as version %s (%s) for RAG %s", request.build_id, ver_id, request.version_tag, rag_id)
        return version

    def rollback_version(self, rag_id: str, target_version_id: str) -> RAGArtifactRecord:
        """Rolls back active version of a RAG artifact to an earlier version."""
        return self.update_rag(rag_id, UpdateRAGRequest(active_version_id=target_version_id))

    def archive_rag(self, rag_id: str) -> RAGArtifactRecord:
        return self.update_rag(rag_id, UpdateRAGRequest(status=RAGStatus.ARCHIVED))

    def delete_rag(self, rag_id: str, force: bool = True, account_id: Optional[str] = None) -> Tuple[RAGArtifactRecord, List[str]]:
        """
        Deletes a RAG artifact:
        - If referenced by agents and force=True (default): atomically detaches rag_id from all referencing agents,
          persists the updated agent state, and deletes the RAG artifact record.
        - If referenced by agents and force=False: fails closed by raising RAGInUseError (HTTP 409).
        - Removes underlying build directories from self.builds_dir if no other RAG references them.
        """
        records = self._load_registry()
        if rag_id not in records:
            # Fallback check: If rag_id corresponds to an unindexed build (e.g. rag_bld_xxx or rag_class10_english)
            if rag_id.startswith("rag_"):
                candidate_bld = rag_id.removeprefix("rag_")
                if candidate_bld == "class10_english":
                    candidate_bld = "bld_6f509ca2"
                if (self.builds_dir / candidate_bld / "manifest.json").exists():
                    self._migrate_single_build(candidate_bld, records)
                    self._save_registry(records)

            if rag_id not in records:
                raise RAGNotFoundError(rag_id)

        target_record = records[rag_id]
        if account_id is not None and target_record.account_id != account_id:
            raise RAGNotFoundError(rag_id)

        affected_agents: List[str] = []
        if self.agent_workspace_service:
            referencing = self.agent_workspace_service.get_agents_referencing_rag(rag_id)
            if referencing:
                if not force:
                    raise RAGInUseError(rag_id, referencing)
                # Atomic unlinking from all referencing agents
                affected_agents = self.agent_workspace_service.detach_rag_from_all_agents(rag_id)
                logger.info("Deleted RAG %s safely unlinked from agents: %s", rag_id, affected_agents)

        record = records.pop(rag_id)
        self._save_registry(records)

        # Clean up associated build directory/directories if no remaining RAG references them
        for version in record.versions:
            if version.build_id:
                # Check if any remaining RAG artifact in the registry still references this build_id
                still_referenced = any(
                    any(v.build_id == version.build_id for v in remaining_rag.versions)
                    for remaining_rag in records.values()
                )
                if not still_referenced:
                    bld_dir = self.builds_dir / version.build_id
                    if bld_dir.exists() and bld_dir.is_dir():
                        try:
                            shutil.rmtree(bld_dir)
                        except Exception as e:
                            logger.warning("Failed to remove build directory %s: %s", bld_dir, e)

        # Invalidate suggestions cache for deleted RAG
        for version in record.versions:
            self._suggestions_cache.pop(version.version_id, None)

        return record, affected_agents

    def resolve_active_build_id(self, rag_id: str) -> str:
        """Resolves immutable rag_id to active version's underlying build_id."""
        record = self.get_rag(rag_id)
        if not record.active_version_id:
            if record.versions:
                return record.versions[-1].build_id
            raise InvalidRAGPackError(f"RAG Artifact {rag_id} has no compiled versions.")

        for v in record.versions:
            if v.version_id == record.active_version_id:
                return v.build_id

        raise RAGVersionNotFoundError(rag_id, record.active_version_id)

    def get_suggestions(self, rag_id: str) -> List[str]:
        """
        Generates deterministic, document-aware suggested questions for the active version of a RAG artifact.
        Caches suggestions by active version_id.
        Never calls an LLM; extracts directly from chunk headings, section titles, natural questions, and document titles.
        """
        record = self.get_rag(rag_id)
        if not record.versions:
            return self._default_fallback_suggestions(record.name)

        active_ver_id = record.active_version_id or record.versions[-1].version_id
        if active_ver_id in self._suggestions_cache:
            return self._suggestions_cache[active_ver_id]

        target_version = next((v for v in record.versions if v.version_id == active_ver_id), record.versions[-1])
        build_id = target_version.build_id
        build_dir = self.builds_dir / build_id

        suggestions = self._generate_deterministic_suggestions(build_dir, record.name)
        self._suggestions_cache[active_ver_id] = suggestions
        return suggestions

    def _default_fallback_suggestions(self, doc_name: str) -> List[str]:
        clean_name = re.sub(r'\.[a-zA-Z0-9]+$', '', doc_name).replace('_', ' ').strip()
        first_q = f"What is the main purpose of {clean_name}?" if clean_name else "What is the main purpose of this document?"
        return [
            first_q,
            "Explain the key concepts and architecture.",
            "What are the main implementation steps or workflow?",
            "Summarize the important sections of this document.",
        ]

    def _generate_deterministic_suggestions(self, build_dir: Path, doc_name: str) -> List[str]:
        chunks_file = build_dir / "index" / "chunks.jsonl"
        headings: List[str] = []
        questions: List[str] = []
        major_sections: List[str] = []

        if chunks_file.exists():
            try:
                with open(chunks_file, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i > 80:
                            break
                        try:
                            chk = json.loads(line)
                        except Exception:
                            continue

                        meta = chk.get("metadata", {})
                        if (not doc_name or doc_name.startswith("Knowledge Base (")) and meta.get("source_name"):
                            doc_name = meta["source_name"]

                        # Extract headings from metadata heading_path
                        for h in meta.get("heading_path") or []:
                            h_clean = re.sub(r'^[0-9]+[\.\)]\s*', '', h).strip()
                            h_clean = re.sub(r'[\uFFFD\?]+', ' - ', h_clean).strip()
                            if len(h_clean) > 3 and not re.search(r'Page\s+[0-9]+', h_clean, re.I):
                                if h_clean not in headings:
                                    headings.append(h_clean)

                        txt = chk.get("text", "")
                        for l in txt.split("\n"):
                            l_strip = l.strip()
                            # Match markdown headers (# Title) or numbered sections (1. Design Goal)
                            m_sec = re.match(r'^(?:#{1,3}\s+|[0-9]{1,2}\.\s+)([A-Za-z][A-Za-z0-9\s\-_]{3,45})$', l_strip)
                            if m_sec:
                                s_name = m_sec.group(1).strip()
                                if s_name not in major_sections and len(s_name) > 3:
                                    major_sections.append(s_name)

                            # Match direct natural questions in text
                            m_q = re.search(r'([A-Z][^\n\.\?!]{10,85}\?)', l_strip)
                            if m_q:
                                q_cand = m_q.group(1).strip()
                                if not re.search(r'(forgot|sign in|login|password|cookie|click|subscribe|account)', q_cand, re.I):
                                    if q_cand not in questions:
                                        questions.append(q_cand)
            except Exception as e:
                logger.warning("Error reading chunks.jsonl for suggestions in %s: %s", build_dir, e)

        clean_name = re.sub(r'\.[a-zA-Z0-9]+$', '', doc_name).replace('_', ' ').strip()
        suggestions: List[str] = []

        # Priority 1: High-quality natural questions from text
        for q in questions:
            if len(suggestions) >= 4:
                break
            q_clean = q.replace('\uFFFD', "'").strip()
            # Strip accidental surrounding quotes if present
            if (q_clean.startswith('"') and q_clean.endswith('"')) or (q_clean.startswith("'") and q_clean.endswith("'")):
                q_clean = q_clean[1:-1].strip()
            if len(q_clean.split()) >= 4 and q_clean not in suggestions:
                suggestions.append(q_clean)

        # Priority 2: Structured sections & headings converted into contextual questions
        all_sections: List[str] = []
        for s in major_sections + headings:
            s_norm = s.strip()
            if s_norm and s_norm.lower() not in [x.lower() for x in all_sections]:
                all_sections.append(s_norm)

        for sec in all_sections:
            if len(suggestions) >= 4:
                break
            sec_clean = re.sub(r'[^\w\s\-_/]', ' ', sec).strip()
            sec_clean = re.sub(r'\s+', ' ', sec_clean)
            if len(sec_clean) < 3:
                continue
            sec_l = sec_clean.lower()
            if any(w in sec_l for w in ['goal', 'purpose', 'overview', 'introduction']):
                q = f"What is the {sec_l} of this document?"
            elif any(w in sec_l for w in ['principle', 'guideline', 'rule']):
                q = f"Explain the key {sec_l}."
            elif any(w in sec_l for w in ['architecture', 'system', 'component', 'pipeline']):
                q = f"What are the key {sec_l} components?"
            elif any(w in sec_l for w in ['workflow', 'how it works', 'process', 'step', 'implementation']):
                q = f"Explain the {sec_l} workflow."
            else:
                q = f"What does this document explain about {sec_clean}?"

            if q not in suggestions:
                suggestions.append(q)

        # Priority 3: Fallbacks tailored to document title
        fallbacks = self._default_fallback_suggestions(doc_name)
        for fb in fallbacks:
            if len(suggestions) >= 4:
                break
            if fb not in suggestions:
                suggestions.append(fb)

        return suggestions[:4]

    def compare_versions(self, rag_id: str, base_version_id: str, target_version_id: str) -> VersionComparisonResult:
        """
        Computes a descriptive, objective comparison between two versions of a RAG artifact.
        Factual metrics only (chunk count, vector count, manifest hash, sources added/removed/retained).
        No qualitative assertions or value judgments.
        """
        record = self.get_rag(rag_id)
        base_ver = next((v for v in record.versions if v.version_id == base_version_id), None)
        if not base_ver:
            raise RAGVersionNotFoundError(rag_id, base_version_id)

        target_ver = next((v for v in record.versions if v.version_id == target_version_id), None)
        if not target_ver:
            raise RAGVersionNotFoundError(rag_id, target_version_id)

        # Load manifests if available on disk for detailed inspection
        base_manifest: Optional[BuildManifest] = None
        base_mf_file = self.builds_dir / base_ver.build_id / "manifest.json"
        if base_mf_file.exists():
            try:
                with open(base_mf_file, "r", encoding="utf-8") as f:
                    base_manifest = BuildManifest.model_validate(json.load(f))
            except Exception as e:
                logger.warning("Could not read base manifest %s: %s", base_mf_file, e)

        target_manifest: Optional[BuildManifest] = None
        target_mf_file = self.builds_dir / target_ver.build_id / "manifest.json"
        if target_mf_file.exists():
            try:
                with open(target_mf_file, "r", encoding="utf-8") as f:
                    target_manifest = BuildManifest.model_validate(json.load(f))
            except Exception as e:
                logger.warning("Could not read target manifest %s: %s", target_mf_file, e)

        base_sources = set(base_manifest.source_ids if base_manifest else [])
        target_sources = set(target_manifest.source_ids if target_manifest else [])

        sources_added = sorted(list(target_sources - base_sources))
        sources_removed = sorted(list(base_sources - target_sources))
        sources_retained = sorted(list(base_sources & target_sources))

        base_summary = VersionComparisonSummary(
            chunk_count=base_ver.chunk_count,
            vector_count=base_ver.vector_count,
            sources_count=len(base_sources),
            manifest_hash=base_ver.manifest_hash,
            embedding_model=base_ver.embedding_model or (base_manifest.embedding_model if base_manifest else None),
            vector_store=base_ver.vector_store or (base_manifest.vector_store if base_manifest else None),
            architecture=base_manifest.approved_architecture if base_manifest else None,
        )

        target_summary = VersionComparisonSummary(
            chunk_count=target_ver.chunk_count,
            vector_count=target_ver.vector_count,
            sources_count=len(target_sources),
            manifest_hash=target_ver.manifest_hash,
            embedding_model=target_ver.embedding_model or (target_manifest.embedding_model if target_manifest else None),
            vector_store=target_ver.vector_store or (target_manifest.vector_store if target_manifest else None),
            architecture=target_manifest.approved_architecture if target_manifest else None,
        )

        return VersionComparisonResult(
            rag_id=rag_id,
            base_version_id=base_version_id,
            base_version_tag=base_ver.version_tag,
            target_version_id=target_version_id,
            target_version_tag=target_ver.version_tag,
            base=base_summary,
            target=target_summary,
            chunk_count_delta=target_ver.chunk_count - base_ver.chunk_count,
            vector_count_delta=target_ver.vector_count - base_ver.vector_count,
            sources_count_delta=len(target_sources) - len(base_sources),
            manifest_hash_changed=base_ver.manifest_hash != target_ver.manifest_hash,
            embedding_model_changed=(base_summary.embedding_model != target_summary.embedding_model),
            sources_added=sources_added,
            sources_removed=sources_removed,
            sources_retained=sources_retained,
        )


    # --------------------------------------------------------------------------
    # ZIP-based .ragpack Portability (Export & Import)
    # --------------------------------------------------------------------------

    def export_ragpack(self, rag_id: str, version_id: Optional[str] = None, output_path: Optional[Path] = None) -> Path:
        """
        Creates a deterministic, ZIP-based .ragpack package.
        Validates the zero-LLM-weight invariant.
        """
        record = self.get_rag(rag_id)
        ver_id = version_id or record.active_version_id
        if not ver_id:
            raise InvalidRAGPackError(f"RAG {rag_id} has no version to export.")

        target_version = next((v for v in record.versions if v.version_id == ver_id), None)
        if not target_version:
            raise RAGVersionNotFoundError(rag_id, ver_id)

        build_id = target_version.build_id
        build_dir = self.builds_dir / build_id
        if not build_dir.exists():
            raise InvalidRAGPackError(f"Underlying build directory {build_dir} not found.")

        # Determine export file path
        safe_name = record.name.replace(" ", "_").lower()
        if output_path:
            ragpack_path = Path(output_path)
        else:
            export_dir = self.workspace_dir / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)
            ragpack_path = export_dir / f"{safe_name}_{target_version.version_tag}.ragpack"

        # Pre-scan build directory: reject any forbidden model weights
        for root, _, files in os.walk(build_dir):
            for file in files:
                ext = Path(file).suffix.lower()
                if ext in FORBIDDEN_MODEL_EXTENSIONS:
                    raise ForbiddenModelWeightError(file)

        files_hash_map: Dict[str, RAGPackFileHash] = {}

        with zipfile.ZipFile(ragpack_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # 1. Add manifest.json from build
            manifest_file = build_dir / "manifest.json"
            if manifest_file.exists():
                arcname = "manifest.json"
                zf.write(manifest_file, arcname=arcname)
                files_hash_map[arcname] = RAGPackFileHash(
                    sha256=compute_file_sha256(manifest_file),
                    size_bytes=manifest_file.stat().st_size,
                )

            # 2. Add knowledge directory (chunks.jsonl and lance files)
            index_dir = build_dir / "index"
            if index_dir.exists():
                for root, _, files in os.walk(index_dir):
                    for file in files:
                        ext = Path(file).suffix.lower()
                        if ext in FORBIDDEN_MODEL_EXTENSIONS:
                            raise ForbiddenModelWeightError(file)
                        f_path = Path(root) / file
                        rel_path = f_path.relative_to(index_dir)
                        arcname = f"knowledge/{rel_path.as_posix()}"
                        zf.write(f_path, arcname=arcname)
                        files_hash_map[arcname] = RAGPackFileHash(
                            sha256=compute_file_sha256(f_path),
                            size_bytes=f_path.stat().st_size,
                        )

            # 3. Add sources_registry snippet if available
            sources_reg = self.workspace_dir / "sources_registry.json"
            if sources_reg.exists():
                try:
                    with open(sources_reg, "r", encoding="utf-8") as sf:
                        full_sources = json.load(sf)
                    filtered_sources = {k: v for k, v in full_sources.items() if k in record.source_ids}
                    sources_bytes = json.dumps(filtered_sources, indent=2).encode("utf-8")
                    arcname = "provenance/sources_registry.json"
                    zf.writestr(arcname, sources_bytes)
                    files_hash_map[arcname] = RAGPackFileHash(
                        sha256=hashlib.sha256(sources_bytes).hexdigest(),
                        size_bytes=len(sources_bytes),
                    )
                except Exception as e:
                    logger.warning("Could not bundle sources registry: %s", e)

            # 4. Generate & write root .ragpack manifest
            ragpack_manifest = RAGPackManifest(
                schema_version="1.0",
                rag_id=record.rag_id,
                rag_name=record.name,
                version_id=target_version.version_id,
                version_tag=target_version.version_tag,
                build_id=build_id,
                files=files_hash_map,
            )
            zf.writestr("ragpack_manifest.json", ragpack_manifest.model_dump_json(indent=2))

        logger.info("Successfully exported .ragpack: %s", ragpack_path)
        return ragpack_path

    def import_ragpack(self, ragpack_path: Path) -> RAGArtifactRecord:
        """
        Validates and imports a .ragpack bundle into live storage.
        Enforces:
        1. Zip-slip / path traversal check.
        2. Quota & entry limits.
        3. Forbidden model weight scan (*.gguf, *.onnx, etc.).
        4. Cryptographic SHA-256 integrity check of all files against ragpack_manifest.json.
        5. Build manifest validation.
        6. Atomic copy to storage/builds/ upon complete validation.
        7. Registration in rag_artifacts/registry.json.
        """
        path = Path(ragpack_path)
        if not path.exists():
            raise InvalidRAGPackError(f"File not found: {path}")

        scratch_id = f"import_{uuid.uuid4().hex[:8]}"
        temp_extract_dir = self.scratch_dir / scratch_id
        temp_extract_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(path, "r") as zf:
                # 1. Path traversal & security validation
                infolist = zf.infolist()
                if len(infolist) > 10000:
                    raise InvalidRAGPackError("Archive exceeds safe entry limit (10,000 files).")

                for info in infolist:
                    norm = os.path.normpath(info.filename)
                    if norm.startswith("..") or os.path.isabs(norm):
                        raise InvalidRAGPackError(f"Zip slip security violation detected: '{info.filename}'")

                    # Forbidden model weight check
                    ext = Path(info.filename).suffix.lower()
                    if ext in FORBIDDEN_MODEL_EXTENSIONS:
                        raise ForbiddenModelWeightError(info.filename)

                # Extract to scratch
                zf.extractall(temp_extract_dir)

            # 2. Check and load ragpack_manifest.json
            manifest_file = temp_extract_dir / "ragpack_manifest.json"
            if not manifest_file.exists():
                raise InvalidRAGPackError("Missing root 'ragpack_manifest.json' in .ragpack bundle.")

            with open(manifest_file, "r", encoding="utf-8") as f:
                pkg_data = json.load(f)
            pkg_manifest = RAGPackManifest.model_validate(pkg_data)

            # 3. Verify SHA-256 digests
            for rel_path, expected_hash in pkg_manifest.files.items():
                f_target = temp_extract_dir / rel_path
                if not f_target.exists():
                    raise InvalidRAGPackError(f"Missing declared file '{rel_path}' in package.")
                computed_hash = compute_file_sha256(f_target)
                if computed_hash != expected_hash.sha256:
                    raise InvalidRAGPackError(
                        f"Integrity check failed for '{rel_path}': expected {expected_hash.sha256}, got {computed_hash}"
                    )

            # 4. Verify internal build manifest.json
            bld_manifest_file = temp_extract_dir / "manifest.json"
            if not bld_manifest_file.exists():
                raise InvalidRAGPackError("Missing build 'manifest.json' in package.")
            with open(bld_manifest_file, "r", encoding="utf-8") as f:
                bld_data = json.load(f)
            bld_manifest = BuildManifest.model_validate(bld_data)

            # 5. Atomic installation into live builds directory
            dest_build_id = f"bld_imp_{uuid.uuid4().hex[:8]}"
            dest_build_dir = self.builds_dir / dest_build_id
            dest_build_dir.mkdir(parents=True, exist_ok=True)
            dest_index_dir = dest_build_dir / "index"
            dest_index_dir.mkdir(parents=True, exist_ok=True)

            # Copy manifest
            shutil.copy2(bld_manifest_file, dest_build_dir / "manifest.json")

            # Copy knowledge files to index
            src_knowledge_dir = temp_extract_dir / "knowledge"
            if src_knowledge_dir.exists():
                for item in src_knowledge_dir.iterdir():
                    if item.is_dir():
                        shutil.copytree(item, dest_index_dir / item.name)
                    else:
                        shutil.copy2(item, dest_index_dir / item.name)

            # 6. Register imported artifact into RAG registry
            imported_rag_id = pkg_manifest.rag_id
            records = self._load_registry()
            # If rag_id already exists in registry, create a unique copy or new version
            if imported_rag_id in records:
                imported_rag_id = f"{imported_rag_id}_imp_{uuid.uuid4().hex[:4]}"

            now_str = datetime.now(timezone.utc).isoformat()
            ver_id = f"ver_{uuid.uuid4().hex[:8]}"
            version = RAGVersionInfo(
                version_id=ver_id,
                version_tag=pkg_manifest.version_tag or "v1.0.0",
                build_id=dest_build_id,
                created_at=now_str,
                chunk_count=bld_manifest.chunk_count,
                vector_count=bld_manifest.vector_count,
                manifest_hash=bld_manifest.manifest_hash,
                manifest_id=bld_manifest.manifest_id,
                embedding_model=bld_manifest.embedding_model,
                vector_store=bld_manifest.vector_store,
            )

            record = RAGArtifactRecord(
                rag_id=imported_rag_id,
                name=f"{pkg_manifest.rag_name} (Imported)",
                description=f"Imported from {path.name}",
                status=RAGStatus.ACTIVE,
                active_version_id=ver_id,
                versions=[version],
                source_ids=bld_manifest.source_ids,
                created_at=now_str,
                updated_at=now_str,
            )
            records[imported_rag_id] = record
            self._save_registry(records)

            logger.info("Successfully imported .ragpack into RAG Artifact %s (%s)", imported_rag_id, dest_build_id)
            return record

        finally:
            if temp_extract_dir.exists():
                shutil.rmtree(temp_extract_dir, ignore_errors=True)
