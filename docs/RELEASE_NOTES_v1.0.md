# Ragger.ai v1.0.0 — Release Notes

**Release Date:** September 18, 2026  
**Artifact:** `release/RaggerAI-Setup.exe` (108.21 MB)  
**Architecture:** Electron 32 + React 18 + Hermetic Python 3.12 (PyInstaller `onedir`)  
**Target Platform:** Windows 10/11 x64 (Clean Machine / Zero Prerequisites)

---

## 🚀 Highlights & Major Milestones

Ragger.ai v1.0.0 represents the complete, locked implementation of the 10-phase production blueprint:

1. **Self-Contained Standalone Installer**:
   - Packaged as a single per-user setup executable: `RaggerAI-Setup.exe` (108.21 MB).
   - Zero developer tooling required: runs on a clean Windows machine without Python, Node.js, Git, or pip.
   - Zero UAC administrative elevation required.

2. **Strict Model Separation Invariant**:
   - Heavy AI model weights are completely excluded from the application distribution.
   - The recursive distribution scan verified **zero** `.gguf`, `.safetensors`, `.onnx` model weights, or model-weight `.bin` files inside `release/win-unpacked/`.
   - Weights are acquired and verified exclusively by the **Phase 9 Local AI Model Manager** under `%LOCALAPPDATA%\RaggerAI\models`.

3. **End-to-End Local-First RAG Pipeline**:
   - **Ingestion**: Supports 14 file formats (PDF, DOCX, PPTX, XLSX, CSV, TSV, JSON, XML, HTML, MD, TXT, EPUB, DOC, RTF).
   - **Corpus Analysis**: Read-only structural metrics (token density, table/code/text modality distribution) with zero hallucination.
   - **Recommendation**: Rule-based architectural mapping to Document RAG, Knowledge RAG, Structured Data RAG, Hybrid RAG, or Research RAG.
   - **Approved Build**: User approval gate before FAISS index creation with deterministic chunk hashing and manifest verification.
   - **Dense Retrieval**: Hot reload with atomic pointer swapping and concurrent query locking.
   - **Grounded Generation**: Streaming generation with strict citation validation and low-confidence disclaimer triggers.
   - **Quality Evaluation**: Automated probe generation, retrieval evaluation (Hits@K, MRR), and response quality scoring (Citation Precision, Source Coverage, Claim-Level Faithfulness).
   - **Hardware Adaptation**: Host RAM/VRAM inspection with deterministic tier classification (Low, Medium, High, Enthusiast) and 300s TTL cache.

4. **Security & Process Integrity**:
   - Loopback-only binding (`127.0.0.1`) on ephemeral ports.
   - Per-session 256-bit cryptographic bearer token authentication.
   - Comprehensive 401 / 401 / 200 authentication contract.
   - Clean process-tree teardown ensuring 0 orphan/zombie processes.

---

## 📊 Verification & Test Results

| Test Suite | Total Tests / Steps | Passed | Status |
| :--- | :---: | :---: | :---: |
| **Phase 1–9 PyTest Regression Suite** | 185 tests | 185 | ✅ 100% PASS |
| **Electron & IPC Integration Suite** | 54 steps | 54 | ✅ 100% PASS |
| **Frozen Standalone Engine (Steps 55–57)** | 3 gates | 3 | ✅ 100% PASS |
| **Distribution & Zero-Weight Scan (Steps 58–63)** | 6 gates | 6 | ✅ 100% PASS |
| **NSIS Installer Integrity (Steps 64–65)** | 2 gates | 2 | ✅ 100% PASS |
| **Clean Machine Environment (Steps 66–69)** | 4 gates | 4 | ✅ 100% PASS |
| **Master Build & Test Runner (`npm test`)** | Complete Suite | Code 0 | ✅ 100% PASS |

---

## 🛠️ Components & File Manifest

| File / Folder | Purpose |
| :--- | :--- |
| `release/RaggerAI-Setup.exe` | Production Windows installer (108.21 MB) |
| `release/win-unpacked/` | Unpacked production application distribution |
| `engine/dist/engine/ragger-engine.exe` | Frozen Python 3.12 engine binary (13.70 MB) |
| `engine/dist/engine/_internal/` | Hermetic Python runtime (87 items, DLLs, packages) |
| `frontend/dist/` | Production React 18 single-page application |
| `scripts/sandbox.wsb` | Windows Sandbox VM definition |
| `scripts/sandbox_runner.cmd` | Automated clean-machine sandbox test script |

---

## 🔮 Future Roadmap (Phase 11+)
- **GPU Acceleration Extension**: Pre-configured CUDA and DirectML ONNX runtime execution providers for low-latency dense embeddings.
- **Dynamic Corpus Ingestion**: Watch-folder and background sync for continuously updated document repositories.
- **Cross-Platform Packaging**: macOS DMG and Linux AppImage/deb packaging following the same frozen runtime architecture.
