# Ragger.ai

<div align="center">

# 🚀 Ragger.ai — Private, Local-First Desktop RAG Platform

**Turn your enterprise & research data into an intelligent, private, local-first knowledge system.**

[![Download Setup.exe](https://img.shields.io/badge/⬇️_Direct_Download-RaggerAI--Setup.exe_(Windows)-0078D6?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/Pottrivendhan/Ragger.Ai/releases/download/v1.0.0/RaggerAI-Setup.exe)
[![GitHub Release](https://img.shields.io/badge/Release-v1.0.0-success?style=for-the-badge&logo=github)](https://github.com/Pottrivendhan/Ragger.Ai/releases/tag/v1.0.0)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%20x64-0078D6.svg?logo=windows)]()
[![Architecture: Frozen Engine](https://img.shields.io/badge/Architecture-Hermetic%20Python%20%2B%20Electron-success.svg)]()
[![Regression Gate: 185/185](https://img.shields.io/badge/Tests-185%2F185%20Passing-brightgreen.svg)]()
[![Zero Cloud Leakage](https://img.shields.io/badge/Privacy-100%25%20Local%20%26%20Zero%20Cloud-orange.svg)]()

[📥 Download Installer](#-download--production-installation) • [🌟 Overview](#-overview) • [🎯 Key Features](#-key-features) • [🏗️ Architecture](#-architecture) • [Phase 1–10 Matrix](#-phase-110-development-matrix) • [💻 Developer Quickstart](#-developer-quickstart)

</div>

---

## 📥 Download & Production Installation

### ⚡ Direct Download
Get the ready-to-run Windows standalone desktop installer directly from the GitHub Release:

👉 **[Download RaggerAI-Setup.exe (v1.0.0)](https://github.com/Pottrivendhan/Ragger.Ai/releases/download/v1.0.0/RaggerAI-Setup.exe)**

> **Note on AI Model Weights**: In accordance with best practices, **large model weights are not hosted in the git source tree**. The lightweight installer automatically connects to the built-in **Local Model Manager** where you can download and manage verified GGUF and ONNX models on demand with a single click.

### System Requirements
- **OS**: Windows 10 / 11 (64-bit)
- **RAM**: 8 GB minimum (16 GB recommended for larger local GGUF models)
- **Disk Space**: ~500 MB for application; 2–5 GB for local GGUF models (e.g. Qwen2.5-1.5B / Llama)
- **Prerequisites**: **None.** No Python, Node.js, C++ compilers, or Git required for end-users.

### Easy Installation Steps
1. Download **[`RaggerAI-Setup.exe`](https://github.com/Pottrivendhan/Ragger.Ai/releases/download/v1.0.0/RaggerAI-Setup.exe)**.
2. Run the installer (per-user installation, zero administrative/UAC prompts required).
3. Launch **Ragger.ai** from your Start Menu or Desktop shortcut.
4. Navigate to the **Model Manager** to download or import your preferred local GGUF model and start querying your documents!

---

## 🌟 Overview

**Ragger.ai** is an enterprise-grade, privacy-preserving desktop platform for heterogeneous document engineering and Retrieval-Augmented Generation (RAG). Built for enterprises, legal teams, medical researchers, and security-conscious knowledge workers, Ragger.ai operates **100% locally on your workstation**.

- **Zero Cloud Leakage**: All parsing, embeddings, retrieval, generation, and quality evaluation execute on local hardware.
- **Single-Click Setup**: Ships as a standalone Windows installer (`RaggerAI-Setup.exe`) bundling a hermetic Python runtime and Electron desktop shell.
- **Model Isolation**: Zero model weight bloat in the source repository. All models are cryptographically validated with SHA-256 via the embedded Model Manager.

---

## 🎯 Key Features

- **Multi-Format Ingestion (14 Formats)**: Deterministic parsing for PDF, DOCX, PPTX, XLSX, CSV, TSV, JSON, XML, HTML, Markdown, TXT, EPUB, DOC, and RTF.
- **Heuristic Corpus Analyzer**: Distinguishes narrative documents from tabular datasets without AI hallucinations, computing token density, structural depth, and modality distributions.
- **Rule-Based Architecture Recommender**: Selects the optimal RAG strategy (**Document RAG**, **Knowledge RAG**, **Structured Data RAG**, **Hybrid RAG**, or **Research RAG**) based on deterministic corpus properties.
- **Cryptographic Build & Dense Retrieval**: Generates reproducible FAISS/dense indexes with atomic pointer swapping, hot reload, and SHA-256 manifest validation.
- **Grounded Generation with Strict Citation Verification**: Enforces zero hallucinated citations, clean natural-language answers without internal provenance leakage, and disclaimer triggers for low-confidence queries.
- **Interactive AI Agent Workspace**: Full conversational workspace supporting multi-turn chat, markdown rendering, active generation termination, question editing, and Enter/Shift+Enter controls.
- **Automated Quality Evaluation**: Evaluates retrieval accuracy (Hits@1, Hits@3, Hits@5, MRR) and response quality (Citation Precision, Source Coverage, Claim-Level Faithfulness) via automated LLM judges.
- **Hardware-Aware Model Manager**: Probes host CPU, RAM, and GPU VRAM with exact tier grading; manages direct GGUF and ONNX downloads with resumable HTTP 206 chunking, SHA-256 validation, and local Ollama daemon integration.

---

## 🏗️ Architecture

Ragger.ai utilizes a hermetic three-tier architecture:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                           Ragger.ai Desktop                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────────────────┐             ┌────────────────────────┐   │
│   │     React 18 + Vite      │             │     Electron Shell     │   │
│   │    (Tailored Design)     │◄───(IPC)───►│ (Process Supervisor)   │   │
│   └──────────────────────────┘             └───────────┬────────────┘   │
│                                                        │                │
│                                               (Auth Loopback HTTP)      │
│                                               256-bit Bearer Token      │
│                                               Ephemeral 127.0.0.1 Port  │
│                                                        ▼                │
│                                            ┌────────────────────────┐   │
│                                            │  FastAPI Python Engine │   │
│                                            │ (PyInstaller onedir)   │   │
│                                            └───────────┬────────────┘   │
│                                                        │                │
│                                            ┌───────────┴────────────┐   │
│                                            │ %LOCALAPPDATA%\RaggerAI│   │
│                                            │ (Storage, Builds, MM)  │   │
│                                            └────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Security & Process Isolation Invariants
1. **Loopback-Only Binding**: The FastAPI engine strictly binds to `127.0.0.1` on an OS-assigned ephemeral port.
2. **256-Bit Bearer Token**: A unique cryptographic token is generated per session in Electron's main process; the React frontend never touches the secret token directly.
3. **Graceful Process Supervision**: Electron supervises child process trees, issuing SIGTERM on exit with zero orphan/zombie processes.

---

## 🏆 Phase 1–10 Development Matrix

All 10 architectural phases specified in `coreplan.txt` are **100% complete, verified, and locked**:

| Phase | Milestone | Status | Key Deliverables & Contracts |
| :---: | :--- | :---: | :--- |
| **1** | **Ingestion Foundation** | ✅ PASS | File detection, deterministic SHA-256 hashing, path traversal security, 14 parsers. |
| **2** | **Ingestion Boundary & Chunking** | ✅ PASS | Strict boundary invariant, token-window chunking, hierarchical chunking, overlap limits. |
| **3** | **Synthesis & Canonical Storage** | ✅ PASS | Unified JSON storage schema, dataset records serialization, schema integrity. |
| **4** | **Corpus Analysis & Invariants** | ✅ PASS | Read-only observer invariant, structural metrics, zero recommendation leakage. |
| **5** | **Approved Build & Indexing** | ✅ PASS | User approval gate, reproducible chunk IDs, FAISS dense indexing, manifest hashing. |
| **6** | **Dense Retrieval Gate** | ✅ PASS | Atomic pointer hot reload, concurrent queries, missing build gate (HTTP 412/404/424). |
| **7** | **Grounded Generation & Citations** | ✅ PASS | Ephemeral streaming, strict citation validation, hallucination purge, clean provenance. |
| **8** | **Quality Evaluation & Factuality** | ✅ PASS | Automated probe generation, Hits@K, MRR, citation precision, claim faithfulness. |
| **9** | **Model Manager & Hardware** | ✅ PASS | Hardware tier grading, immutable catalog, resumable HTTP 206, SHA-256, Ollama daemon. |
| **10** | **Production Export & Packaging** | ✅ PASS | PyInstaller onedir, NSIS installer (`RaggerAI-Setup.exe`), zero weights, clean sandbox. |

---

## 💻 Developer Quickstart

For developers contributing to or building Ragger.ai from source:

### Prerequisites
- Node.js (v20+ or v22+)
- Python 3.10+ (Python 3.12 recommended)

### Clone & Install
```bash
# 1. Clone the repository
git clone https://github.com/Pottrivendhan/Ragger.Ai.git
cd Ragger.Ai

# 2. Install Node dependencies
npm install

# 3. Setup Python virtual environment
python -m venv engine/.venv
.\engine\.venv\Scripts\python.exe -m pip install -e ".\engine[dev]"
```

### Running Locally in Development Mode
```bash
# Concurrently launches Vite frontend + Electron main shell + Python engine
npm run dev
```

### Full Test & Verification Pipeline
```bash
# Run 185 Phase 1-9 pytest regression suite
npm run test:engine

# Run complete 54-step Electron supervisor & IPC integration suite
npm run test:integration

# Master test runner (all suites back-to-back)
npm test
```

### Building Production Installer
```bash
# 1. Build frontend bundle
npm run build:frontend

# 2. Build desktop Electron shell
npm run build:desktop

# 3. Freeze Python engine via PyInstaller
npm run bundle:engine

# 4. Compile NSIS Setup Executable
npm run dist
```
The output installer will be generated in `release/RaggerAI-Setup.exe`.

---

## 📄 License
This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
