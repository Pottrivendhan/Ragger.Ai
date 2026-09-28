"""
Multi-RAG Resolution Coordinator for Phase 16.
Responsible for:
1. Strict server-authoritative resolution chain:
   rag_id -> active_version_id -> RAGVersion -> build_id -> BuildRuntimeCache[build_id]
   (verifying build manifest status == "completed").
2. Parallel retrieval dispatch across isolated BuildRuntimeCache instances.
3. Returning structured MultiRAGRetrievalResult (target + response) to eliminate provenance detachment.
4. Reciprocal Rank Fusion (RRF, k=60) and composite deduplication on (rag_id:build_id:chunk_id).
5. Controlled fail-closed behavior on missing or corrupt attached RAGs.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ragger_engine.agent_workspace.models import AgentProfile
from ragger_engine.agent_workspace.exceptions import (
    NoAttachedRAGError,
    RAGArtifactNotFoundError,
)
from ragger_engine.rag_lifecycle.exceptions import (
    RAGNotFoundError,
    RAGVersionNotFoundError,
    InvalidRAGPackError,
)
from ragger_engine.retrieval.exceptions import BuildUnavailableError, ManifestCorruptedError
from ragger_engine.retrieval.models import RetrievalQuery, RetrievalResponse
from ragger_engine.retrieval.service import RetrievalService
from ragger_engine.multi_rag.models import (
    ResolvedRAGTarget,
    MultiRAGClientTarget,
    MultiRAGCandidate,
    MultiRAGRetrievalResult,
    MultiRAGFusedContext,
)

logger = logging.getLogger(__name__)


class MultiRAGRetrievalError(Exception):
    """Raised when any single attached RAG fails to retrieve, enforcing fail-closed invariant."""
    def __init__(self, message: str, details: Optional[Dict] = None):
        super().__init__(message)
        self.code = "MULTI_RAG_RETRIEVAL_FAILED"
        self.details = details or {}


class MultiRAGCoordinator:
    """
    Coordinates multi-RAG resolution, parallel scoped retrieval, and candidate fusion.
    Enforces index isolation and strict composite provenance.
    """

    def __init__(
        self,
        retrieval_service: RetrievalService,
        rag_lifecycle_service=None,
        rag_library_service=None,
    ):
        self.retrieval_service = retrieval_service
        self.rag_lifecycle_service = rag_lifecycle_service
        self.rag_library_service = rag_library_service

    def resolve_agent_runtimes(self, agent: "AgentProfile") -> List[ResolvedRAGTarget]:
        """
        Enforces authoritative resolution chain for every attached RAG:
        RAG exists -> active_version_id -> RAGVersion -> build_id -> BuildRuntimeCache[build_id]
        
        Strict invariants:
        - RAGStatus.ACTIVE alone is NOT sufficient.
        - Must resolve to a valid active_version_id.
        - Version must map to a completed, valid build manifest.
        - Fails closed immediately if any attached RAG is invalid or corrupt.
        - De-duplicates attached_rag_ids preserving first appearance.
        """
        if not agent.attached_rag_ids:
            raise NoAttachedRAGError(agent.agent_id)

        # De-duplicate attached IDs while maintaining order
        seen_rags = set()
        unique_rag_ids = []
        for rid in agent.attached_rag_ids:
            if rid not in seen_rags:
                seen_rags.add(rid)
                unique_rag_ids.append(rid)

        resolved_targets: List[ResolvedRAGTarget] = []

        for rag_id in unique_rag_ids:
            resolved_target = self._resolve_single_rag(rag_id)
            resolved_targets.append(resolved_target)

        return resolved_targets

    def _resolve_single_rag(self, rag_id: str) -> ResolvedRAGTarget:
        """
        Resolves a single rag_id through the authoritative chain.
        """
        # 1. Check RAGLifecycleService first (Phase 12-15 authoritative registry)
        if self.rag_lifecycle_service:
            try:
                record = self.rag_lifecycle_service.get_rag(rag_id)
            except RAGNotFoundError:
                record = None

            if record:
                # Invariant: RAG must have active_version_id
                if not record.active_version_id:
                    raise InvalidRAGPackError(f"RAG '{rag_id}' has no active_version_id configured.")

                active_ver = None
                for v in record.versions:
                    if v.version_id == record.active_version_id:
                        active_ver = v
                        break

                if not active_ver:
                    raise RAGVersionNotFoundError(rag_id, record.active_version_id)

                build_id = active_ver.build_id
                # Verify build manifest exists, completed, and valid via retrieval_service
                self._verify_build_runtime(build_id)

                return ResolvedRAGTarget(
                    rag_id=record.rag_id,
                    rag_name=record.name,
                    version_id=active_ver.version_id,
                    version_tag=active_ver.version_tag,
                    build_id=build_id,
                )

        # 2. Check legacy / build aliases (e.g. rag_bld_6f509ca2 or direct build_id)
        if self.rag_library_service:
            artifacts = {a.rag_id: a for a in self.rag_library_service.list_artifacts()}
            for a in self.rag_library_service.list_artifacts():
                artifacts[f"rag_{a.build_id}"] = a
                artifacts[a.build_id] = a

            if rag_id in artifacts:
                art = artifacts[rag_id]
                self._verify_build_runtime(art.build_id)
                rag_name = getattr(art, "name", None) or art.rag_id
                return ResolvedRAGTarget(
                    rag_id=art.rag_id,
                    rag_name=rag_name,
                    version_id="ver_default",
                    version_tag="v1.0.0",
                    build_id=art.build_id,
                )

        # 3. Direct build fallback if prefixed with rag_ or raw build ID and build actually exists
        raw_build_id = rag_id[4:] if rag_id.startswith("rag_") else rag_id
        # If rag_lifecycle_service was provided and rag_id wasn't in it, and we don't have a verified build, fail
        builds_dir = getattr(self.retrieval_service, "workspace_dir", None)
        if builds_dir:
            build_manifest_path = Path(builds_dir) / "builds" / raw_build_id / "manifest.json"
            if not build_manifest_path.exists():
                raise RAGArtifactNotFoundError(rag_id)
        elif self.rag_lifecycle_service and not rag_id.startswith("bld_") and not rag_id.startswith("rag_bld_"):
            # If lifecycle service is configured, non-build IDs that failed lifecycle lookup must fail
            raise RAGArtifactNotFoundError(rag_id)

        try:
            self._verify_build_runtime(raw_build_id)
            return ResolvedRAGTarget(
                rag_id=rag_id,
                rag_name=rag_id,
                version_id="ver_default",
                version_tag="v1.0.0",
                build_id=raw_build_id,
            )
        except Exception:
            raise RAGArtifactNotFoundError(rag_id)


    def _verify_build_runtime(self, build_id: str) -> None:
        """
        Validates that build_id exists in BuildRuntimeCache and has completed status.
        Raises BuildUnavailableError or ManifestCorruptedError on failure.
        """
        runtime = self.retrieval_service.get_or_load_build_runtime(build_id, is_scoped_call=True)
        if runtime.manifest.status != "completed":
            raise BuildUnavailableError(
                build_id, f"Build '{build_id}' manifest status is '{runtime.manifest.status}', expected 'completed'."
            )

    async def parallel_retrieve(
        self,
        targets: List[ResolvedRAGTarget],
        query: str,
        top_k_per_rag: int = 5,
        filters: Optional[Dict] = None,
    ) -> List[MultiRAGRetrievalResult]:
        """
        Executes parallel scoped retrieval across all resolved targets.
        Strongly couples each RetrievalResponse with its ResolvedRAGTarget.
        
        Fail-closed invariant:
        If ANY single attached RAG retrieval fails, the entire operation fails closed.
        Zero silent degradation.
        """
        loop = asyncio.get_running_loop()

        def _retrieve_single(target: ResolvedRAGTarget) -> MultiRAGRetrievalResult:
            try:
                retrieval_req = RetrievalQuery(
                    query=query,
                    top_k=top_k_per_rag,
                    filters=filters,
                )
                resp: RetrievalResponse = self.retrieval_service.retrieve(
                    query=retrieval_req,
                    build_id=target.build_id,
                )
                return MultiRAGRetrievalResult(
                    target=target,
                    response=resp,
                )
            except Exception as e:
                logger.error("Failed parallel retrieval for RAG %s (build %s): %s", target.rag_id, target.build_id, e)
                raise MultiRAGRetrievalError(
                    f"Retrieval failed for attached RAG '{target.rag_name}' ({target.rag_id}): {str(e)}",
                    details={"rag_id": target.rag_id, "build_id": target.build_id, "error": str(e)},
                ) from e

        tasks = [
            loop.run_in_executor(None, _retrieve_single, target)
            for target in targets
        ]

        try:
            results: List[MultiRAGRetrievalResult] = await asyncio.gather(*tasks)
            return results
        except Exception as e:
            if isinstance(e, MultiRAGRetrievalError):
                raise e
            raise MultiRAGRetrievalError(f"Multi-RAG parallel retrieval failed: {str(e)}") from e

    def fuse_and_deduplicate(
        self,
        retrieval_results: List[MultiRAGRetrievalResult],
        global_top_k: int = 8,
        rrf_k: int = 60,
    ) -> MultiRAGFusedContext:
        """
        Performs Reciprocal Rank Fusion (RRF, k=60) and composite deduplication:
        - RRF formula: RRF(d) = sum_{r in RAGs} (1 / (rrf_k + rank_r(d)))
        - Deduplication key: candidate.composite_key == f"{rag_id}:{build_id}:{chunk_id}"
        - Preserves strict provenance on each candidate.
        """
        start_time = time.monotonic()
        all_candidates: List[MultiRAGCandidate] = []
        rrf_scores: Dict[str, float] = {}
        candidate_by_key: Dict[str, MultiRAGCandidate] = {}

        for result in retrieval_results:
            target = result.target
            # result.response.results contains RetrievedChunk instances sorted by rank
            for rank_idx, chunk in enumerate(result.response.results):
                rank = rank_idx + 1  # 1-indexed rank
                candidate = MultiRAGCandidate(
                    rag_id=target.rag_id,
                    rag_name=target.rag_name,
                    version_id=target.version_id,
                    version_tag=target.version_tag,
                    build_id=target.build_id,
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.provenance.source_id or f"src_{target.rag_id}",
                    source_name=chunk.provenance.source_name or "Unknown Source",
                    page_number=chunk.provenance.page_number,
                    heading_path=chunk.provenance.heading_path or [],
                    text=chunk.text,
                    raw_score=chunk.score,
                    retrieval_rank=rank,
                )
                comp_key = candidate.composite_key
                
                # Compute / accumulate RRF score
                rank_contrib = 1.0 / (rrf_k + rank)
                rrf_scores[comp_key] = rrf_scores.get(comp_key, 0.0) + rank_contrib

                if comp_key not in candidate_by_key:
                    candidate_by_key[comp_key] = candidate
                else:
                    # If duplicate chunk appears across rankings, preserve highest raw_score
                    if candidate.raw_score > candidate_by_key[comp_key].raw_score:
                        candidate_by_key[comp_key] = candidate

        # Assign calculated RRF scores to candidate objects
        for comp_key, candidate in candidate_by_key.items():
            candidate.rrf_score = rrf_scores[comp_key]
            all_candidates.append(candidate)

        # Sort descending by rrf_score (tie breaker: raw_score descending)
        all_candidates.sort(key=lambda c: (c.rrf_score, c.raw_score), reverse=True)

        from ragger_engine.retrieval.deduplication import deduplicate_multi_rag_candidates
        deduped_candidates = deduplicate_multi_rag_candidates(all_candidates)
        selected_candidates = deduped_candidates[:global_top_k]
        latency = (time.monotonic() - start_time) * 1000.0

        return MultiRAGFusedContext(
            candidates=selected_candidates,
            targets_resolved=[r.target for r in retrieval_results],
            total_candidates=len(all_candidates),
            retrieval_latency_ms=latency,
        )

    def get_client_targets(self, targets: List[ResolvedRAGTarget]) -> List[MultiRAGClientTarget]:
        """
        Projects resolved targets for client consumption.
        Strictly excludes build_id.
        """
        return [
            MultiRAGClientTarget(
                rag_id=t.rag_id,
                rag_name=t.rag_name,
                version_id=t.version_id,
                version_tag=t.version_tag,
            )
            for t in targets
        ]
