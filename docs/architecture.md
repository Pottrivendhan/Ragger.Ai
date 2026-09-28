# Ragger.ai — System Architecture

**Version:** 1.0.0-draft  
**Component:** System Architecture Blueprint  
**Target Environment:** Windows 10/11 Desktop

---

## 1. High-Level Architectural Model

Ragger.ai employs a decoupled **Three-Tier Desktop Architecture**:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           ELECTRON RUNTIME                              │
│                                                                         │
│   ┌───────────────────────────────────┐                                 │
│   │        REACT RENDERER             │                                 │
│   │  (Vite + TypeScript + Custom DS)  │                                 │
│   └─────────────────┬─────────────────┘                                 │
│                     │ Secure ContextBridge                              │
│   ┌─────────────────▼─────────────────┐                                 │
│   │      ELECTRON MAIN PROCESS        │                                 │
│   │   - Window Lifecycle Management   │                                 │
│   │   - Python Process Supervisor     │                                 │
│   │   - Native Dialogs & File Shell   │                                 │
│   │   - OS Credential Manager Access  │                                 │
│   └─────────────────┬─────────────────┘                                 │
└─────────────────────┼───────────────────────────────────────────────────┘
                      │ Localhost Loopback HTTP/SSE (Bearer Token Auth)
┌─────────────────────▼───────────────────────────────────────────────────┐
│                     PYTHON RAG ENGINE SERVICE                           │
│                     (FastAPI + Pydantic v2)                             │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │ File Detector│  │   Parsers    │  │  Normalizer  │  │   Sampler   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘  │
│         └─────────────────┼─────────────────┴─────────────────┘         │
│                           ▼                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │Analyzer Agent│  │Recommendation│  │ RAG Builder  │  │  Retriever  │  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬──────┘  │
│         └─────────────────┼─────────────────┴─────────────────┘         │
│                           ▼                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌─────────────┐  │
│  │Vector Store  │  │Model Manager │  │  Evaluator   │  │  Workspace  │  │
│  │ (Local DB)   │  │(GGUF/LocalAI)│  │ (Synthetic)  │  │  Storage    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory & Monorepo Structure

```text
Ragger.ai/
├── docs/                           # Architectural blueprints & product specifications
│   ├── product-specification.md
│   ├── architecture.md
│   ├── rag-architecture.md
│   ├── file-processing.md
│   ├── recommendation-engine.md
│   ├── local-ai.md
│   ├── packaging.md
│   ├── security.md
│   └── development-roadmap.md
│
├── apps/
│   └── desktop/                    # Electron Host Process
│       ├── src/
│       │   ├── main/               # Electron Main process
│       │   │   ├── index.ts        # App entry & lifecycle
│       │   │   ├── supervisor.ts   # Python engine process manager
│       │   │   ├── ipc/            # Native IPC handlers
│       │   │   └── security.ts     # Token generator & sandbox guards
│       │   ├── preload/            # ContextIsolation Preload script
│       │   │   └── index.ts        # contextBridge exposure
│       │   └── shared/             # Desktop-specific types & constants
│       ├── package.json
│       └── tsconfig.json
│
├── frontend/                       # Web & Desktop User Interface
│   ├── src/
│   │   ├── app/                    # Routing, top-level providers
│   │   ├── components/             # Reusable UI component library
│   │   │   ├── layout/             # AppShell, Sidebar, TopBar
│   │   │   ├── feedback/           # StatusBadge, ProgressIndicator, Toast
│   │   │   ├── cards/              # FileCard, RecommendationCard, MetricCard
│   │   │   └── inputs/             # Button, Input, Select, FileDropZone
│   │   ├── design-system/          # Design tokens (colors, typography, spacing)
│   │   ├── features/               # Domain feature modules
│   │   │   ├── workspaces/         # Workspace list, dashboard, creation
│   │   │   ├── ingestion/          # File upload, dropzone, file list
│   │   │   ├── analysis/           # Analysis results, file profiles
│   │   │   ├── recommendation/     # Architecture cards, approval flow
│   │   │   ├── builder/            # Live build progress, stage monitor
│   │   │   ├── chat/               # Grounded chat, citation viewer
│   │   │   ├── evaluation/         # Test reports, quality metrics
│   │   │   └── models/             # Local model catalog & downloader
│   │   ├── services/               # API clients (HTTP + SSE client)
│   │   ├── store/                  # Client state stores (Zustand)
│   │   └── types/                  # TypeScript domain models
│   ├── index.html
│   ├── vite.config.ts
│   └── package.json
│
├── engine/                         # Python RAG Engine Service
│   ├── ragger_engine/
│   │   ├── api/                    # FastAPI routes & middlewares
│   │   │   ├── v1/                 # Versioned route endpoints
│   │   │   └── middleware/         # Auth token & error middlewares
│   │   ├── core/                   # Configuration, logging, lifecycle
│   │   ├── ingestion/              # Ingestion manager & detector
│   │   ├── parsers/                # Format-specific parsers
│   │   ├── normalization/          # DocumentModel & DatasetModel
│   │   ├── sampling/               # Deterministic sample generators
│   │   ├── analyzer/               # Analyzer Agent (Pydantic schema)
│   │   ├── recommendation/         # Deterministic rule engine
│   │   ├── builder/                # RAG build orchestrator
│   │   ├── chunking/               # Chunking strategies
│   │   ├── metadata/               # Metadata enrichment
│   │   ├── embeddings/             # Embedding provider abstractions
│   │   ├── storage/                # Vector store abstractions (Chroma/Lance)
│   │   ├── retrieval/              # Query routing, search, rerank
│   │   ├── generation/             # LLM provider abstractions
│   │   ├── evaluation/             # Synthetic QA & quality evaluation
│   │   ├── models/                 # Local GGUF/ONNX model manager
│   │   └── workspace/              # Workspace persistence & metadata
│   ├── tests/                      # Pytest suite
│   ├── pyproject.toml
│   └── requirements.txt
│
└── packaging/                      # Build & Installer Automation
    ├── build_engine.py             # Script to freeze Python engine via PyInstaller
    ├── electron-builder.yml        # Electron packaging configuration
    └── nsis/                       # Custom NSIS scripts for single EXE setup
```

---

## 3. Electron ↔ Python Engine Lifecycle & Process Supervision

### 3.1 Startup Sequence
1. **Electron Main Starts**: Initializes logging, checks single-instance lock.
2. **Security Token Generation**: Electron generates a cryptographically secure 256-bit random hex string (`RAGGER_API_TOKEN`).
3. **Port Allocation**: Electron allocates an available ephemeral loopback port (`127.0.0.1:0`).
4. **Python Process Spawn**:
   - In Development: Electron spawns `python -m ragger_engine.main --port <PORT> --token <TOKEN>`.
   - In Production: Electron spawns `resources/engine/ragger-engine.exe --port <PORT> --token <TOKEN>`.
5. **Health Handshake**:
   - Electron polls `http://127.0.0.1:<PORT>/health` with a backoff policy (max 15 seconds, 250ms interval).
   - Python engine responds with `{"status": "healthy", "version": "1.0.0", "pid": 12345}`.
6. **Window Launch**: Once health is verified, Electron loads the Vite UI, injecting connection parameters into the renderer via the secure `contextBridge`.

### 3.2 Process Teardown & Graceful Shutdown
1. When Electron receives `before-quit` or `window-all-closed`:
2. Sends a graceful shutdown notification to Python (`POST /v1/system/shutdown` with auth token).
3. Waits up to 3000ms for clean resource cleanup (closing vector databases, unmapping models).
4. If the child process is still running after timeout, Electron sends `SIGTERM` / `TerminateProcess` to avoid zombie Python processes.

---

## 4. Communication & IPC Architecture

### 4.1 Security Boundaries
- `nodeIntegration: false` and `contextIsolation: true` are strictly enforced on the renderer window.
- The renderer communicates exclusively via `window.raggerAPI`, which exposes strictly typed RPC channels.
- Frontend talks directly to the local Python engine over loopback HTTP using the injected bearer token, keeping high-throughput streaming (embeddings, chunk streams, model downloads) off the Electron IPC bus.

### 4.2 Streaming Events Architecture
- **Build Progress & Model Downloads**: Handled via Server-Sent Events (SSE) from the Python engine (`GET /v1/workspaces/{id}/build/stream`, `GET /v1/models/downloads/stream`).
- SSE provides lightweight, one-way real-time telemetry with automatic reconnection and sequence numbering.

---

## 5. Local State & Storage Hierarchy

All application data is isolated under the standard Windows user application directory:

```text
%LOCALAPPDATA%\RaggerAI\
├── config.json                     # Global app preferences & provider configs
├── models/                         # Local AI model weights & manifests
│   ├── manifests/                  # JSON metadata for installed models
│   ├── analyzer/                   # Dedicated analyzer model weights
│   ├── embeddings/                 # Sentence-transformers / ONNX models
│   └── generation/                 # User-downloaded chat LLMs (GGUF)
├── workspaces/                     # User workspace directories
│   └── <workspace_uuid>/
│       ├── workspace.json          # Workspace configuration & metadata
│       ├── raw_sources/            # Immutable copies of uploaded files
│       ├── parsed/                 # Serialized Document/Dataset models
│       ├── samples/                # Extracted analysis samples
│       ├── analysis/               # Analyzer Agent output & file profiles
│       ├── recommendation.json     # Recommended architecture & rule audit
│       ├── approved_config.json    # Immutable snapshot of user approval
│       ├── vector_store/           # Local vector index files (Chroma/LanceDB)
│       └── evaluation/             # Evaluation datasets & test results
└── logs/                           # Rolling diagnostic log files
    ├── electron.log
    └── engine.log
```

---

## 6. Centralized Error Handling & Taxonomy

All Python engine errors emit a standard RFC 7807 Problem Details JSON payload:

```json
{
  "type": "https://ragger.ai/errors/PARSE_UNSUPPORTED_ENCODING",
  "title": "Unsupported File Encoding",
  "status": 422,
  "detail": "The file 'quarterly_report.txt' contains non-standard binary encoding that could not be normalized.",
  "instance": "/v1/workspaces/ws-101/sources/src-202/parse",
  "code": "PARSE_UNSUPPORTED_ENCODING",
  "recoverable": false,
  "suggested_action": "Ensure the text file is encoded in standard UTF-8 or ASCII format."
}
```

### Domain Error Code Prefixes:
- `INGEST_*`: Upload, checksum verification, disk quota, file lock failures.
- `PARSE_*`: Format parsing, corrupted headers, password-protected files.
- `NORM_*`: Structural AST transformation, table extraction errors.
- `ANALYZE_*`: Schema validation failures, LLM provider communication errors.
- `BUILD_*`: Chunking boundaries, embedding generation, vector store indexing failures.
- `RETRIEVE_*`: Index missing, empty result sets, query translation errors.
- `MODEL_*`: Download interrupted, checksum mismatch, insufficient RAM/VRAM.

---

## 7. Implementation State vs. Planned Roadmap

### 7.1 Implemented (Phase 1: Foundation)
- [x] **Monorepo Structure**: Root npm workspaces (`apps/desktop`, `frontend`) and Python `engine`.
- [x] **Electron Process Supervisor** (`PythonProcessSupervisor`):
  - Dynamic loopback port allocation (`127.0.0.1:<dynamic_port>`).
  - Ephemeral 256-bit cryptographic bearer token generation (`RAGGER_API_TOKEN`).
  - Python child process spawn, health polling (`/health`), and authenticated loopback handshake (`/api/v1/health`).
  - Clean process tree teardown on Windows (`taskkill /T /F`) with zero orphan processes.
- [x] **Python FastAPI Engine**:
  - `GET /health` (unauthenticated liveness probe).
  - `GET /api/v1/health` (Bearer token authenticated health check with real PID).
  - `GET /api/v1/runtime` (Bearer token authenticated diagnostic telemetry, zero leaked secrets).
  - `TokenAuthMiddleware` with constant-time comparison (`secrets.compare_digest`).
  - Structured logging with automatic token redaction filter.
- [x] **Secure IPC & Context Isolation**:
  - `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`.
  - Token kept strictly in Electron Main memory, never exposed to React renderer.
  - Renderer invokes `window.ragger.engine.*` which proxies authenticated requests through Electron Main.
- [x] **Real Developer Health Check UI**:
  - Live indicators for Frontend, Electron Host, Python Engine, FastAPI Service, and Authenticated Loopback.
  - Real unmocked PID, dynamic port, platform, and Python version display.
  - Reactive error state detection upon engine failure or termination.
- [x] **Automated Tests**:
  - Pytest suite testing health endpoints and token authentication (100% pass).
  - End-to-end integration test verifying supervisor lifecycle, port allocation, token auth, 401 rejection, and shutdown (100% pass).

### 7.2 Planned (Subsequent Phases)
- [ ] **Phase 2**: Custom Ragger Design System (light theme, bespoke component tokens).
- [ ] **Phase 3**: Desktop Application Shell & Local Workspace Persistence.
- [ ] **Phase 4**: Ingestion Subsystem (14 file formats, `FileDetector`, checksums).
- [ ] **Phase 5**: Format Parsers & Structural Normalization (`DocumentModel` / `DatasetModel`).
- [ ] **Phase 6**: Deterministic Sample Generator (`AnalysisSample`).
- [ ] **Phase 7**: Analyzer Agent (Pydantic schema observer).
- [ ] **Phase 8**: Deterministic Recommendation Engine (Rule registry, product explanations).
- [ ] **Phase 9**: User Approval & Frozen Build Configuration Gate.
- [ ] **Phases 10–20**: RAG Builder, Retrieval, Chat, Evaluation, Model Manager, Packaging, QA.

