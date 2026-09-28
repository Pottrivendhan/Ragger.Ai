# Ragger.ai — Master Development Roadmap (Phases 0–20)

**Version:** 1.0.0-draft  
**Component:** Engineering Execution Plan & Milestone Verification  
**Strategy:** Phased, Verified, Non-Monolithic Implementation

---

## 1. Phased Execution Principles

To prevent architectural drift, brittle demo implementations, and fake progress indicators, Ragger.ai is engineered in strict, decoupled phases. 

**Cardinal Rule of Execution**:
> Each phase must be verified against its explicit verification criteria before proceeding to the subsequent phase. No forward-leaping into future features.

```text
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ... ──► Phase 20
(Arch)      (Found.)    (Design)    (Shell)     (Ingest)         (Polish)
```

---

## 2. Detailed Phase Breakdown & Exit Gates

### Phase 0: Product Specification & Architecture Foundation *(Current)*
- **Objective**: Establish the product constitution, technical specifications, and architectural blueprints.
- **Deliverables**: Complete documentation suite in `/docs/`.
- **Exit Gate**: All 9 architecture documents created and reviewed. Zero premature source code written.

---

### Phase 1: Foundation (Application Scaffold & Supervised Runtime)
- **Objective**: Establish the Electron + React + Vite + Python FastAPI monorepo with supervised process lifecycles.
- **Key Deliverables**:
  - Monorepo folder structure (`apps/desktop`, `frontend`, `engine`).
  - Python virtual environment / dependency configuration (`pyproject.toml`).
  - Electron main process supervisor with dynamic loopback port and token authentication.
  - Bidirectional health check screen verifying Electron $\leftrightarrow$ Frontend $\leftrightarrow$ Python $\leftrightarrow$ FastAPI connectivity.
- **Exit Gate**: Launching `npm run dev` boots all three tiers; health check passes with real live process IDs.

---

### Phase 2: Ragger.ai Custom Design System
- **Objective**: Implement a bespoke, light-theme, high-trust design system for technical professionals.
- **Key Deliverables**:
  - Custom design tokens (typography, spacing, borders, radius, shadows, transitions).
  - Core component library: `AppShell`, `Sidebar`, `TopBar`, `Button`, `FileDropZone`, `FileCard`, `StatusBadge`, `ProgressIndicator`, `RecommendationCard`, `MetricCard`, `DataTable`.
  - Realistic state-driven animations (no fake loops).
- **Exit Gate**: Design system storybook or component gallery renders cleanly in light theme with 60 FPS transitions.

---

### Phase 3: Desktop Application Shell & Workspace State
- **Objective**: Build navigation routing and local workspace persistence.
- **Key Deliverables**:
  - Top-level routing: `Home`, `Workspaces`, `Create RAG`, `Models`, `Settings`.
  - Workspace sub-navigation: `Overview`, `Sources`, `Analysis`, `Architecture`, `Build`, `Test`, `Chat`, `API`.
  - Workspace state model and local disk persistence under `%LOCALAPPDATA%\RaggerAI\workspaces\`.
- **Exit Gate**: User can create, view, switch, and delete workspaces with state persisted across app restarts.

---

### Phase 4: File Ingestion Subsystem
- **Objective**: Robust file ingestion supporting 14 heterogeneous formats.
- **Key Deliverables**:
  - `FileDetector` with 3-layer validation (extension, MIME, magic bytes).
  - Drag-and-drop & file browser with multi-file selection.
  - SHA-256 duplicate detection and per-file validation.
  - Source registry persisting file records in workspace metadata.
- **Exit Gate**: Ingestion of valid files succeeds with accurate metadata; corrupted or disguised files are flagged with granular error badges.

---

### Phase 5: Format-Specific Parsing & Normalization
- **Objective**: Convert raw files into standardized structural models without flattening.
- **Key Deliverables**:
  - 14 format parsers (PDF, DOCX, DOC, TXT, MD, PPTX, CSV, XLSX, XLS, TSV, JSON, XML, HTML, EPUB).
  - `DocumentModel` (sections, headings, paragraphs, tables, lists).
  - `DatasetModel` (columns, data types, row counts, statistical bounds).
- **Exit Gate**: Unit tests parse real sample files of all 14 formats, verifying structural integrity and zero data loss.

---

### Phase 6: Representative Sample Generator
- **Objective**: Extract compact, deterministic samples from large files for LLM analysis.
- **Key Deliverables**:
  - `SampleGenerator` and `SamplePolicy` abstractions.
  - Document policy: Head, middle, tail, outline, tables (~4,000 token budget).
  - Dataset policy: Schema, dimension stats, head 10, random 10, tail 5 (~3,000 token budget).
- **Exit Gate**: Sample extraction runs deterministically in < 200ms per file, staying strictly within token caps.

---

### Phase 7: Analyzer Agent
- **Objective**: LLM-powered structural observation producing strict Pydantic profiles.
- **Key Deliverables**:
  - `AnalyzerAgent` with strict Pydantic output schema (`FileAnalysisProfile`).
  - Provider abstraction (`LLMProvider`) supporting Local and Cloud backends.
  - Automated schema repair retry loop.
- **Exit Gate**: Analyzer returns valid `FileAnalysisProfile` JSON on sample inputs; invalid responses trigger retry or graceful failure.

---

### Phase 8: Deterministic Recommendation Engine
- **Objective**: Rule-based selection of optimal RAG architecture with predefined explanations.
- **Key Deliverables**:
  - `RuleRegistry` with deterministic rules (`RULE_TABULAR_DOMINANT`, `RULE_HIERARCHICAL_LONGFORM`, etc.).
  - Cross-source `WorkspaceKnowledgeProfile` aggregation.
  - Product-controlled explanation catalog.
- **Exit Gate**: Unit tests verify that specific file profile combinations deterministically trigger expected architectures and explanations.

---

### Phase 9: User Review & Approval Workflow
- **Objective**: Require explicit user review and configuration freezing before building.
- **Key Deliverables**:
  - Recommendation review screen with detected signals, why-recommended explanation, and tradeoffs.
  - Customization drawer (chunk size, embedding provider, top-k).
  - Creation of immutable `ApprovedBuildConfig` snapshot on user click.
- **Exit Gate**: Builder cannot be triggered without user approval; modifying settings updates the frozen config.

---

### Phase 10: RAG Builder
- **Objective**: Execute the end-to-end RAG construction pipeline with observable progress.
- **Key Deliverables**:
  - Modular `ChunkingStrategy`, `MetadataGenerator`, `EmbeddingProvider`, and `VectorStore`.
  - Real-time build telemetry via Server-Sent Events (SSE).
  - Resumable build checkpoints.
- **Exit Gate**: Ingested files are chunked, embedded, and indexed into local vector storage; UI displays real stage metrics.

---

### Phase 11: Retrieval Engine
- **Objective**: Modular multi-strategy retrieval system.
- **Key Deliverables**:
  - `QueryProcessor`, `QueryRouter`, `DenseRetriever`, `BM25Retriever`, and `HybridRetriever`.
  - Reciprocal Rank Fusion (RRF) for hybrid search.
  - Reranker abstraction (`FlashRank` / cross-encoder).
- **Exit Gate**: Retrieval tests return relevant chunks with similarity scores and page/section breadcrumbs in < 150ms.

---

### Phase 12: Grounded RAG Chat
- **Objective**: Interactive chat interface with strict citation attribution.
- **Key Deliverables**:
  - Context assembler with strict grounding system prompt.
  - Chat UI with streaming responses and inline citation badges `[Source, Page]`.
  - Expandable Retrieval Inspector showing retrieved chunks and similarity scores.
- **Exit Gate**: Chat answers questions accurately using retrieved context; queries without evidence trigger polite insufficiency disclaimer.

---

### Phase 13: Automated Evaluation
- **Objective**: Automated health checks and quality benchmarking.
- **Key Deliverables**:
  - Synthetic question generator.
  - Retrieval accuracy metrics (Hits@K, MRR).
  - Grounding/faithfulness scoring.
- **Exit Gate**: Built RAG generates a Quality Report Card distinguishing retrieval success from generation accuracy.

---

### Phase 14: Local AI Model Manager
- **Objective**: Integrated manager for downloading, verifying, and deleting local model weights.
- **Key Deliverables**:
  - Model catalog (GGUF / ONNX models).
  - Chunked HTTP downloader with pause, resume, cancel, and SHA-256 verification.
  - Hardware probing (RAM, VRAM, CPU instruction sets).
- **Exit Gate**: User can download a 1.5B GGUF model; pausing, resuming, and checksum verification succeed.

---

### Phase 15: Cloud LLM Provider Integration
- **Objective**: Secure integration with external AI APIs.
- **Key Deliverables**:
  - Provider adapters for OpenAI, Anthropic, Groq, and Cohere.
  - Secure credential storage using Windows Credential Manager (DPAPI).
- **Exit Gate**: Users can input API keys, which are stored encrypted and used for cloud completions when enabled.

---

### Phase 16: Workspace Management & Multi-Project Support
- **Objective**: Full lifecycle management for multiple concurrent workspaces.
- **Key Deliverables**:
  - Workspace CRUD, duplication, renaming, and archiving.
  - Export/import workspace configurations.
- **Exit Gate**: Multiple distinct workspaces operate independently without state collision.

---

### Phase 17: Security & Reliability Hardening
- **Objective**: Comprehensive security review and boundary protection.
- **Key Deliverables**:
  - Token-authenticated loopback IPC verification.
  - DOMPurify sanitization on rendered chat and markdown.
  - Decompression bomb and path traversal test suite.
- **Exit Gate**: Penetration test suite confirms zero path traversal, XSS, or unauthorized loopback execution.

---

### Phase 18: Windows Production Packaging
- **Objective**: Single standalone installer (`RaggerAI-Setup.exe`).
- **Key Deliverables**:
  - PyInstaller `onedir` frozen Python runtime.
  - NSIS installer configured via `electron-builder`.
  - Standalone verification script.
- **Exit Gate**: Application installs and runs on a fresh Windows Sandbox with zero pre-installed developer tools.

---

### Phase 19: Production QA & End-to-End Stress Testing
- **Objective**: Automated testing of edge cases and high-stress scenarios.
- **Key Deliverables**:
  - Automated test suite covering all 14 file formats, corrupted files, and missing models.
  - Stress testing with 50+ mixed files.
- **Exit Gate**: 100% pass rate on integration test suite with graceful error recovery.

---

### Phase 20: Product Polish & UX Refinement
- **Objective**: Elevate the product to commercial enterprise standards.
- **Key Deliverables**:
  - Onboarding walkthrough, educational tooltips explaining RAG concepts.
  - Full keyboard navigation and accessibility standards compliance.
  - Performance optimization and UI micro-interaction polish.
- **Exit Gate**: Complete user journey from launch to query feels responsive, intuitive, and professional.
