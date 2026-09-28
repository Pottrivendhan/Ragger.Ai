"""
Core Evaluation Service for Phase 8 Automated Quality Evaluation & Benchmarking Subsystem.
Strictly isolated from Retrieval/Generation runtime logic. Enforces:
- One active evaluation per workspace concurrency gate (HTTP 409)
- Active build snapshot capture & post-run integrity verification (HTTP 409)
- Graph RAG evaluation rejection (HTTP 422)
- Zero chat history pollution via ephemeral generation
- Frozen RAG Quality Score calculation with dynamic normalization
- Atomic report persistence
"""

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Dict, List, Optional
import uuid

from ragger_engine.builder.models import Chunk
from ragger_engine.generation.models import ChatQueryRequest
from ragger_engine.generation.service import GenerationService
from ragger_engine.retrieval.models import RetrievalQuery
from ragger_engine.retrieval.service import RetrievalService

from .config_manager import get_evaluation_config
from .dataset_generator import generate_evaluation_probes
from .exceptions import (
    EvaluationAlreadyRunningError,
    EvaluationCancelledError,
    EvaluationError,
    EvaluationNotFoundError,
    InvalidEvaluationParameterError,
    ModelNotAvailableError,
)
from .metrics import (
    aggregate_deterministic_metrics,
    aggregate_judge_metrics,
    calculate_rag_quality_score,
)
from .models import (
    BuildSnapshot,
    EvaluationConfig,
    EvaluationReport,
    EvaluationRunProgress,
    EvaluationRunRequest,
    EvaluationState,
    ProbeEvaluationResult,
    ProbeType,
    VersionEvaluationComparisonResult,
    VersionEvaluationMetricDelta,
)
from .providers.base import BaseEvalJudge
from .providers.factory import get_eval_judge
from .snapshot import (
    capture_build_snapshot,
    capture_build_snapshot_for_build,
    verify_build_integrity,
)


class EvaluationService:
    """
    Orchestrates automated evaluation jobs, benchmark scoring, and report persistence
    for active workspace builds and version-scoped RAG artifacts.
    """

    def __init__(
        self,
        workspace_dir: Path,
        workspace_id: str,
        retrieval_service: RetrievalService,
        generation_service: GenerationService,
        judge_override: Optional[BaseEvalJudge] = None,
        rag_lifecycle_service=None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.workspace_id = workspace_id
        self.retrieval_service = retrieval_service
        self.generation_service = generation_service
        self._judge_override = judge_override
        self.rag_lifecycle_service = rag_lifecycle_service

        self.evaluations_dir = self.workspace_dir / "evaluations"
        self.evaluations_dir.mkdir(parents=True, exist_ok=True)

        self._lock = asyncio.Lock()
        self._active_eval_id: Optional[str] = None
        self._active_task: Optional[asyncio.Task] = None
        self._cancel_event = asyncio.Event()
        self._progress: Optional[EvaluationRunProgress] = None

    # -------------------------------------------------------------------------
    # Concurrency and Job Lifecycle
    # -------------------------------------------------------------------------

    def _resolve_snapshot(self, request: EvaluationRunRequest, target_ws: str) -> BuildSnapshot:
        """
        Resolves build snapshot based on evaluation mode:
        - Legacy mode (neither rag_id nor version_id): captures active_build.json snapshot.
        - Version-scoped mode (both rag_id and version_id): resolves build_id via RAGLifecycleService
          and captures immutable build snapshot.
        - Partial arguments: strictly rejected with InvalidEvaluationParameterError (HTTP 400).
        """
        has_rag = request.rag_id is not None and bool(request.rag_id.strip())
        has_ver = request.version_id is not None and bool(request.version_id.strip())

        if has_rag != has_ver:
            raise InvalidEvaluationParameterError(
                "Both 'rag_id' and 'version_id' must be provided for version-scoped evaluation, "
                "or both omitted for legacy workspace evaluation. Partial arguments are rejected.",
                parameter="rag_id/version_id",
            )

        if has_rag and has_ver:
            if not self.rag_lifecycle_service:
                raise EvaluationError("RAGLifecycleService is not configured for version-scoped evaluation.")
            
            rag_record = self.rag_lifecycle_service.get_rag(request.rag_id)
            target_version = None
            for v in rag_record.versions:
                if v.version_id == request.version_id:
                    target_version = v
                    break

            if not target_version:
                from ragger_engine.rag_lifecycle.exceptions import RAGVersionNotFoundError
                raise RAGVersionNotFoundError(request.rag_id, request.version_id)

            return capture_build_snapshot_for_build(
                self.workspace_dir,
                build_id=target_version.build_id,
                rag_id=request.rag_id,
                version_id=request.version_id,
                version_tag=target_version.version_tag,
            )

        # Legacy workspace mode
        return capture_build_snapshot(self.workspace_dir, target_ws)

    async def start_evaluation(
        self,
        request: EvaluationRunRequest,
        workspace_id: Optional[str] = None,
    ) -> str:
        """
        Starts an evaluation run in the background.
        Enforces strictly one active evaluation per workspace (HTTP 409).
        Executes preflight validations synchronously (build snapshot, architecture, judge model check)
        before spawning background task so that preflight failures return appropriate HTTP status codes.
        """
        target_ws = workspace_id or self.workspace_id
        async with self._lock:
            if self._active_eval_id and self._active_task and not self._active_task.done():
                raise EvaluationAlreadyRunningError(target_ws, self._active_eval_id)

            # 1. PREFLIGHT: Capture Build Snapshot & Validate Architecture (412 / 422 / 400 / 404)
            snapshot: BuildSnapshot = self._resolve_snapshot(request, target_ws)

            # 2. Config & Judge availability validation (424 / 400)
            config: EvaluationConfig = get_evaluation_config(self.workspace_dir)
            sample_size = request.sample_size or config.default_sample_size
            sampling_seed = request.sampling_seed if request.sampling_seed is not None else config.sampling_seed
            effective_config = EvaluationConfig(
                judge_provider=config.judge_provider,
                judge_model_name=config.judge_model_name,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                default_sample_size=sample_size,
                sampling_seed=sampling_seed,
                retrieval_top_k=config.retrieval_top_k,
            )
            judge = get_eval_judge(effective_config, judge_override=self._judge_override)
            judge.validate_availability()

            eval_id = f"eval_{uuid.uuid4().hex[:12]}"
            self._active_eval_id = eval_id
            self._cancel_event.clear()

            now_iso = datetime.now(timezone.utc).isoformat()
            self._progress = EvaluationRunProgress(
                eval_id=eval_id,
                workspace_id=target_ws,
                state=EvaluationState.PREFLIGHT,
                current_stage="Preflight checks passed, starting evaluation",
                total_probes=0,
                processed_probes=0,
                percent=0.0,
                created_at=now_iso,
                updated_at=now_iso,
            )

            self._active_task = asyncio.create_task(
                self._run_evaluation_job(request, eval_id, snapshot=snapshot, effective_config=effective_config, judge=judge, workspace_id=target_ws)
            )
            return eval_id

    async def run_evaluation(
        self,
        request: EvaluationRunRequest,
        eval_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> EvaluationReport:
        """
        Direct/synchronous evaluation runner (used by tests and background tasks).
        """
        target_ws = workspace_id or self.workspace_id
        async with self._lock:
            if self._active_eval_id and self._active_task and not self._active_task.done() and self._active_eval_id != eval_id:
                raise EvaluationAlreadyRunningError(target_ws, self._active_eval_id)

            snapshot: BuildSnapshot = self._resolve_snapshot(request, target_ws)
            config: EvaluationConfig = get_evaluation_config(self.workspace_dir)
            sample_size = request.sample_size or config.default_sample_size
            sampling_seed = request.sampling_seed if request.sampling_seed is not None else config.sampling_seed
            effective_config = EvaluationConfig(
                judge_provider=config.judge_provider,
                judge_model_name=config.judge_model_name,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
                default_sample_size=sample_size,
                sampling_seed=sampling_seed,
                retrieval_top_k=config.retrieval_top_k,
            )
            judge = get_eval_judge(effective_config, judge_override=self._judge_override)
            judge.validate_availability()

            if not eval_id:
                eval_id = f"eval_{uuid.uuid4().hex[:12]}"

            self._active_eval_id = eval_id
            self._cancel_event.clear()

            now_iso = datetime.now(timezone.utc).isoformat()
            self._progress = EvaluationRunProgress(
                eval_id=eval_id,
                workspace_id=target_ws,
                state=EvaluationState.PREFLIGHT,
                current_stage="Preflight checks passed, starting evaluation",
                total_probes=0,
                processed_probes=0,
                percent=0.0,
                created_at=now_iso,
                updated_at=now_iso,
            )

        return await self._run_evaluation_job(request, eval_id, snapshot=snapshot, effective_config=effective_config, judge=judge, workspace_id=target_ws)

    async def cancel_evaluation(self, eval_id: str, workspace_id: Optional[str] = None) -> dict:
        """
        Requests cancellation of an active evaluation run.
        Terminal states (completed, cancelled, failed) are immutable; late cancels are no-ops.
        """
        target_ws = workspace_id or self.workspace_id
        async with self._lock:
            # Check if this eval_id is on disk
            report_file = self.evaluations_dir / f"{eval_id}.json"
            if report_file.exists():
                try:
                    with open(report_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    if data.get("workspace_id") != target_ws:
                        raise EvaluationNotFoundError(eval_id, target_ws)
                except EvaluationNotFoundError:
                    raise
                except Exception:
                    pass
                return {"status": "already_completed", "eval_id": eval_id}

            if self._active_eval_id != eval_id:
                raise EvaluationNotFoundError(eval_id, target_ws)

            if not self._progress:
                return {"status": "not_active", "eval_id": eval_id}

            if self._progress.workspace_id != target_ws:
                raise EvaluationNotFoundError(eval_id, target_ws)

            state = self._progress.state
            if state == EvaluationState.COMPLETED:
                return {"status": "already_completed", "eval_id": eval_id}
            elif state == EvaluationState.CANCELLED:
                return {"status": "already_cancelled", "eval_id": eval_id}
            elif state == EvaluationState.FAILED:
                return {"status": "already_failed", "eval_id": eval_id}

            self._cancel_event.set()
            self._progress.state = EvaluationState.CANCEL_REQUESTED
            self._progress.current_stage = "Cancellation requested by user"
            self._progress.updated_at = datetime.now(timezone.utc).isoformat()
            return {"status": "cancellation_requested", "eval_id": eval_id}

    def get_progress(self, eval_id: str, workspace_id: Optional[str] = None) -> EvaluationRunProgress:
        """Returns the real-time progress of an evaluation run or completed progress snapshot."""
        target_ws = workspace_id or self.workspace_id
        if self._progress and self._progress.eval_id == eval_id:
            if self._progress.workspace_id != target_ws:
                raise EvaluationNotFoundError(eval_id, target_ws)
            return self._progress

        report_file = self.evaluations_dir / f"{eval_id}.json"
        if report_file.exists():
            with open(report_file, "r", encoding="utf-8") as f:
                report_data = json.load(f)
            if report_data.get("workspace_id") != target_ws:
                raise EvaluationNotFoundError(eval_id, target_ws)
            return EvaluationRunProgress(
                eval_id=eval_id,
                workspace_id=target_ws,
                state=EvaluationState.COMPLETED,
                current_stage="Evaluation completed successfully",
                total_probes=len(report_data.get("probe_results", [])),
                processed_probes=len(report_data.get("probe_results", [])),
                percent=100.0,
                created_at=report_data.get("created_at", datetime.now(timezone.utc).isoformat()),
                updated_at=report_data.get("completed_at", datetime.now(timezone.utc).isoformat()),
            )

        raise EvaluationNotFoundError(eval_id, target_ws)

    # -------------------------------------------------------------------------
    # Core Pipeline Execution
    # -------------------------------------------------------------------------

    async def _run_evaluation_job(
        self,
        request: EvaluationRunRequest,
        eval_id: str,
        snapshot: Optional[BuildSnapshot] = None,
        effective_config: Optional[EvaluationConfig] = None,
        judge: Optional[BaseEvalJudge] = None,
        workspace_id: Optional[str] = None,
    ) -> EvaluationReport:
        target_ws = workspace_id or self.workspace_id
        start_time_monotonic = time.monotonic()
        start_time_iso = datetime.now(timezone.utc).isoformat()

        def _update_progress(state: EvaluationState, stage: str, percent: float, processed: int = 0, total: int = 0):
            if self._progress and self._progress.eval_id == eval_id:
                self._progress.state = state
                self._progress.current_stage = stage
                self._progress.percent = percent
                if processed:
                    self._progress.processed_probes = processed
                if total:
                    self._progress.total_probes = total
                self._progress.updated_at = datetime.now(timezone.utc).isoformat()

        try:
            # 1. PREFLIGHT: Capture Build Snapshot & Validate Architecture (if not provided)
            _update_progress(EvaluationState.PREFLIGHT, "Validating active build snapshot and architecture", 5.0)
            if snapshot is None:
                snapshot = self._resolve_snapshot(request, target_ws)

            if effective_config is None:
                config: EvaluationConfig = get_evaluation_config(self.workspace_dir)
                sample_size = request.sample_size or config.default_sample_size
                sampling_seed = request.sampling_seed if request.sampling_seed is not None else config.sampling_seed
                effective_config = EvaluationConfig(
                    judge_provider=config.judge_provider,
                    judge_model_name=config.judge_model_name,
                    temperature=config.temperature,
                    max_tokens=config.max_tokens,
                    default_sample_size=sample_size,
                    sampling_seed=sampling_seed,
                    retrieval_top_k=config.retrieval_top_k,
                )
            else:
                sample_size = effective_config.default_sample_size
                sampling_seed = effective_config.sampling_seed

            if judge is None:
                judge = get_eval_judge(effective_config, judge_override=self._judge_override)
                judge.validate_availability()

            if self._cancel_event.is_set():
                raise EvaluationCancelledError(eval_id)

            # 2. DATASET GENERATION: Load chunks & generate synthetic probes
            _update_progress(EvaluationState.GENERATING_DATASET, "Generating stratified synthetic probes", 15.0)
            chunks_file = self.workspace_dir / "builds" / snapshot.build_id / "index" / "chunks.jsonl"
            if not chunks_file.exists():
                raise EvaluationError(f"Chunks store missing for active build '{snapshot.build_id}'")

            chunks: List[Chunk] = []
            chunk_source_map: Dict[str, str] = {}
            with open(chunks_file, "r", encoding="utf-8") as f:
                for line in f:
                    line_str = line.strip()
                    if line_str:
                        c = Chunk.model_validate_json(line_str)
                        chunks.append(c)
                        chunk_source_map[c.chunk_id] = c.source_id

            probes = generate_evaluation_probes(
                chunks=chunks,
                sample_size=sample_size,
                sampling_seed=sampling_seed,
            )

            total_probes = len(probes)
            _update_progress(
                EvaluationState.EVALUATING_RETRIEVAL,
                f"Generated {total_probes} probes. Beginning evaluation.",
                20.0,
                processed=0,
                total=total_probes,
            )

            # 3. EVALUATION EXECUTION: Retrieval + Generation + Judge
            probe_results: List[ProbeEvaluationResult] = []
            selected_chunk_ids = [p.origin_chunk_id for p in probes if p.origin_chunk_id]
            selected_source_ids = list({p.origin_source_id for p in probes if p.origin_source_id})

            for idx, probe in enumerate(probes):
                if self._cancel_event.is_set():
                    raise EvaluationCancelledError(eval_id)

                pct = 20.0 + (float(idx) / float(total_probes)) * 60.0
                _update_progress(
                    EvaluationState.EVALUATING_RETRIEVAL,
                    f"Evaluating probe {idx + 1}/{total_probes}: {probe.query[:40]}...",
                    round(pct, 1),
                    processed=idx,
                    total=total_probes,
                )

                # 3a. Phase 6 Retrieval against target build_id
                ret_start = time.monotonic()
                ret_query = RetrievalQuery(
                    query=probe.query,
                    top_k=effective_config.retrieval_top_k,
                )
                ret_res = self.retrieval_service.retrieve(ret_query, build_id=snapshot.build_id)
                ret_latency = (time.monotonic() - ret_start) * 1000.0

                retrieved_cids = [r.chunk_id for r in ret_res.results]
                retrieved_texts = [r.text for r in ret_res.results]

                # Retrieval ranks
                rank = None
                hit_1 = False
                hit_3 = False
                hit_5 = False
                recip_rank = 0.0

                if probe.origin_chunk_id and probe.origin_chunk_id in retrieved_cids:
                    rank = retrieved_cids.index(probe.origin_chunk_id) + 1
                    hit_1 = (rank == 1)
                    hit_3 = (rank <= 3)
                    hit_5 = (rank <= 5)
                    recip_rank = 1.0 / float(rank)

                if self._cancel_event.is_set():
                    raise EvaluationCancelledError(eval_id)

                # 3b. Phase 7 Ephemeral Grounded Generation (No session persistence) against target build_id
                _update_progress(
                    EvaluationState.EVALUATING_GENERATION,
                    f"Generating ephemeral answer for probe {idx + 1}/{total_probes}...",
                    round(pct + (30.0 / total_probes), 1),
                    processed=idx,
                    total=total_probes,
                )

                gen_req = ChatQueryRequest(
                    query=probe.query,
                    top_k=effective_config.retrieval_top_k,
                    temperature=effective_config.temperature,
                )
                gen_res = await self.generation_service.generate_ephemeral(gen_req, target_ws, build_id=snapshot.build_id)
                gen_answer = gen_res.answer
                gen_latency = gen_res.generation_latency_ms

                # Citations verification
                verified_cits = len(gen_res.valid_citations)
                unverified_cits = len(gen_res.unverified_citation_keys)
                total_cits = verified_cits + unverified_cits
                cit_precision = (float(verified_cits) / float(total_cits)) if total_cits > 0 else None

                if self._cancel_event.is_set():
                    raise EvaluationCancelledError(eval_id)

                # 3c. Judge Claims & Disclaimer Assessment
                is_ood = (probe.probe_type == ProbeType.OUT_OF_DOMAIN)
                correct_disc = await judge.evaluate_disclaimer(probe.query, gen_answer, is_ood)

                # Claims are evaluated on in-domain probes or when answer has factual content
                tot_claims, sup_claims, unsup_claims = await judge.evaluate_claims(
                    probe.query,
                    gen_answer,
                    retrieved_texts,
                )
                faith_score = (float(sup_claims) / float(tot_claims)) if tot_claims > 0 else None

                # Detect disclaimer markers
                disclaimer_markers = ["could not find information", "insufficient evidence", "not found"]
                emitted_disc = any(dm in gen_answer.lower() for dm in disclaimer_markers) or gen_res.has_insufficient_evidence

                probe_result = ProbeEvaluationResult(
                    probe_id=probe.probe_id,
                    probe_type=probe.probe_type,
                    query=probe.query,
                    retrieved_chunk_ids=retrieved_cids,
                    origin_chunk_rank=rank,
                    hit_at_1=hit_1,
                    hit_at_3=hit_3,
                    hit_at_5=hit_5,
                    reciprocal_rank=round(recip_rank, 4),
                    retrieval_latency_ms=round(ret_latency, 2),
                    generated_answer=gen_answer,
                    disclaimer_emitted=emitted_disc,
                    correct_disclaimer=correct_disc,
                    total_claims=tot_claims,
                    supported_claims=sup_claims,
                    unsupported_claims=unsup_claims,
                    faithfulness=round(faith_score, 4) if faith_score is not None else None,
                    verified_citations=verified_cits,
                    unverified_citations=unverified_cits,
                    citation_precision=round(cit_precision, 4) if cit_precision is not None else None,
                    generation_latency_ms=round(gen_latency, 2),
                )
                probe_results.append(probe_result)

            # 4. AGGREGATING METRICS
            _update_progress(EvaluationState.AGGREGATING, "Aggregating benchmark metrics and composite score", 85.0)
            det_metrics = aggregate_deterministic_metrics(probe_results, snapshot, chunk_source_map)
            judge_metrics = aggregate_judge_metrics(probe_results)
            quality_score, weights_used = calculate_rag_quality_score(det_metrics, judge_metrics)

            # 5. POST-RUN VERIFICATION: Check build integrity against preflight snapshot
            _update_progress(EvaluationState.VERIFYING, "Verifying post-evaluation build integrity", 95.0)
            verify_build_integrity(self.workspace_dir, snapshot)

            # 6. PERSISTENCE: Save Evaluation Report atomically
            end_time_iso = datetime.now(timezone.utc).isoformat()
            duration_ms = (time.monotonic() - start_time_monotonic) * 1000.0

            report = EvaluationReport(
                eval_id=eval_id,
                workspace_id=target_ws,
                created_at=start_time_iso,
                completed_at=end_time_iso,
                duration_ms=round(duration_ms, 2),
                build_snapshot=snapshot,
                config=effective_config,
                quality_score=quality_score,
                metric_weights_used=weights_used,
                deterministic_metrics=det_metrics,
                judge_evaluated_metrics=judge_metrics,
                probe_results=probe_results,
                selected_chunk_ids=selected_chunk_ids,
                selected_source_ids=selected_source_ids,
                rag_id=snapshot.rag_id,
                version_id=snapshot.version_id,
                version_tag=snapshot.version_tag,
            )

            report_file = self.evaluations_dir / f"{eval_id}.json"
            tmp_file = self.evaluations_dir / f"{eval_id}.json.tmp"
            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=2))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_file, report_file)

            _update_progress(
                EvaluationState.COMPLETED,
                "Evaluation completed successfully",
                100.0,
                processed=total_probes,
                total=total_probes,
            )
            return report

        except EvaluationCancelledError as e:
            if self._progress:
                self._progress.state = EvaluationState.CANCELLED
                self._progress.current_stage = "Evaluation run cancelled by user"
                self._progress.error_code = "EVALUATION_CANCELLED"
                self._progress.error_message = str(e)
                self._progress.updated_at = datetime.now(timezone.utc).isoformat()
            raise

        except Exception as e:
            if self._progress:
                self._progress.state = EvaluationState.FAILED
                self._progress.current_stage = f"Evaluation failed: {str(e)}"
                self._progress.error_code = getattr(e, "code", "EVALUATION_FAILED")
                self._progress.error_message = str(e)
                self._progress.updated_at = datetime.now(timezone.utc).isoformat()
            raise

        finally:
            async with self._lock:
                if self._active_eval_id == eval_id:
                    self._active_eval_id = None
                    self._active_task = None

    # -------------------------------------------------------------------------
    # Report Retrieval and Deletion
    # -------------------------------------------------------------------------

    def list_reports(self, workspace_id: Optional[str] = None) -> List[dict]:
        """Lists all evaluation reports persisted in this workspace."""
        reports = []
        target_ws = workspace_id or self.workspace_id
        for p in self.evaluations_dir.glob("eval_*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("workspace_id") != target_ws:
                    continue
                reports.append({
                    "eval_id": data.get("eval_id"),
                    "workspace_id": data.get("workspace_id"),
                    "created_at": data.get("created_at"),
                    "completed_at": data.get("completed_at"),
                    "duration_ms": data.get("duration_ms"),
                    "quality_score": data.get("quality_score"),
                    "build_id": data.get("build_snapshot", {}).get("build_id"),
                    "chunk_count": data.get("build_snapshot", {}).get("chunk_count"),
                    "probe_count": len(data.get("probe_results", [])),
                    "rag_id": data.get("rag_id") or data.get("build_snapshot", {}).get("rag_id"),
                    "version_id": data.get("version_id") or data.get("build_snapshot", {}).get("version_id"),
                    "version_tag": data.get("version_tag") or data.get("build_snapshot", {}).get("version_tag"),
                })
            except Exception:
                pass

        reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return reports

    def list_version_reports(self, rag_id: str, version_id: str, workspace_id: Optional[str] = None) -> List[dict]:
        """Lists evaluation reports specifically executed for a given RAG version."""
        all_reports = self.list_reports(workspace_id=workspace_id)
        return [r for r in all_reports if r.get("rag_id") == rag_id and r.get("version_id") == version_id]

    def get_report(self, eval_id: str, workspace_id: Optional[str] = None) -> EvaluationReport:
        """Loads and returns an evaluation report by ID with workspace ownership check."""
        target_ws = workspace_id or self.workspace_id
        report_file = self.evaluations_dir / f"{eval_id}.json"
        if not report_file.exists():
            raise EvaluationNotFoundError(eval_id, target_ws)

        try:
            with open(report_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("workspace_id") != target_ws:
                raise EvaluationNotFoundError(eval_id, target_ws)
            return EvaluationReport.model_validate(data)
        except EvaluationNotFoundError:
            raise
        except Exception as e:
            raise EvaluationError(f"Failed to read evaluation report '{eval_id}': {str(e)}") from e

    def delete_report(self, eval_id: str, workspace_id: Optional[str] = None) -> None:
        """Deletes an evaluation report by ID with workspace ownership check."""
        target_ws = workspace_id or self.workspace_id
        report_file = self.evaluations_dir / f"{eval_id}.json"
        if not report_file.exists():
            raise EvaluationNotFoundError(eval_id, target_ws)

        try:
            with open(report_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("workspace_id") != target_ws:
                raise EvaluationNotFoundError(eval_id, target_ws)
            report_file.unlink()
        except EvaluationNotFoundError:
            raise
        except Exception as e:
            raise EvaluationError(f"Failed to delete evaluation report '{eval_id}': {str(e)}") from e

    def compare_version_evaluations(
        self,
        rag_id: str,
        base_eval_id: str,
        target_eval_id: str,
        workspace_id: Optional[str] = None,
    ) -> VersionEvaluationComparisonResult:
        """
        Computes a purely factual, numeric comparison between two evaluation reports for the same RAG.
        Enforces:
        - Both evaluations belong to rag_id (cross-RAG comparison rejected with HTTP 400).
        - Both evaluations completed successfully.
        - Output is descriptive and numeric only (no promotional language or ranking).
        """
        base_report = self.get_report(base_eval_id, workspace_id=workspace_id)
        target_report = self.get_report(target_eval_id, workspace_id=workspace_id)

        base_rag = base_report.rag_id or base_report.build_snapshot.rag_id
        target_rag = target_report.rag_id or target_report.build_snapshot.rag_id

        if base_rag != rag_id:
            raise InvalidEvaluationParameterError(
                f"Base evaluation '{base_eval_id}' belongs to RAG '{base_rag}', not '{rag_id}'.",
                parameter="base_eval_id",
            )
        if target_rag != rag_id:
            raise InvalidEvaluationParameterError(
                f"Target evaluation '{target_eval_id}' belongs to RAG '{target_rag}', not '{rag_id}'.",
                parameter="target_eval_id",
            )

        def make_delta(base_val: Optional[float], target_val: Optional[float]) -> VersionEvaluationMetricDelta:
            if base_val is not None and target_val is not None:
                d = round(target_val - base_val, 4)
            else:
                d = None
            return VersionEvaluationMetricDelta(
                base_value=base_val,
                target_value=target_val,
                delta=d,
            )

        b_snap = base_report.build_snapshot
        t_snap = target_report.build_snapshot

        b_det = base_report.deterministic_metrics
        t_det = target_report.deterministic_metrics
        b_jdg = base_report.judge_evaluated_metrics
        t_jdg = target_report.judge_evaluated_metrics

        return VersionEvaluationComparisonResult(
            rag_id=rag_id,
            base_eval_id=base_eval_id,
            target_eval_id=target_eval_id,
            base_version_id=b_snap.version_id,
            base_version_tag=b_snap.version_tag,
            base_build_id=b_snap.build_id,
            target_version_id=t_snap.version_id,
            target_version_tag=t_snap.version_tag,
            target_build_id=t_snap.build_id,
            quality_score_delta=make_delta(base_report.quality_score, target_report.quality_score),
            hits_at_1_delta=make_delta(b_det.hits_at_1, t_det.hits_at_1),
            hits_at_3_delta=make_delta(b_det.hits_at_3, t_det.hits_at_3),
            hits_at_5_delta=make_delta(b_det.hits_at_5, t_det.hits_at_5),
            mrr_delta=make_delta(b_det.mrr, t_det.mrr),
            source_coverage_delta=make_delta(b_det.source_coverage, t_det.source_coverage),
            citation_precision_delta=make_delta(b_det.citation_precision, t_det.citation_precision),
            faithfulness_delta=make_delta(b_jdg.faithfulness, t_jdg.faithfulness),
            disclaimer_accuracy_delta=make_delta(b_jdg.disclaimer_accuracy, t_jdg.disclaimer_accuracy),
        )
