"""Analyzer Service for Phase 3.

Orchestrates structural fact extraction, semantic observation provider execution,
persistent disk storage of file profiles, and deterministic workspace synthesis.
"""

import json
import os
from pathlib import Path
import threading
from typing import Dict, List, Optional, Union

from ragger_engine.analyzer.exceptions import SourceNotIngestedError
from ragger_engine.analyzer.models import (
    FileAnalysisProfile,
    WorkspaceKnowledgeProfile,
)
from ragger_engine.analyzer.providers import (
    BaseAnalyzerProvider,
    DeterministicHeuristicAnalyzer,
    OllamaAnalyzerProvider,
    OpenAICompatibleProvider,
)
from ragger_engine.analyzer.structural import StructuralFactExtractor
from ragger_engine.ingestion.registry import SourceRegistry, get_default_storage_dir
from ragger_engine.ingestion.service import IngestionService


class AnalyzerService:
    """Manages knowledge analysis of ingested files and workspace synthesis."""

    def __init__(
        self,
        ingestion_service: IngestionService,
        storage_dir: Optional[Union[str, Path]] = None,
        default_provider: str = "heuristic_offline",
    ):
        self.ingestion_service = ingestion_service
        self.registry = ingestion_service.registry
        self.storage_dir = Path(storage_dir) if storage_dir else get_default_storage_dir()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_file = self.storage_dir / "analysis_profiles.json"
        self.workspace_file = self.storage_dir / "workspace_profile.json"
        self._lock = threading.RLock()

        # Providers registry
        self.providers: Dict[str, BaseAnalyzerProvider] = {
            "heuristic_offline": DeterministicHeuristicAnalyzer(),
            "ollama": OllamaAnalyzerProvider(),
            "openai_compatible": OpenAICompatibleProvider(),
        }
        self.default_provider = default_provider
        self._profiles: Dict[str, FileAnalysisProfile] = {}
        self._workspace_profile: Optional[WorkspaceKnowledgeProfile] = None
        self._load_profiles()

    def _load_profiles(self) -> None:
        """Loads cached profiles from persistent disk storage."""
        with self._lock:
            if self.profiles_file.exists():
                try:
                    with open(self.profiles_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._profiles = {
                            k: FileAnalysisProfile.model_validate(v)
                            for k, v in data.items()
                        }
                except Exception:
                    self._profiles = {}

            if self.workspace_file.exists():
                try:
                    with open(self.workspace_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        self._workspace_profile = WorkspaceKnowledgeProfile.model_validate(data)
                except Exception:
                    self._workspace_profile = None

    def _save_profiles(self) -> None:
        """Atomically saves profiles to persistent disk storage."""
        with self._lock:
            temp_file = self.profiles_file.with_suffix(".tmp")
            data = {k: v.model_dump() for k, v in self._profiles.items()}
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.profiles_file)

    def _save_workspace_profile(self) -> None:
        """Atomically saves workspace profile to persistent disk storage."""
        with self._lock:
            if not self._workspace_profile:
                return
            temp_file = self.workspace_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._workspace_profile.model_dump(), f, indent=2)
            temp_file.replace(self.workspace_file)

    async def analyze_source(
        self,
        source_id: str,
        provider_name: Optional[str] = None,
    ) -> FileAnalysisProfile:
        """Runs observational analysis on an ingested source and saves FileAnalysisProfile."""
        source = self.registry.get_source(source_id)
        if not source:
            raise SourceNotIngestedError(source_id)

        # Retrieve normalized model and sample
        normalized_model = self.ingestion_service.get_normalized_model(source_id)
        sample = self.ingestion_service.get_sample(source_id)
        if not sample:
            raise SourceNotIngestedError(f"No sample available for source '{source_id}'")

        # 1. Authoritative structural facts from Phase 2
        facts = StructuralFactExtractor.extract_facts(source, normalized_model or {})

        # 2. Select provider
        target_provider_id = provider_name or self.default_provider
        provider = self.providers.get(target_provider_id, self.providers["heuristic_offline"])

        # 3. Execute observation
        observations, telemetry = await provider.analyze(source, facts, sample)

        # 4. Construct FileAnalysisProfile
        profile = FileAnalysisProfile(
            source_id=source_id,
            original_filename=source.original_filename,
            structural_facts=facts,
            semantic_observations=observations,
            telemetry=telemetry,
        )

        with self._lock:
            self._profiles[source_id] = profile
            self._save_profiles()

        return profile

    def synthesize_workspace(self, workspace_id: str = "default") -> WorkspaceKnowledgeProfile:
        """Deterministically synthesizes all analyzed files into a WorkspaceKnowledgeProfile.
        
        CRITICAL ARCHITECTURAL RULE:
        Synthesis is 100% deterministic Python logic. It does NOT call an LLM.
        """
        with self._lock:
            profiles = list(self._profiles.values())
            total_sources = len(profiles)

            if total_sources == 0:
                profile = WorkspaceKnowledgeProfile(
                    workspace_id=workspace_id,
                    total_sources=0,
                    is_homogeneous=True,
                    modality_distribution={},
                    dominant_modality="unknown",
                    cross_source_entity_overlap=[],
                    overall_domain="general",
                    file_profiles={},
                )
                self._workspace_profile = profile
                self._save_workspace_profile()
                return profile

            # 1. Modality distribution
            modality_counts: Dict[str, int] = {}
            for p in profiles:
                mod = p.semantic_observations.primary_modality.value
                modality_counts[mod] = modality_counts.get(mod, 0) + 1

            modality_dist = {
                k: round(v / total_sources, 4) for k, v in modality_counts.items()
            }
            dominant_modality = max(modality_counts.items(), key=lambda x: x[1])[0]
            is_homogeneous = len(modality_counts) == 1

            # 2. Domain distribution
            domain_counts: Dict[str, int] = {}
            for p in profiles:
                d = p.semantic_observations.detected_domain
                domain_counts[d] = domain_counts.get(d, 0) + 1
            overall_domain = max(domain_counts.items(), key=lambda x: x[1])[0]

            # 3. Deterministic cross-source entity overlap (conservative set intersection)
            overlap_entities: List[str] = []
            if total_sources >= 2:
                all_entity_sets = [
                    {e.lower().strip() for e in p.semantic_observations.key_entities if len(e.strip()) > 2}
                    for p in profiles
                ]
                # Find entities appearing in at least 2 distinct files
                entity_freq: Dict[str, int] = {}
                canonical_names: Dict[str, str] = {}
                for p in profiles:
                    for e in p.semantic_observations.key_entities:
                        norm = e.lower().strip()
                        if len(norm) > 2:
                            canonical_names[norm] = e
                            entity_freq[norm] = entity_freq.get(norm, 0) + 1

                overlap_entities = [
                    canonical_names[norm]
                    for norm, count in entity_freq.items()
                    if count >= 2
                ]

            workspace_profile = WorkspaceKnowledgeProfile(
                workspace_id=workspace_id,
                total_sources=total_sources,
                is_homogeneous=is_homogeneous,
                modality_distribution=modality_dist,
                dominant_modality=dominant_modality,
                cross_source_entity_overlap=sorted(overlap_entities),
                overall_domain=overall_domain,
                file_profiles=dict(self._profiles),
            )

            self._workspace_profile = workspace_profile
            self._save_workspace_profile()
            return workspace_profile

    def get_profile(self, source_id: str) -> Optional[FileAnalysisProfile]:
        with self._lock:
            return self._profiles.get(source_id)

    def list_profiles(self) -> List[FileAnalysisProfile]:
        with self._lock:
            return list(self._profiles.values())

    def get_workspace_profile(self) -> Optional[WorkspaceKnowledgeProfile]:
        with self._lock:
            return self._workspace_profile
