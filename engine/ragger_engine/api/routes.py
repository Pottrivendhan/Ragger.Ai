"""API routes for Ragger Engine (Diagnostics & Ingestion)."""

import os
import platform
import sys
import asyncio
from typing import List, Optional, Union
from fastapi import APIRouter, File, Header, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ragger_engine.core.config import settings
from ragger_engine.ingestion.exceptions import IngestionError
from ragger_engine.ingestion.models import (
    DatasetModel,
    DetectedFileType,
    DocumentModel,
    IngestionResult,
    SourceRecord,
)
from ragger_engine.ingestion.service import IngestionService
from ragger_engine.analyzer.service import AnalyzerService
from ragger_engine.analyzer.models import FileAnalysisProfile, WorkspaceKnowledgeProfile
from ragger_engine.analyzer.exceptions import AnalysisError
from ragger_engine.analyzer.providers.ollama import OllamaAnalyzerProvider
from ragger_engine.recommendation.service import RecommendationService
from ragger_engine.recommendation.models import (
    ApprovedBuildConfig,
    ArchitectureSpec,
    ChunkingConfig,
    EmbeddingConfig,
    RagArchitectureId,
    RecommendationResult,
    RetrievalConfig,
    VectorDbConfig,
)
from ragger_engine.recommendation.exceptions import (
    ArchitectureCompatibilityError,
    BuildNotApprovedError,
    ImmutableConfigMutationError,
    InvalidConfigurationError,
    NoRecommendationAvailableError,
    RecommendationError,
)

from ragger_engine.builder.service import BuilderService
from ragger_engine.builder.models import BuildProgress, BuildManifest
from ragger_engine.builder.exceptions import (
    ArchitectureNotBuildableError,
    BuildAlreadyRunningError,
    BuilderError,
    BuildGateError,
    ModelNotAvailableError,
    SourceDriftError,
    VectorDbUnavailableError,
)

from ragger_engine.retrieval.service import RetrievalService
from ragger_engine.retrieval.models import (
    RetrievalQuery,
    RetrievalResponse,
    RetrievalStatus,
)
from ragger_engine.retrieval.exceptions import (
    ArchitectureNotRetrievableError,
    BuildIncompleteError,
    BuildUnavailableError,
    InvalidFilterError,
    InvalidTopKError,
    ManifestCorruptedError,
    NoActiveBuildError,
    QueryEmbeddingError,
    RetrievalEngineError,
)

router = APIRouter()
ingestion_service = IngestionService()
analyzer_service = AnalyzerService(ingestion_service=ingestion_service)
recommendation_service = RecommendationService()
builder_service = BuilderService(
    workspace_dir=recommendation_service.storage_dir,
    ingestion_service=ingestion_service,
    recommendation_service=recommendation_service,
)
retrieval_service = RetrievalService(
    workspace_dir=recommendation_service.storage_dir,
)

from ragger_engine.generation.service import GenerationService
from ragger_engine.generation.models import (
    ChatQueryRequest,
    GenerationResponse,
    ChatSession,
    GenerationConfig,
)
from ragger_engine.generation.exceptions import (
    GenerationError,
    GenerationCancelledError,
    ModelNotAvailableError as GenModelNotAvailableError,
    SessionNotFoundError,
    InvalidGenerationParameterError,
)

generation_service = GenerationService(
    workspace_dir=recommendation_service.storage_dir,
    retrieval_service=retrieval_service,
)

from ragger_engine.evaluation import (
    EvaluationService,
    EvaluationConfig,
    EvaluationRunRequest,
    EvaluationRunProgress,
    EvaluationReport,
    NoActiveBuildError as EvalNoActiveBuildError,
    ArchitectureNotEvaluableError,
    EvaluationAlreadyRunningError,
    EvaluationBuildChangedError,
    EvaluationNotFoundError,
    ModelNotAvailableError as EvalModelNotAvailableError,
    EvaluationCancelledError,
    InvalidEvaluationParameterError,
    EvaluationError,
    VersionEvaluationComparisonResult,
    get_evaluation_config,
    save_evaluation_config,
)

evaluation_service = EvaluationService(
    workspace_dir=recommendation_service.storage_dir,
    workspace_id="default",
    retrieval_service=retrieval_service,
    generation_service=generation_service,
)

from ragger_engine.models import (
    ModelManagerService,
    HardwareProfile,
    CatalogModelSpec,
    InstalledModelInfo,
    DownloadProgress,
    ActivateModelRequest,
    ActivateModelResponse,
    OllamaStatusResponse,
    ModelNotFoundError,
    ModelInUseError,
    DownloadAlreadyRunningError,
    ModelRoleMismatchError,
    InsufficientDiskSpaceError,
    ChecksumMismatchError,
    OllamaUnavailableError,
)

model_manager_service = ModelManagerService(
    storage_dir=recommendation_service.storage_dir,
    workspace_dir=recommendation_service.storage_dir,
)

from ragger_engine.rag_library import (
    RAGLibraryService,
    RAGArtifact,
    RAGArtifactDetail,
)

rag_library_service = RAGLibraryService(
    workspace_dir=recommendation_service.storage_dir,
)

from ragger_engine.rag_lifecycle import (
    RAGLifecycleService,
    RAGArtifactRecord,
    RAGVersionInfo,
    CreateRAGRequest,
    UpdateRAGRequest,
    RegisterVersionRequest,
    VersionComparisonResult,
    RAGSuggestionsResponse,
    RAGNotFoundError,
    RAGVersionNotFoundError,
    RAGInUseError,
    InvalidRAGPackError,
    ForbiddenModelWeightError,
)

from ragger_engine.agent_workspace import (
    AgentWorkspaceService,
    AgentProfile,
    CreateAgentRequest,
    UpdateAgentRequest,
    AttachRAGRequest,
    AgentChatRequest,
    AgentChatResponse,
    AgentNotFoundError,
    RAGArtifactNotFoundError,
    NoAttachedRAGError,
)

from ragger_engine.multi_rag import (
    MultiRAGCoordinator,
    MultiRAGClientTarget,
    MultiRAGRetrievalError,
)

multi_rag_coordinator = MultiRAGCoordinator(
    retrieval_service=retrieval_service,
    rag_lifecycle_service=None,  # wired below once rag_lifecycle_service is created
    rag_library_service=rag_library_service,
)

agent_workspace_service = AgentWorkspaceService(
    workspace_dir=recommendation_service.storage_dir,
    rag_library_service=rag_library_service,
    generation_service=generation_service,
    multi_rag_coordinator=multi_rag_coordinator,
)

rag_lifecycle_service = RAGLifecycleService(
    workspace_dir=recommendation_service.storage_dir,
    agent_workspace_service=agent_workspace_service,
)
agent_workspace_service.rag_lifecycle_service = rag_lifecycle_service
multi_rag_coordinator.rag_lifecycle_service = rag_lifecycle_service
evaluation_service.rag_lifecycle_service = rag_lifecycle_service




# ---------------------------------------------------------------------------
# Diagnostics Models & Routes
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class AuthenticatedHealthResponse(BaseModel):
    status: str
    service: str
    version: str
    authenticated: bool
    process_id: int


class RuntimeDiagnosticsResponse(BaseModel):
    python_version: str
    platform: str
    engine_version: str
    process_id: int
    environment: str
    host: str
    port: int


@router.get("/health", response_model=HealthResponse, tags=["Diagnostics"])
async def liveness_probe():
    """Unauthenticated liveness probe used for process supervision readiness."""
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get("/api/v1/health", response_model=AuthenticatedHealthResponse, tags=["Diagnostics"])
async def authenticated_health():
    """Authenticated health check confirming loopback token validity."""
    return AuthenticatedHealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        authenticated=True,
        process_id=os.getpid(),
    )


@router.get("/api/v1/runtime", response_model=RuntimeDiagnosticsResponse, tags=["Diagnostics"])
async def runtime_diagnostics():
    """Authenticated runtime diagnostic telemetry (strictly sanitized, zero secrets)."""
    return RuntimeDiagnosticsResponse(
        python_version=sys.version.split()[0],
        platform=platform.system().lower(),
        engine_version=settings.app_version,
        process_id=os.getpid(),
        environment=settings.environment,
        host=settings.host,
        port=settings.port,
    )


# ---------------------------------------------------------------------------
# Phase 2 Ingestion Requests & Routes
# ---------------------------------------------------------------------------

class IngestionDetectRequest(BaseModel):
    file_path: str


class IngestionParseRequest(BaseModel):
    file_path: str
    source_id: Optional[str] = None


class IngestionIngestRequest(BaseModel):
    file_path: str
    custom_source_id: Optional[str] = None


@router.post("/api/v1/ingestion/detect", response_model=DetectedFileType, tags=["Ingestion"])
async def detect_file_format(request: IngestionDetectRequest):
    """Detects file format via 4-signal deterministic detection."""
    try:
        return ingestion_service.detect_only(request.file_path)
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "DETECTION_ERROR", "message": str(e)})


@router.post("/api/v1/ingestion/parse", response_model=Union[DocumentModel, DatasetModel], tags=["Ingestion"])
async def parse_and_normalize_file(request: IngestionParseRequest):
    """Parses and normalizes file into DocumentModel or DatasetModel."""
    try:
        return ingestion_service.parse_only(request.file_path, source_id=request.source_id)
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "PARSE_ERROR", "message": str(e)})


@router.post("/api/v1/ingestion/ingest", response_model=IngestionResult, tags=["Ingestion"])
async def ingest_file(request: IngestionIngestRequest):
    """Full pipeline: Intake -> Detect -> Register -> Parse -> Normalize -> Sample."""
    try:
        return ingestion_service.ingest(request.file_path, custom_source_id=request.custom_source_id)
    except IngestionError as e:
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "INGESTION_ERROR", "message": str(e)})


@router.get("/api/v1/ingestion/sources", response_model=List[SourceRecord], tags=["Ingestion"])
async def list_sources():
    """Lists all registered source files from persistent SourceRegistry."""
    return ingestion_service.registry.list_sources()


@router.post("/api/v1/ingestion/upload", response_model=IngestionResult, tags=["Ingestion"])
async def upload_and_ingest_file(file: UploadFile = File(...)):
    """Accepts multipart browser file upload, stores safely, and executes ingestion pipeline."""
    from ragger_engine.core.storage import get_storage_root
    import shutil
    import logging
    logger = logging.getLogger("ragger.ingestion.upload")
    try:
        incoming_dir = get_storage_root() / "incoming"
        incoming_dir.mkdir(parents=True, exist_ok=True)
        filename = os.path.basename(file.filename or "uploaded_document")
        dest_path = incoming_dir / filename
        logger.info(f"Incoming upload for file '{filename}', saving to: {dest_path}")
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        file_size = dest_path.stat().st_size
        logger.info(f"Upload successfully received ({file_size} bytes). Triggering ingestion pipeline...")
        result = ingestion_service.ingest(str(dest_path))
        logger.info(f"Ingestion pipeline completed for '{filename}', assigned source_id: {result.source.source_id}")
        return result
    except IngestionError as e:
        logger.error(f"Ingestion error for '{file.filename}': code={e.code}, msg={e.message}", exc_info=True)
        raise HTTPException(status_code=e.status_code, detail={"code": e.code, "message": e.message})
    except Exception as e:
        logger.error(f"Unexpected upload failure for '{file.filename}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "UPLOAD_FAILED", "message": str(e)})



# ---------------------------------------------------------------------------
# Phase 3 Analyzer Requests & Routes
# ---------------------------------------------------------------------------

class AnalyzeFileRequest(BaseModel):
    source_id: str
    provider: Optional[str] = None


class SynthesizeWorkspaceRequest(BaseModel):
    workspace_id: str = "default"


@router.post("/api/v1/analysis/file", response_model=FileAnalysisProfile, tags=["Analyzer"])
async def analyze_file(request: AnalyzeFileRequest):
    """Executes observational analysis on an ingested source sample."""
    import logging
    logger = logging.getLogger("ragger.analysis.file")
    try:
        logger.info(f"Starting observational analysis for source_id: {request.source_id}")
        profile = await analyzer_service.analyze_source(
            source_id=request.source_id,
            provider_name=request.provider,
        )
        logger.info(f"Analysis completed for source_id {request.source_id}: {profile.structural_facts.total_words} words, domain: {profile.semantic_observations.detected_domain}")
        return profile
    except AnalysisError as e:
        logger.error(f"Analysis error for source_id {request.source_id}: code={e.code}, msg={e.message}", exc_info=True)
        raise HTTPException(status_code=400, detail={"code": e.code, "message": e.message})
    except Exception as e:
        logger.error(f"Unexpected analysis failure for source_id {request.source_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail={"code": "ANALYSIS_FAILED", "message": str(e)})


@router.post("/api/v1/analysis/workspace", response_model=WorkspaceKnowledgeProfile, tags=["Analyzer"])
async def synthesize_workspace(request: SynthesizeWorkspaceRequest):
    """Deterministically synthesizes all analyzed files into a WorkspaceKnowledgeProfile."""
    try:
        return analyzer_service.synthesize_workspace(workspace_id=request.workspace_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "SYNTHESIS_FAILED", "message": str(e)})


@router.get("/api/v1/analysis/profiles", response_model=List[FileAnalysisProfile], tags=["Analyzer"])
async def list_analysis_profiles():
    """Lists all generated FileAnalysisProfile records from persistent storage."""
    return analyzer_service.list_profiles()


@router.get("/api/v1/analysis/workspace", response_model=Optional[WorkspaceKnowledgeProfile], tags=["Analyzer"])
async def get_workspace_profile():
    """Retrieves current cached WorkspaceKnowledgeProfile."""
    return analyzer_service.get_workspace_profile()


@router.get("/api/v1/analysis/providers", tags=["Analyzer"])
async def list_analyzer_providers():
    """Lists available analyzer providers and local availability status."""
    ollama_provider = analyzer_service.providers.get("ollama")
    ollama_available = False
    if isinstance(ollama_provider, OllamaAnalyzerProvider):
        ollama_available = await ollama_provider.is_available()

    return [
        {
            "id": "heuristic_offline",
            "name": "Deterministic Heuristic (Offline)",
            "description": "Fast (< 10ms), 100% reproducible statistical and structural observation without external LLM.",
            "available": True,
            "is_default": True,
        },
        {
            "id": "ollama",
            "name": "Local Ollama",
            "description": "Local LLM execution via Ollama (127.0.0.1:11434) with zero network egress.",
            "available": ollama_available,
            "is_default": False,
        },
        {
            "id": "openai_compatible",
            "name": "OpenAI-Compatible (vLLM / LM Studio / External)",
            "description": "Standard chat completions endpoint for local vLLM, LM Studio, or configured servers.",
            "available": True,
            "is_default": False,
        },
    ]


# ---------------------------------------------------------------------------
# Phase 4 Recommendation Requests & Routes
# ---------------------------------------------------------------------------

class EvaluateRecommendationRequest(BaseModel):
    workspace_id: str = "default"


class ApproveConfigurationRequest(BaseModel):
    workspace_id: str = "default"
    architecture_id: RagArchitectureId
    source_ids: Optional[List[str]] = None
    custom_chunking: Optional[ChunkingConfig] = None
    custom_embedding: Optional[EmbeddingConfig] = None
    custom_vector_db: Optional[VectorDbConfig] = None
    custom_retrieval: Optional[RetrievalConfig] = None
    is_revision: bool = False


@router.post("/api/v1/recommendation/evaluate", response_model=RecommendationResult, tags=["Recommendation"])
async def evaluate_recommendation(request: EvaluateRecommendationRequest):
    """Deterministically evaluates workspace knowledge profile and constituent file profiles."""
    try:
        workspace_profile = analyzer_service.get_workspace_profile()
        file_profiles = analyzer_service.list_profiles()

        if workspace_profile is None or workspace_profile.total_sources == 0:
            if file_profiles:
                workspace_profile = analyzer_service.synthesize_workspace(workspace_id=request.workspace_id)
            else:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "NO_ANALYSIS_PROFILE", "message": "No workspace knowledge profile available. Run file analysis first."}
                )

        return recommendation_service.evaluate(workspace_profile, file_profiles)
    except HTTPException:
        raise
    except NoRecommendationAvailableError as e:
        raise HTTPException(status_code=400, detail={"code": "NO_SOURCES", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "EVALUATION_FAILED", "message": str(e)})


@router.get("/api/v1/recommendation/current", response_model=Optional[RecommendationResult], tags=["Recommendation"])
async def get_current_recommendation():
    """Retrieves current evaluated recommendation result."""
    return recommendation_service.get_current_recommendation()


@router.get("/api/v1/recommendation/architectures", response_model=List[ArchitectureSpec], tags=["Recommendation"])
async def list_rag_architectures():
    """Returns the full catalog of available RAG architectures and their technical specifications."""
    return recommendation_service.get_all_architectures()


@router.post("/api/v1/recommendation/approve", response_model=ApprovedBuildConfig, tags=["Recommendation"])
async def approve_configuration(request: ApproveConfigurationRequest):
    """
    Approves and freezes an ApprovedBuildConfig snapshot.
    Enforces immutability: existing frozen configurations cannot be mutated without is_revision=True.
    """
    try:
        source_ids = request.source_ids
        if not source_ids:
            source_ids = [s.source_id for s in ingestion_service.registry.list_sources()]

        return recommendation_service.approve_configuration(
            workspace_id=request.workspace_id,
            approved_architecture_id=request.architecture_id,
            source_ids=source_ids,
            custom_chunking=request.custom_chunking,
            custom_embedding=request.custom_embedding,
            custom_vector_db=request.custom_vector_db,
            custom_retrieval=request.custom_retrieval,
            is_revision=request.is_revision,
        )
    except ImmutableConfigMutationError as e:
        raise HTTPException(status_code=409, detail={"code": "CONFIG_ALREADY_FROZEN", "message": str(e)})
    except ArchitectureCompatibilityError as e:
        raise HTTPException(status_code=422, detail={"code": "INCOMPATIBLE_CONFIGURATION", "message": str(e)})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"code": "APPROVAL_FAILED", "message": str(e)})


@router.get("/api/v1/recommendation/approved", response_model=Optional[ApprovedBuildConfig], tags=["Recommendation"])
async def get_approved_build_config():
    """Retrieves the current frozen ApprovedBuildConfig snapshot."""
    return recommendation_service.get_approved_config()


@router.get("/api/v1/recommendation/validate-build", tags=["Recommendation"])
async def validate_build_contract():
    """
    Phase 5 Build Guardrail verification.
    Verifies that a frozen, cryptographically intact ApprovedBuildConfig exists for current sources.
    """
    current_source_ids = [s.source_id for s in ingestion_service.registry.list_sources()]
    is_valid, reason = recommendation_service.validate_build_prerequisites(current_source_ids=current_source_ids)
    if not is_valid:
        raise HTTPException(
            status_code=412,
            detail={"code": "BUILD_NOT_APPROVED", "message": reason}
        )
    approved = recommendation_service.get_approved_config()
    return {
        "valid": True,
        "config_id": approved.config_id if approved else None,
        "config_version": approved.config_version if approved else None,
        "config_hash": approved.config_hash if approved else None,
        "approved_architecture": approved.approved_architecture if approved else None,
    }


# ---------------------------------------------------------------------------
# Phase 5 RAG Builder API Routes
# ---------------------------------------------------------------------------

class CancelBuildRequest(BaseModel):
    build_id: str


@router.post("/api/v1/builder/start", tags=["Builder"])
async def start_knowledge_build():
    """
    Triggers end-to-end knowledge base construction against approved configuration.
    Enforces strict preflight build gate and single-build workspace concurrency lock.
    """
    try:
        build_id = builder_service.start_build()
        return {"status": "started", "build_id": build_id}
    except BuildAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": e.code, "message": str(e), "active_build_id": e.active_build_id},
        )
    except ArchitectureNotBuildableError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": e.code, "message": str(e)},
        )
    except (ModelNotAvailableError, VectorDbUnavailableError) as e:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={"code": e.code, "message": str(e)},
        )
    except (SourceDriftError, BuildGateError) as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"code": e.code, "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "BUILD_TRIGGER_FAILED", "message": str(e)},
        )


@router.get("/api/v1/builder/progress", response_model=BuildProgress, tags=["Builder"])
async def get_build_progress():
    """Authoritative state endpoint returning current build telemetry counters and stage."""
    return builder_service.progress


@router.get("/api/v1/builder/events", tags=["Builder"])
async def stream_build_events():
    """
    Server-Sent Events (SSE) streaming endpoint.
    Mirrors the authoritative BuildProgress state in real time.
    """
    async def event_generator():
        last_stage = None
        last_vectors = -1
        while True:
            prog = builder_service.progress
            # Emit event when stage or processed count changes
            if prog.current_stage != last_stage or prog.vectors_processed != last_vectors:
                last_stage = prog.current_stage
                last_vectors = prog.vectors_processed
                payload = prog.model_dump_json()
                yield f"data: {payload}\n\n"

            if prog.status in ("completed", "failed", "cancelled", "idle"):
                # Send final event and close stream
                payload = prog.model_dump_json()
                yield f"data: {payload}\n\n"
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/v1/builder/manifest", response_model=BuildManifest, tags=["Builder"])
async def get_active_build_manifest():
    """Retrieves the active, atomically verified BuildManifest for the workspace."""
    manifest = builder_service.get_active_manifest()
    if not manifest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NO_ACTIVE_BUILD", "message": "No active build manifest found for this workspace."},
        )
    return manifest


@router.post("/api/v1/builder/cancel", tags=["Builder"])
async def cancel_active_build(request: CancelBuildRequest):
    """Requests graceful cancellation of the active build pipeline."""
    builder_service.cancel_build(request.build_id)
    return {"status": "cancel_requested", "build_id": request.build_id}


# ---------------------------------------------------------------------------
# Phase 6 RAG Retrieval Engine API Routes
# ---------------------------------------------------------------------------

@router.post("/api/v1/retrieval/query", response_model=RetrievalResponse, tags=["Retrieval"])
async def query_retrieval_engine(query: RetrievalQuery):
    """
    Executes grounded retrieval query against the active build index.
    Dispatches to the architecture-specific strategy locked in the active manifest.
    """
    try:
        return retrieval_service.retrieve(query)
    except NoActiveBuildError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except (ManifestCorruptedError, BuildIncompleteError) as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except ArchitectureNotRetrievableError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except ModelNotAvailableError as e:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={"error": {"code": e.code, "message": str(e), "details": getattr(e, "details", {})}},
        )
    except (InvalidFilterError, InvalidTopKError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except QueryEmbeddingError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "RETRIEVAL_QUERY_FAILED", "message": str(e), "details": {}}},
        )


@router.get("/api/v1/retrieval/status", response_model=RetrievalStatus, tags=["Retrieval"])
async def get_retrieval_status():
    """Returns active build diagnostic metadata and retrieval readiness status."""
    return retrieval_service.get_status()


@router.post("/api/v1/retrieval/reload", tags=["Retrieval"])
async def reload_retrieval_cache():
    """
    Forces single-flight hot-reload of the active build cache.
    Zero-argument security contract: strictly reloads active_build.json.
    """
    try:
        cache = retrieval_service.reload_active_cache()
        return {
            "status": "reloaded",
            "build_id": cache.build_id,
            "manifest_id": cache.manifest.manifest_id,
            "manifest_hash": cache.manifest_hash,
            "architecture": cache.manifest.approved_architecture,
        }
    except NoActiveBuildError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except (ManifestCorruptedError, BuildIncompleteError) as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "RELOAD_FAILED", "message": str(e), "details": {}}},
        )


# ---------------------------------------------------------------------------
# Phase 7 Grounded Generation & Interactive RAG Chat Routes
# ---------------------------------------------------------------------------

@router.post("/api/v1/chat/generate", response_model=GenerationResponse, tags=["Chat"])
async def generate_chat_response(request: ChatQueryRequest, workspace_id: str = "default"):
    """
    Executes synchronous grounded generation against active build index and chat session.
    Strictly reuses Phase 6 retrieval, validates citations, and returns unmodified answer text.
    """
    try:
        return await generation_service.generate(request, workspace_id=workspace_id)
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except NoActiveBuildError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except (ManifestCorruptedError, BuildIncompleteError) as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except ArchitectureNotRetrievableError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except (GenModelNotAvailableError, ModelNotAvailableError) as e:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={"error": {"code": e.code, "message": str(e), "details": getattr(e, "details", {})}},
        )
    except (InvalidGenerationParameterError, InvalidTopKError, InvalidFilterError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except GenerationCancelledError as e:
        raise HTTPException(
            status_code=499,
            detail={"error": {"code": "GENERATION_CANCELLED", "message": str(e), "details": {}}},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "GENERATION_FAILED", "message": str(e), "details": {}}},
        )


@router.post("/api/v1/chat/stream", tags=["Chat"])
async def stream_chat_response(request: ChatQueryRequest, workspace_id: str = "default"):
    """
    Streams grounded generation token events and terminal metadata over Server-Sent Events (SSE).
    """
    async def sse_event_generator():
        import json as json_lib
        try:
            async for event in generation_service.stream_generation(request, workspace_id=workspace_id):
                ev_name = event.get("event", "message")
                ev_data = json_lib.dumps(event.get("data", {}))
                yield f"event: {ev_name}\ndata: {ev_data}\n\n"
        except Exception as err:
            err_data = json_lib.dumps({"code": "STREAM_ERROR", "message": str(err)})
            yield f"event: error\ndata: {err_data}\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/api/v1/chat/cancel/{session_id}", tags=["Chat"])
async def cancel_chat_generation(session_id: str):
    """Signals cancellation for an active generation task. Safe against terminal state races."""
    return await generation_service.cancel_generation(session_id)


@router.get("/api/v1/chat/sessions", response_model=List[ChatSession], tags=["Chat"])
async def list_chat_sessions(workspace_id: str = "default"):
    """Lists persisted chat sessions for the active workspace."""
    return generation_service.list_sessions(workspace_id=workspace_id)


@router.get("/api/v1/chat/sessions/{session_id}", response_model=ChatSession, tags=["Chat"])
async def get_chat_session(session_id: str, workspace_id: str = "default"):
    """Retrieves session dialogue history with workspace ownership verification."""
    try:
        return generation_service.get_session(session_id=session_id, workspace_id=workspace_id)
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.delete("/api/v1/chat/sessions/{session_id}", tags=["Chat"])
async def delete_chat_session(session_id: str, workspace_id: str = "default"):
    """Deletes a chat session with workspace ownership verification."""
    try:
        deleted = generation_service.delete_session(session_id=session_id, workspace_id=workspace_id)
        return {"deleted": deleted, "session_id": session_id}
    except SessionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.get("/api/v1/chat/config", response_model=GenerationConfig, tags=["Chat"])
async def get_generation_configuration():
    """Returns application-managed generation parameters."""
    return generation_service.get_generation_config()


@router.post("/api/v1/chat/config", response_model=GenerationConfig, tags=["Chat"])
async def update_generation_configuration(config: GenerationConfig):
    """Updates application-managed generation parameters."""
    generation_service.set_generation_config(config)
    return generation_service.get_generation_config()


# ---------------------------------------------------------------------------
# Phase 8 Automated Quality Evaluation & Benchmarking Routes
# ---------------------------------------------------------------------------

class EvaluationRunResponse(BaseModel):
    eval_id: str
    status: str
    workspace_id: str


@router.post("/api/v1/evaluation/run", response_model=EvaluationRunResponse, tags=["Evaluation"])
async def trigger_evaluation_run(
    request: EvaluationRunRequest = EvaluationRunRequest(),
    workspace_id: str = "default",
):
    """
    Triggers an automated RAG quality evaluation run against the active workspace build.
    Runs asynchronously in background; returns eval_id for progress polling.
    Enforces strictly one active evaluation per workspace (HTTP 409).
    """
    try:
        eval_id = await evaluation_service.start_evaluation(request, workspace_id=workspace_id)
        return EvaluationRunResponse(
            eval_id=eval_id,
            status="started",
            workspace_id=workspace_id,
        )
    except EvalNoActiveBuildError as e:
        raise HTTPException(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except ArchitectureNotEvaluableError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except EvaluationAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except EvalModelNotAvailableError as e:
        raise HTTPException(
            status_code=status.HTTP_424_FAILED_DEPENDENCY,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except InvalidEvaluationParameterError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except (RAGNotFoundError, RAGVersionNotFoundError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": str(e)}},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "EVALUATION_START_FAILED", "message": str(e), "details": {}}},
        )


@router.get("/api/v1/evaluation/progress/{eval_id}", response_model=EvaluationRunProgress, tags=["Evaluation"])
async def get_evaluation_progress(eval_id: str, workspace_id: str = "default"):
    """Returns observable telemetry and progress for an evaluation run."""
    try:
        return evaluation_service.get_progress(eval_id, workspace_id=workspace_id)
    except EvaluationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/evaluation/cancel/{eval_id}", tags=["Evaluation"])
async def cancel_evaluation_run(eval_id: str, workspace_id: str = "default"):
    """Signals cancellation for an active evaluation run. Protected against terminal state races."""
    try:
        return await evaluation_service.cancel_evaluation(eval_id, workspace_id=workspace_id)
    except EvaluationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.get("/api/v1/evaluation/reports", tags=["Evaluation"])
async def list_evaluation_reports(workspace_id: str = "default"):
    """Lists persisted evaluation report summaries for the active workspace."""
    return evaluation_service.list_reports(workspace_id=workspace_id)


@router.get("/api/v1/evaluation/reports/{eval_id}", response_model=EvaluationReport, tags=["Evaluation"])
async def get_evaluation_report(eval_id: str, workspace_id: str = "default"):
    """Retrieves full evaluation report card with metrics, probe diagnostics, and snapshot."""
    try:
        return evaluation_service.get_report(eval_id, workspace_id=workspace_id)
    except EvaluationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.delete("/api/v1/evaluation/reports/{eval_id}", tags=["Evaluation"])
async def delete_evaluation_report(eval_id: str, workspace_id: str = "default"):
    """Deletes an evaluation report card from the workspace."""
    try:
        evaluation_service.delete_report(eval_id, workspace_id=workspace_id)
        return {"deleted": True, "eval_id": eval_id}
    except EvaluationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.get("/api/v1/evaluation/config", response_model=EvaluationConfig, tags=["Evaluation"])
async def get_evaluation_configuration(workspace_id: str = "default"):
    """Returns application-managed evaluation parameters."""
    return get_evaluation_config(evaluation_service.workspace_dir)


@router.post("/api/v1/evaluation/config", response_model=EvaluationConfig, tags=["Evaluation"])
async def update_evaluation_configuration(config: EvaluationConfig, workspace_id: str = "default"):
    """Updates application-managed evaluation parameters atomically."""
    return save_evaluation_config(evaluation_service.workspace_dir, config)


# ---------------------------------------------------------------------------
# Phase 9 Local AI Model Manager & Hardware Adaptation Routes
# ---------------------------------------------------------------------------

@router.get("/api/v1/models/hardware", response_model=HardwareProfile, tags=["Models"])
async def get_hardware_capabilities(refresh: bool = False):
    """Returns host machine hardware capabilities, RAM/VRAM, and capability tier (cached 5m)."""
    return model_manager_service.get_hardware(refresh=refresh)


@router.get("/api/v1/models/catalog", response_model=List[CatalogModelSpec], tags=["Models"])
async def get_model_catalog(refresh_hardware: bool = False):
    """Returns curated immutable model catalog enriched with host compatibility and recommendations."""
    return model_manager_service.get_catalog(refresh_hardware=refresh_hardware)


@router.get("/api/v1/models/installed", response_model=List[InstalledModelInfo], tags=["Models"])
async def get_installed_models():
    """Returns unified inventory of all installed models (Direct weights + Ollama models)."""
    return await model_manager_service.list_installed_models()


@router.get("/api/v1/models/download/progress/{model_key:path}", response_model=DownloadProgress, tags=["Models"])
@router.get("/api/v1/models/download/{model_key:path}/progress", response_model=DownloadProgress, tags=["Models"])
async def get_model_download_progress(model_key: str):
    """Returns observable telemetry and progress for a download or pull in progress."""
    progress = model_manager_service.get_download_progress(model_key)
    if not progress:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "DOWNLOAD_NOT_FOUND", "message": f"No download found for '{model_key}'", "details": {}}},
        )
    return progress


@router.post("/api/v1/models/download/pause/{model_key:path}", tags=["Models"])
@router.post("/api/v1/models/download/{model_key:path}/pause", tags=["Models"])
async def pause_model_download(model_key: str):
    """Pauses active direct file download with fsync buffer flush."""
    try:
        return await model_manager_service.pause_download(model_key)
    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/models/download/resume/{model_key:path}", response_model=DownloadProgress, tags=["Models"])
@router.post("/api/v1/models/download/{model_key:path}/resume", response_model=DownloadProgress, tags=["Models"])
async def resume_model_download(model_key: str):
    """Resumes a paused direct file download or Ollama pull."""
    try:
        return await model_manager_service.resume_download(model_key)
    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except DownloadAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except InsufficientDiskSpaceError as e:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/models/download/cancel/{model_key:path}", tags=["Models"])
@router.post("/api/v1/models/download/{model_key:path}/cancel", tags=["Models"])
async def cancel_model_download(model_key: str):
    """Cancels an active download or pull and purges partial files."""
    try:
        return await model_manager_service.cancel_download(model_key)
    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/models/download/{model_key:path}", response_model=DownloadProgress, tags=["Models"])
async def download_model(model_key: str):
    """Triggers direct file download or Ollama pull for the specified catalog model_key."""
    try:
        return await model_manager_service.download_model(model_key)
    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except DownloadAlreadyRunningError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except InsufficientDiskSpaceError as e:
        raise HTTPException(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except OllamaUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.delete("/api/v1/models/{model_key:path}", tags=["Models"])
@router.delete("/api/v1/models/installed/{model_key:path}", tags=["Models"])
async def delete_installed_model(model_key: str):
    """Deletes an installed model after verifying it is not referenced in active configurations (HTTP 409)."""
    if model_key.startswith("installed/"):
        model_key = model_key[len("installed/"):]
    try:
        return await model_manager_service.delete_model(model_key)
    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except ModelInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except OllamaUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/models/{model_key:path}/activate", response_model=ActivateModelResponse, tags=["Models"])
async def activate_model(model_key: str, request: ActivateModelRequest):
    """Explicitly activates an installed model for role ('generation' or 'evaluation') in target workspace."""
    target_role = request.role or request.target_role or "generation"
    try:
        return await model_manager_service.activate_model(
            model_key=model_key,
            role=target_role,
            workspace_id=request.workspace_id,
        )
    except ModelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except ModelRoleMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )





@router.get("/api/v1/models/inventory", tags=["Models"])
async def get_models_inventory():
    """Unified inventory alias returning both array and total metrics."""
    models = await model_manager_service.list_installed_models()
    total_bytes = sum(m.size_bytes for m in models)
    return {
        "models": models,
        "total_count": len(models),
        "total_size_bytes": total_bytes,
    }


@router.get("/api/v1/models/ollama/status", response_model=OllamaStatusResponse, tags=["Models"])
async def get_ollama_status():
    """Returns real-time connection diagnostic status for local Ollama daemon."""
    return await model_manager_service.get_ollama_status()


# ---------------------------------------------------------------------------
# RAG Library Routes (Phase 11A - Read-Only Decoupled Knowledge Artifacts)
# ---------------------------------------------------------------------------

@router.get("/api/v1/rag-library/builds", response_model=List[RAGArtifact], tags=["RAG Library"])
async def list_rag_artifacts():
    """Discovers and lists all compiled RAG knowledge artifacts in the workspace."""
    return rag_library_service.list_artifacts()


@router.get("/api/v1/rag-library/builds/{build_id}", response_model=RAGArtifactDetail, tags=["RAG Library"])
async def get_rag_artifact_detail(build_id: str):
    """Returns detailed structure, configuration, and sample chunks for a specific RAG build."""
    artifact = rag_library_service.get_artifact_detail(build_id)
    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "BUILD_NOT_FOUND", "message": f"RAG build '{build_id}' does not exist."}},
        )
    return artifact


# ---------------------------------------------------------------------------
# Agent Workspace Routes (Phase 11B - Agents & RAG Attachment Orchestration)
# ---------------------------------------------------------------------------

@router.get("/api/v1/agents", response_model=List[AgentProfile], tags=["Agent Workspace"])
async def list_agents(x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Lists all configured AI Agent profiles for the requesting account."""
    return agent_workspace_service.list_agents(account_id=x_account_id)


@router.post("/api/v1/agents", response_model=AgentProfile, status_code=status.HTTP_201_CREATED, tags=["Agent Workspace"])
async def create_agent(request: CreateAgentRequest, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Creates a new AI Agent with validated RAG artifact attachments."""
    try:
        return agent_workspace_service.create_agent(request, account_id=x_account_id)
    except RAGArtifactNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.get("/api/v1/agents/{agent_id}", response_model=AgentProfile, tags=["Agent Workspace"])
async def get_agent(agent_id: str, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Retrieves an AI Agent profile by ID."""
    try:
        return agent_workspace_service.get_agent(agent_id, account_id=x_account_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.patch("/api/v1/agents/{agent_id}", response_model=AgentProfile, tags=["Agent Workspace"])
async def update_agent(agent_id: str, request: UpdateAgentRequest, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Updates an AI Agent profile or attachments."""
    try:
        return agent_workspace_service.update_agent(agent_id, request, account_id=x_account_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except RAGArtifactNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.delete("/api/v1/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Agent Workspace"])
async def delete_agent(agent_id: str, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Deletes an AI Agent profile."""
    try:
        agent_workspace_service.delete_agent(agent_id, account_id=x_account_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/agents/{agent_id}/rag-attachments", response_model=AgentProfile, tags=["Agent Workspace"])
async def attach_rag_to_agent(agent_id: str, request: AttachRAGRequest, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Attaches a RAG artifact to an Agent."""
    try:
        return agent_workspace_service.attach_rag(agent_id, request.rag_id, account_id=x_account_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except RAGArtifactNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.delete("/api/v1/agents/{agent_id}/rag-attachments/{rag_id}", response_model=AgentProfile, tags=["Agent Workspace"])
async def detach_rag_from_agent(agent_id: str, rag_id: str, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Detaches a RAG artifact from an Agent."""
    try:
        return agent_workspace_service.detach_rag(agent_id, rag_id, account_id=x_account_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.get("/api/v1/agents/{agent_id}/sessions", tags=["Agent Workspace"])
async def list_agent_sessions(agent_id: str):
    """Lists sessions for a specific agent."""
    try:
        return agent_workspace_service.list_agent_sessions(agent_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/agents/{agent_id}/chat", response_model=AgentChatResponse, tags=["Agent Workspace"])
async def agent_chat(agent_id: str, request: AgentChatRequest, workspace_id: str = "default"):
    """
    Executes grounded agent chat by dispatching through the verified GenerationService.
    Attaches RAG ID and build ID to every valid citation.
    """
    try:
        return await agent_workspace_service.chat(agent_id, request, workspace_id=workspace_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except NoAttachedRAGError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except BuildUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except RAGArtifactNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except MultiRAGRetrievalError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )


@router.post("/api/v1/agents/{agent_id}/chat/stream", tags=["Agent Workspace"])
async def stream_agent_chat_response(agent_id: str, request: AgentChatRequest, workspace_id: str = "default"):
    """
    Streams grounded agent generation token events and terminal metadata over Server-Sent Events (SSE).
    Authoritatively delegates to AgentWorkspaceService.stream_chat.
    """
    async def sse_event_generator():
        import json as json_lib
        try:
            async for event in agent_workspace_service.stream_chat(agent_id, request, workspace_id=workspace_id):
                ev_name = event.get("event", "message")
                ev_data = json_lib.dumps(event.get("data", {}))
                yield f"event: {ev_name}\ndata: {ev_data}\n\n"
        except (AgentNotFoundError, NoAttachedRAGError, BuildUnavailableError, RAGArtifactNotFoundError) as e:
            err_data = json_lib.dumps({"code": getattr(e, "code", "AGENT_ERROR"), "message": str(e)})
            yield f"event: error\ndata: {err_data}\n\n"
        except Exception as err:
            err_data = json_lib.dumps({"code": "STREAM_ERROR", "message": str(err)})
            yield f"event: error\ndata: {err_data}\n\n"

    return StreamingResponse(
        sse_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/v1/agents/{agent_id}/resolved-targets", response_model=List[MultiRAGClientTarget], tags=["Agent Workspace"])
async def get_agent_resolved_targets(agent_id: str):
    """
    Returns factual resolved version metadata for all attached knowledge bases.
    Strict Invariant (Adjustment 1):
    build_id is strictly backend-internal and must NEVER be exposed to the client.
    Returns: [{ rag_id, rag_name, version_id, version_tag }]
    """
    try:
        agent = agent_workspace_service.get_agent(agent_id)
        if not multi_rag_coordinator:
            return []
        resolved = multi_rag_coordinator.resolve_agent_runtimes(agent)
        return multi_rag_coordinator.get_client_targets(resolved)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except (RAGNotFoundError, RAGArtifactNotFoundError, NoAttachedRAGError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": getattr(e, "code", "ATTACHED_RAG_NOT_FOUND"), "message": str(e)}},
        )
    except BuildUnavailableError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )



# ===========================================================================
# Phase 12: RAG Artifact Lifecycle & Storage Contract Endpoints
# ===========================================================================

@router.get("/api/v1/rag-artifacts", response_model=List[RAGArtifactRecord], tags=["RAG Lifecycle"])
async def list_rag_artifacts(include_archived: bool = False, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Lists all registered RAG Knowledge Artifacts for the requesting account."""
    return rag_lifecycle_service.list_rags(include_archived=include_archived, account_id=x_account_id)


@router.post("/api/v1/rag-artifacts", response_model=RAGArtifactRecord, status_code=status.HTTP_201_CREATED, tags=["RAG Lifecycle"])
async def create_rag_artifact(request: CreateRAGRequest, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Creates a new RAG Knowledge Artifact for the requesting account."""
    try:
        return rag_lifecycle_service.create_rag(request, account_id=x_account_id)
    except InvalidRAGPackError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_INITIAL_BUILD", "message": str(e)}},
        )


@router.get("/api/v1/rag-artifacts/{rag_id}", response_model=RAGArtifactRecord, tags=["RAG Lifecycle"])
async def get_rag_artifact(rag_id: str, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """Retrieves a single RAG Knowledge Artifact by immutable rag_id."""
    try:
        return rag_lifecycle_service.get_rag(rag_id, account_id=x_account_id)
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )


@router.get("/api/v1/rag-artifacts/{rag_id}/suggestions", response_model=RAGSuggestionsResponse, tags=["RAG Lifecycle"])
async def get_rag_suggestions(rag_id: str):
    """Generates document-aware suggested questions for the active version of a RAG artifact."""
    try:
        suggestions = rag_lifecycle_service.get_suggestions(rag_id)
        return RAGSuggestionsResponse(rag_id=rag_id, suggestions=suggestions)
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )


@router.patch("/api/v1/rag-artifacts/{rag_id}", response_model=RAGArtifactRecord, tags=["RAG Lifecycle"])
async def update_rag_artifact(rag_id: str, request: UpdateRAGRequest):
    """Updates metadata, status (e.g. archive), or active version of a RAG Artifact."""
    try:
        return rag_lifecycle_service.update_rag(rag_id, request)
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )


@router.delete("/api/v1/rag-artifacts/{rag_id}", tags=["RAG Lifecycle"])
async def delete_rag_artifact(rag_id: str, force: bool = True, x_account_id: str = Header(default="acc_default", alias="X-Account-ID")):
    """
    Deletes a RAG artifact.
    When user confirms deletion (force=True default), automatically and safely detaches the RAG from all referencing agents.
    If force=False is explicitly specified, fails closed with HTTP 409 if in use by agents.
    """
    try:
        record, affected = rag_lifecycle_service.delete_rag(rag_id, force=force, account_id=x_account_id)
        return {
            "status": "deleted",
            "rag_id": rag_id,
            "name": record.name,
            "unlinked_agents": affected,
        }
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )
    except RAGInUseError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "RAG_IN_USE", "message": str(e), "referencing_agents": e.referencing_agents}},
        )


@router.post("/api/v1/rag-artifacts/{rag_id}/versions", response_model=RAGVersionInfo, status_code=status.HTTP_201_CREATED, tags=["RAG Lifecycle"])
async def register_rag_version(rag_id: str, request: RegisterVersionRequest):
    """Registers a compiled build as a new version of an existing RAG artifact."""
    try:
        return rag_lifecycle_service.register_version(rag_id, request)
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )
    except InvalidRAGPackError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_BUILD", "message": str(e)}},
        )


@router.post("/api/v1/rag-artifacts/{rag_id}/rollback", response_model=RAGArtifactRecord, tags=["RAG Lifecycle"])
async def rollback_rag_version(rag_id: str, target_version_id: str):
    """Rolls back the active version pointer of a RAG artifact to an earlier version."""
    try:
        return rag_lifecycle_service.rollback_version(rag_id, target_version_id)
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "ROLLBACK_FAILED", "message": str(e)}},
        )


@router.get("/api/v1/rag-artifacts/{rag_id}/versions/compare", response_model=VersionComparisonResult, tags=["RAG Lifecycle"])
async def compare_rag_versions(rag_id: str, base_version_id: str, target_version_id: str):
    """
    Computes an objective, descriptive comparison between two versions of a RAG artifact.
    Exposes chunk count, vector count, source differences, and manifest hashes.
    """
    try:
        return rag_lifecycle_service.compare_versions(rag_id, base_version_id, target_version_id)
    except (RAGNotFoundError, RAGVersionNotFoundError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "VERSION_NOT_FOUND", "message": str(e)}},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "COMPARE_FAILED", "message": str(e)}},
        )


@router.get("/api/v1/rag-artifacts/{rag_id}/versions/{version_id}/evaluations", tags=["RAG Lifecycle"])
async def list_version_evaluations(rag_id: str, version_id: str, workspace_id: str = "default"):
    """Lists persisted evaluation benchmark reports specifically captured for a RAG artifact version."""
    try:
        # Validate that the RAG artifact and version exist
        rag_record = rag_lifecycle_service.get_rag(rag_id)
        if not any(v.version_id == version_id for v in rag_record.versions):
            raise RAGVersionNotFoundError(rag_id, version_id)
        return evaluation_service.list_version_reports(rag_id, version_id, workspace_id=workspace_id)
    except (RAGNotFoundError, RAGVersionNotFoundError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NOT_FOUND", "message": str(e)}},
        )


@router.get("/api/v1/rag-artifacts/{rag_id}/evaluations/compare", response_model=VersionEvaluationComparisonResult, tags=["RAG Lifecycle"])
async def compare_version_evaluations(
    rag_id: str,
    base_eval_id: str,
    target_eval_id: str,
    workspace_id: str = "default",
):
    """
    Factual numeric comparison between two evaluation benchmark runs for the specified RAG artifact.
    Enforces same-RAG membership and completed state. Purely objective deltas without promotional language.
    """
    try:
        # Verify RAG existence
        rag_lifecycle_service.get_rag(rag_id)
        return evaluation_service.compare_version_evaluations(
            rag_id=rag_id,
            base_eval_id=base_eval_id,
            target_eval_id=target_eval_id,
            workspace_id=workspace_id,
        )
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )
    except EvaluationNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )
    except InvalidEvaluationParameterError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": e.code, "message": str(e), "details": e.details}},
        )



@router.post("/api/v1/rag-artifacts/{rag_id}/export", tags=["RAG Lifecycle"])
async def export_rag_pack(rag_id: str, version_id: Optional[str] = None):
    """Exports a RAG Knowledge Artifact version to a portable ZIP-based .ragpack bundle."""
    try:
        ragpack_path = rag_lifecycle_service.export_ragpack(rag_id, version_id=version_id)
        return {
            "status": "success",
            "rag_id": rag_id,
            "file_path": str(ragpack_path),
            "file_name": ragpack_path.name,
            "size_bytes": ragpack_path.stat().st_size,
        }
    except RAGNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "RAG_NOT_FOUND", "message": str(e)}},
        )
    except ForbiddenModelWeightError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "FORBIDDEN_MODEL_WEIGHT", "message": str(e)}},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": {"code": "EXPORT_FAILED", "message": str(e)}},
        )


@router.post("/api/v1/rag-artifacts/import", tags=["RAG Lifecycle"])
async def import_rag_pack(file: UploadFile = File(...)):
    """
    Validates and imports a portable .ragpack archive into live storage.
    Enforces path-traversal checks, forbidden model scan, and cryptographic integrity.
    """
    if not file.filename.endswith(".ragpack") and not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_FORMAT", "message": "Expected a .ragpack archive bundle."}},
        )

    temp_path = rag_lifecycle_service.scratch_dir / f"upload_{uuid.uuid4().hex[:8]}_{file.filename}"
    try:
        with open(temp_path, "wb") as f:
            while chunk := await file.read(65536):
                f.write(chunk)

        record = rag_lifecycle_service.import_ragpack(temp_path)
        return {
            "status": "imported",
            "artifact": record,
        }
    except ForbiddenModelWeightError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": {"code": "FORBIDDEN_MODEL_WEIGHT", "message": str(e)}},
        )
    except InvalidRAGPackError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "INVALID_RAGPACK", "message": str(e)}},
        )
    finally:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)





