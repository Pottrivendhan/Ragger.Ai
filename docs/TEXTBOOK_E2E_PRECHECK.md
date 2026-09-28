# Phase A — Pre-Check & Architecture Inspection Report

**Project Root:** `C:\Users\POTTRIVENDHAN\Ragger.ai`  
**Target Ingestion Source:** `D:\D Downloads\Class_10_English_2024_Edition-www.tntextbooks.in.pdf` (67.09 MB / 224 pages)  
**Inspection Date:** September 18, 2026  

---

## 1. Current Architecture Overview

Ragger.ai is structured as a three-tier local desktop application:
1. **Frontend**: React 18 + TypeScript + Vite (`frontend/`).
2. **Desktop Shell**: Electron 32 Main Process with Node.js supervisor (`apps/desktop/`).
3. **Engine Runtime**: Python 3.12 + FastAPI with PyInstaller `onedir` frozen capability (`engine/`).

### Communication Flow:
```text
React Renderer (UI) ──(Electron IPC via window.ragger)──► Electron Main (Supervisor)
                                                                 │
                                                       (Loopback HTTP with 256-bit Bearer Token)
                                                                 ▼
                                                        Python FastAPI Engine (127.0.0.1:<ephemeral>)
```

---

## 2. Current API Endpoints

All endpoints are hosted on the internal FastAPI engine under `http://127.0.0.1:<port>` with `Authorization: Bearer <token>`:

| Subsystem | Method | Path | Description |
| :--- | :---: | :--- | :--- |
| **Diagnostics** | `GET` | `/health` | Unauthenticated loopback liveness probe |
| **Diagnostics** | `GET` | `/api/v1/health` | Authenticated process health & PID confirmation |
| **Diagnostics** | `GET` | `/api/v1/runtime` | Runtime environment diagnostics (Python, platform) |
| **Ingestion** | `POST` | `/api/v1/ingestion/detect` | Multi-signal file format detection |
| **Ingestion** | `POST` | `/api/v1/ingestion/parse` | AST/structural block extraction |
| **Ingestion** | `POST` | `/api/v1/ingestion/ingest` | End-to-end ingest, hash, parse, normalize & sample |
| **Ingestion** | `GET` | `/api/v1/ingestion/sources` | List all registered source records in registry |
| **Analyzer** | `POST` | `/api/v1/analysis/file` | Single-file observational analysis profile |
| **Analyzer** | `POST` | `/api/v1/analysis/workspace` | Deterministic workspace corpus synthesis |
| **Analyzer** | `GET` | `/api/v1/analysis/profiles` | List cached file analysis profiles |
| **Analyzer** | `GET` | `/api/v1/analysis/workspace` | Get current workspace knowledge profile |
| **Analyzer** | `GET` | `/api/v1/analysis/providers` | List available analysis providers |
| **Recommendation** | `POST` | `/api/v1/recommendation/evaluate` | Run rule-based architecture recommendation |
| **Recommendation** | `GET` | `/api/v1/recommendation/current` | Get cached recommendation result |
| **Recommendation** | `GET` | `/api/v1/recommendation/architectures`| List 5 supported RAG architecture specifications |
| **Recommendation** | `POST` | `/api/v1/recommendation/approve` | User approval gate for RAG build configuration |
| **Recommendation** | `GET` | `/api/v1/recommendation/approved` | Get current approved build configuration |
| **Recommendation** | `GET` | `/api/v1/recommendation/validate-build`| Validate approval prerequisite checks |
| **Builder** | `POST` | `/api/v1/builder/start` | Trigger background RAG build execution |
| **Builder** | `GET` | `/api/v1/builder/progress` | Poll active build progress & status |
| **Builder** | `GET` | `/api/v1/builder/events` | SSE streaming build events |
| **Builder** | `GET` | `/api/v1/builder/manifest` | Get active build manifest |
| **Builder** | `POST` | `/api/v1/builder/cancel` | Cancel active build execution |
| **Retrieval** | `POST` | `/api/v1/retrieval/query` | Query active vector index for retrieved chunks |
| **Retrieval** | `GET` | `/api/v1/retrieval/status` | Active retrieval engine status & pointer |
| **Retrieval** | `POST` | `/api/v1/retrieval/reload` | Force atomic pointer reload of active build |
| **Chat** | `POST` | `/api/v1/chat/generate` | Grounded chat completion with citation validation |
| **Chat** | `POST` | `/api/v1/chat/stream` | Token streaming grounded generation via SSE |
| **Chat** | `POST` | `/api/v1/chat/cancel/{session_id}` | Cancel active streaming generation |
| **Chat** | `GET` | `/api/v1/chat/sessions` | List all persisted chat sessions |
| **Chat** | `GET` | `/api/v1/chat/sessions/{session_id}` | Get specific chat session history |
| **Chat** | `DELETE`| `/api/v1/chat/sessions/{session_id}` | Delete chat session |
| **Chat** | `GET` | `/api/v1/chat/config` | Get active generation configuration |
| **Chat** | `POST` | `/api/v1/chat/config` | Update generation configuration |
| **Evaluation** | `POST` | `/api/v1/evaluation/run` | Trigger synthetic probe quality evaluation |
| **Evaluation** | `GET` | `/api/v1/evaluation/progress/{eval_id}` | Poll evaluation run progress |
| **Evaluation** | `GET` | `/api/v1/evaluation/reports` | List evaluation benchmark reports |
| **Evaluation** | `GET` | `/api/v1/evaluation/config` | Get evaluation judge configuration |
| **Models** | `GET` | `/api/v1/models/hardware` | Hardware capability & tier probe |
| **Models** | `GET` | `/api/v1/models/catalog` | Curated local model catalog |
| **Models** | `GET` | `/api/v1/models/installed` | Inventory of installed models |
| **Models** | `POST` | `/api/v1/models/download/{model_key}` | Start resumable direct or Ollama model download |
| **Models** | `GET` | `/api/v1/models/download/{model_key}/progress` | Poll download progress |
| **Models** | `POST` | `/api/v1/models/{model_key}/activate` | Activate installed model for generation/evaluation |

---

## 3. Current Storage Paths

Storage resolution is currently decentralized across multiple modules:
- `ingestion/registry.py`: Checks `RAGGER_STORAGE_DIR`, falls back to `%LOCALAPPDATA%\RaggerAI\storage`.
- `recommendation/service.py`: Checks `RAGGER_STORAGE_DIR`, falls back to `%LOCALAPPDATA%\RaggerAI\storage`.
- `analyzer/service.py`: Inherits from `ingestion/registry.py`.
- `models/service.py`: Takes `storage_dir` parameter and creates `storage_dir / "models"`.

### Data Artifact File Layout:
```text
<storage_root>/
├── sources_registry.json           # Ingested file metadata & SHA-256 hashes
├── analysis_profiles.json          # FileAnalysisProfile records per source
├── workspace_profile.json          # Synthesized WorkspaceKnowledgeProfile
├── recommendation_result.json      # Latest architecture recommendation
├── approved_build_config.json      # ApprovedBuildConfig with config_hash
├── builds/                         # Build artifacts
│   └── <build_id>/
│       ├── manifest.json           # BuildManifest with chunk counts & hashes
│       ├── chunks.jsonl            # Extracted document/dataset chunks
│       └── vectors/                # Vector store index (local_flat_index / lancedb)
├── active_build.json               # Atomic pointer to currently active build
├── chat_sessions/                  # Persisted conversation histories & citations
│   └── <session_id>.json
├── generation_config.json          # Generation provider & model settings
├── evaluation_config.json          # Evaluation judge model configuration
└── models/                         # Phase 9 Model Manager weights
    ├── embedding/                  # ONNX embedding models
    ├── generation/                 # GGUF generation models
    └── judge/                      # GGUF judge models
```

---

## 4. Current Electron IPC Flow

The Electron preload script (`apps/desktop/src/preload/index.ts`) exposes APIs to `window.ragger`:
- `window.ragger.engine`: `getStatus`, `getHealth`, `getRuntime`, `restart`
- `window.ragger.ingestion`: `openFileDialog`, `detectFile`, `ingestFile`, `listSources`
- `window.ragger.analysis`: `analyzeFile`, `synthesizeWorkspace`, `getProfiles`, `getWorkspaceProfile`
- `window.ragger.recommendation`: `evaluate`, `getCurrent`, `listArchitectures`, `approve`, `getApproved`
- `window.ragger.builder`: `start`, `getProgress`, `getManifest`, `cancel`
- `window.ragger.retrieval`: `query`, `getStatus`, `reload`
- `window.ragger.chat`: `generate`, `cancel`, `getSessions`, `getSession`, `deleteSession`, `getConfig`
- `window.ragger.evaluation`: `run`, `getProgress`, `getReports`, `cancel`, `getConfig`
- `window.ragger.models`: `getHardware`, `getCatalog`, `getInstalled`, `startDownload`, `pauseDownload`, etc.

The Electron Main process (`apps/desktop/src/main/ipc/*`) attaches the session bearer token and translates each IPC call to loopback HTTP requests to `127.0.0.1:<port>`.

---

## 5. Current Browser-Mode Limitations

When the React frontend is loaded directly in a web browser at `http://localhost:5173` without Electron:
1. `window.ragger` is **undefined**.
2. Service clients (`ingestionClient.ts`, `analysisClient.ts`, `builderClient.ts`, etc.) throw hard errors (`... is only available in Electron desktop.`).
3. The UI becomes completely non-reactive with dead buttons and unhandled rejections.
4. Vite dev server (`vite.config.ts`) has no reverse proxy configured for `/api/*`.
5. The frontend has no fallback to query the dynamic engine port directly when outside Electron.

---

## 6. Current Model Configuration

The Phase 9 Model Catalog (`engine/ragger_engine/models/catalog.py`) defines 9 curated models:
- **Direct ONNX Embedding**: `bge-small-en-v1.5:onnx:default-v1` (133.4 MB, 384-dim, FP32).
- **Direct GGUF Generation**: `qwen2.5-1.5b-instruct:gguf:q4_k_m-v1` (986 MB, Q4_K_M).
- **Direct GGUF Generation**: `llama3.2-3b-instruct:gguf:q4_k_m-v1` (2.01 GB, Q4_K_M).
- **Direct GGUF Judge**: `qwen2.5-1.5b-judge:gguf:q4_k_m-v1` (986 MB, Q4_K_M).
- **Ollama Generation/Judge**: `llama3.2:3b`, `qwen2.5:1.5b`, `qwen2.5:7b`, `mistral:7b`, `llama3.2:3b-judge`.
- **Testing Providers**: `test_deterministic` for embeddings (384-dim) and LLM generation (gated by `RAGGER_ALLOW_TEST_EMBEDDINGS=1` and `RAGGER_ALLOW_TEST_LLM=1`).

---

## 7. Current RAG Build Lifecycle

The RAG build process follows a strict 7-stage state machine:
```text
1. INGESTION       : Parses raw file into DocumentModel/DatasetModel, records SourceRecord with SHA-256.
2. ANALYSIS        : Extracts structural facts (blocks, headings, word count, modality ratio).
3. RECOMMENDATION  : Rule engine evaluates corpus properties and outputs recommended ArchitectureSpec.
4. USER APPROVAL   : User reviews chunking/retrieval parameters and submits ApprovedBuildConfig with config_hash.
5. CHUNKING        : Deterministic chunking generates chunks.jsonl with reproducible blk/chk IDs.
6. EMBEDDINGS      : Generates dense vectors using approved provider (local_onnx / ollama / test_deterministic).
7. VECTOR INDEXING : Creates vector index (local_flat_index or lancedb), generates BuildManifest, and updates active_build.json.
```
- **FAISS is strictly forbidden** per Phase 5/6 architectural contracts.
- **Retrieval & Generation** are read-only consumers against `active_build.json`.
