# Ragger.ai — Product Specification

**Version:** 1.0.0-draft  
**Status:** Architecture Blueprint (Phase 0)  
**Classification:** Internal Product Constitution  
**Target Environment:** Windows 10/11 Desktop (Electron + Python Runtime)

---

## 1. Executive Summary & Product Vision

### 1.1 Tagline
> **“Turn your data into an intelligent knowledge system.”**

### 1.2 Core Thesis
Ragger.ai is a **knowledge engineering and Retrieval-Augmented Generation (RAG) creation platform**, not merely an interactive chatbot or a superficial PDF viewer. 

In conventional AI tooling, creating an effective RAG system requires deep technical knowledge: determining chunk size, chunk overlap, choosing embedding models, configuring vector database indexing parameters, structuring metadata schemas, writing retrieval rerankers, and designing query routers. Non-expert users and domain researchers cannot effectively navigate these technical tradeoffs, leading to either brittle DIY pipelines or lowest-common-denominator "chat with PDF" toys that fail on real-world heterogeneous datasets.

Ragger.ai inverts this paradigm:
1. Users upload **heterogeneous raw data** (documents, spreadsheets, presentations, structured files).
2. Ragger.ai parses and normalizes each file into a rich structural representation.
3. Ragger.ai deterministically extracts a representative sample.
4. An **Analyzer Agent** observes structural, linguistic, and statistical properties of each source, returning strict machine-readable profiles.
5. A deterministic, rule-based **Recommendation Engine** analyzes the cross-source profile and selects an optimal RAG architecture with human-understandable, product-controlled explanations.
6. The user **reviews, inspects, and approves** (or modifies) the recommended architecture.
7. Upon explicit user approval, the **RAG Builder** executes the build pipeline: normalization, chunking, metadata extraction, embedding generation, vector indexing, and retrieval tuning.
8. The resulting RAG is automatically validated and published with grounded chat, citation tracking, and a local API endpoint.

---

## 2. Product Principles & Constitution

1. **Explainability**: The system must explain *why* an architecture, chunking strategy, or retrieval policy was chosen using transparent, human-readable logic, never opaque LLM hallucinations.
2. **User Control**: RAG construction must **never** start automatically. The user is in complete command and must explicitly approve or customize recommendations.
3. **Modular Architecture**: Ingestion, parsing, normalization, profiling, recommendation, chunking, embedding, vector storage, retrieval, and generation must exist as decoupled interfaces.
4. **Local-First & Offline Capable**: The core platform runs locally on the user's Windows machine. In local mode, zero document, sample, or query data leaves the machine. Internet access is utilized solely when the user explicitly chooses to download a model from the Model Manager, after which the machine can return to being fully air-gapped.
5. **Deterministic Decision Making**: The Analyzer Agent is an *observer*, not a decision-maker. Architecture selection is handled strictly by deterministic rule sets.
6. **Real Processing, Zero Placeholders**: No fake spinners, no artificial delays, no hard-coded mock data. Every progress bar, stage indicator, and status badge must map to real system state.
7. **Observable Execution**: Every stage of ingestion, analysis, and building must emit structured events and diagnostic logs.
8. **Testability & Validation**: Built RAG systems must undergo automated health and retrieval evaluation before being declared ready.
9. **Single-Executable Distribution**: The consumer product must install via a single Windows installer (`RaggerAI-Setup.exe`) containing the desktop application and Python runtime, without requiring pre-installed Node.js, Python, Git, or compilers.
10. **Hardware-Aware Model Decoupling**: AI model weights are *never* bundled into the installer. They are managed and downloaded post-installation via a dedicated Model Manager.

---

## 3. Supported File Format Matrix (v1)

| Category | Extensions | MIME Types / Identifiers | Ingestion Parser | Structural Model |
| :--- | :--- | :--- | :--- | :--- |
| **Documents** | `.pdf` | `application/pdf` | `PDFParser` | DocumentModel (Pages, Sections, Tables) |
| | `.docx` | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `DOCXParser` | DocumentModel (Heading Tree, Paragraphs, Tables) |
| | `.doc` | `application/msword` | `DOCParser` | DocumentModel (Text, Paragraphs) |
| | `.txt` | `text/plain` | `TXTParser` | DocumentModel (Raw text, auto-encoding) |
| | `.md` | `text/markdown`, `text/x-markdown` | `MarkdownParser` | DocumentModel (AST Headings, Code, Lists) |
| | `.pptx` | `application/vnd.openxmlformats-officedocument.presentationml.presentation` | `PPTXParser` | DocumentModel (Slides, Notes, Shapes, Tables) |
| | `.epub` | `application/epub+zip` | `EPUBParser` | DocumentModel (Chapters, Spine, TOC) |
| **Data / Tabular**| `.csv` | `text/csv`, `application/csv` | `CSVParser` | DatasetModel (Columns, Types, Rows, Stats) |
| | `.tsv` | `text/tab-separated-values` | `TSVParser` | DatasetModel (Columns, Types, Rows, Stats) |
| | `.xlsx` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `XLSXParser` | DatasetModel (Sheets, Columns, Types, Stats) |
| | `.xls` | `application/vnd.ms-excel` | `XLSParser` | DatasetModel (Sheets, Columns, Types, Stats) |
| **Structured / Web**| `.json` | `application/json` | `JSONParser` | Document/Dataset Model (Schema depending on layout) |
| | `.xml` | `application/xml`, `text/xml` | `XMLParser` | DocumentModel (Element Hierarchy, Attributes) |
| | `.html`, `.htm` | `text/html` | `HTMLParser` | DocumentModel (DOM Extraction, Stripped Nav/Boilerplate) |

*Note: Raw image files (`.png`, `.jpg`) and direct database connectors are reserved for post-v1 extensions (OCR module and enterprise connectors).*

---

## 4. End-to-End User Experience & Flow

```text
[1. Create Workspace]
         │
         ▼
[2. Ingest Files] ── Drag & Drop / File Browser (Multi-file, duplicate check)
         │
         ▼
[3. File Intelligence] ── Extension + Magic Byte Validation ──► Parsers ──► Normalization
         │
         ▼
[4. Representative Sampling] ── Deterministic Sample Policies (Doc/Data)
         │
         ▼
[5. Source Analysis] ── Analyzer Agent (Pydantic-validated observations)
         │
         ▼
[6. Architecture Recommendation] ── Deterministic Rule Engine + Predefined Explanations
         │
         ▼
[7. User Review & Approval] ── [Approve & Build] OR [Customize Settings]
         │
         ▼
[8. RAG Builder Execution] ── Normalization ──► Chunking ──► Embedding ──► Indexing
         │
         ▼
[9. Automated Health & Evaluation] ── Synthetic queries, retrieval tests, grounding checks
         │
         ▼
[10. Published RAG Workspace] ── Grounded Chat, Retrieval Inspector, Local API Endpoint
```

### Stage Details:
1. **Workspace Creation**: A named container with local directory isolation (`%LOCALAPPDATA%\RaggerAI\workspaces\<workspace_id>`).
2. **File Ingestion**: Immediate checksum computation (SHA-256), extension and header inspection, virus/safety heuristic checks, storage in workspace source cache.
3. **Parsing & Normalization**: Extraction into standardized AST-like `DocumentModel` or tabular `DatasetModel`.
4. **Sample Generation**: Extraction of head, tail, middle, and structural outline within a strict token budget (~4,000 tokens).
5. **Analyzer Agent**: Evaluates density, hierarchy, domain, tabular presence, language, and potential retrieval bottlenecks.
6. **Recommendation Engine**: Evaluates rule conditions against all source profiles. Selects one of 6 product RAG architectures. Emits human-readable explanation cards.
7. **User Approval Gate**: Explicit UI step. No build begins until the user confirms. User may view details, override chunking parameters, change embedding models, or select an alternative architecture.
8. **RAG Builder Pipeline**: Real step-by-step progress tracking with live metrics (chunks created, embeddings calculated, vectors written).
9. **Evaluation**: Verification of retrieval indices and semantic consistency.
10. **Published Interface**: Production-ready interface with cited answers, expandable source snippets, and OpenAPI-compatible local REST endpoint.

---

## 5. Non-Functional Requirements

| Category | Requirement | Specification |
| :--- | :--- | :--- |
| **Performance** | Ingestion & Parsing | Parse a 100-page standard PDF in < 4 seconds on modern quad-core CPU. |
| | UI Responsiveness | 60 FPS UI transitions; no UI blocking during heavy file parsing or vector indexing. |
| | Retrieval Latency | Sub-150ms retrieval search across 50,000 chunks in local vector store. |
| **Memory & Storage** | Baseline Footprint | Idle desktop application < 180MB RAM; idle Python engine < 120MB RAM. |
| | Disk Footprint | Base application installation < 600MB (excluding user-downloaded LLMs). |
| **Privacy & Security** | Local Execution | Zero network traffic in local mode; no external telemetry without explicit opt-in. |
| | Credential Safety | Cloud API keys stored in Windows Credential Manager; loopback IPC secured with bearer token. |
| **Reliability** | Fault Tolerance | Corrupted files fail gracefully with granular error badges without crashing the workspace. |
| | Resumability | Builder pipeline checkpoints progress; crashes during indexing resume from last chunk batch. |
