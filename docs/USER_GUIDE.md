# Ragger.ai — User Guide

Welcome to **Ragger.ai**, your private, local-first platform for turning complex documents and datasets into grounded, intelligent knowledge systems.

---

## 🚀 1. Installation & First Launch

### Step 1: Install
1. Double-click **`RaggerAI-Setup.exe`**.
2. The installer will install Ragger.ai directly to your user profile (`%LOCALAPPDATA%\Programs\Ragger.ai`) without requiring administrative permissions or UAC prompts.
3. Shortcuts will be automatically created on your Desktop and Start Menu.

### Step 2: First Launch
When you open Ragger.ai:
- The desktop shell automatically launches the internal **Python Engine** on a secure, private loopback connection (`127.0.0.1`).
- A random 256-bit cryptographic session token is generated to ensure that only the desktop shell can communicate with the engine.
- You will see the **Workspace Dashboard**.

---

## 📂 2. Importing Documents & Datasets

Ragger.ai supports 14 enterprise and research file formats:
- **Narrative Documents**: PDF, DOCX, DOC, PPTX, EPUB, RTF, HTML, Markdown, TXT.
- **Structured Datasets**: CSV, TSV, XLSX, JSON, XML.

### Ingestion Workflow:
1. Click **"Import Files"** or drag-and-drop your files into the workspace.
2. Ragger.ai performs deterministic file inspection, calculates SHA-256 integrity hashes, and routes files to specialized parsers.
3. Your raw files are safely indexed into canonical format without modifying your original files.

---

## 🔍 3. Corpus Analysis & Architecture Recommendation

Once files are imported:
1. Navigate to the **"Analysis"** tab.
2. Ragger.ai calculates structural metrics across your corpus:
   - Modality breakdown (text, tables, code).
   - Structural depth (heading levels, sections, chapters).
   - Token density and vocabulary variance.
3. The **Recommendation Engine** evaluates your corpus characteristics against rule-based criteria and suggests an optimal RAG strategy:
   - **Document RAG**: Best for narrative manuals, contracts, and reports.
   - **Knowledge RAG**: Best for deep hierarchical books, research papers, and technical specifications.
   - **Structured Data RAG**: Best for tabular spreadsheets, CSVs, and transaction records.
   - **Hybrid RAG**: Best for mixed corpora containing both narrative text and tables.
   - **Research RAG**: Best for scientific papers requiring dense retrieval + lexical boost + reranking.

---

## ⚙️ 4. Build Approval & Index Creation

1. Review the proposed chunking strategy (parent chunk size, child chunk size, overlap).
2. Click **"Approve & Build Index"**.
3. Ragger.ai constructs the dense embeddings and FAISS index locally.
4. When complete, the build is atomically activated via hot reload. The retrieval engine is now immediately available.

---

## 💬 5. Grounded Chat & Strict Citations

1. Navigate to the **"Chat"** tab.
2. Ask questions against your indexed knowledge base.
3. **Grounded Generation Guarantees**:
   - Every claim in the generated response is backed by an explicit citation tag (e.g. `[Doc 1, Page 4]`).
   - Clicking a citation highlights the exact excerpt and source document from your corpus.
   - If the corpus lacks sufficient evidence to answer your query, Ragger.ai triggers an explicit disclaimer rather than fabricating an answer.

---

## 📊 6. Quality Evaluation & Factuality Scoring

Ensure your RAG pipeline meets strict accuracy standards:
1. Navigate to the **"Evaluation"** tab.
2. Click **"Run Automated Evaluation"**.
3. Ragger.ai generates synthetic test probes and runs evaluations using an isolated evaluation judge:
   - **Retrieval Metrics**: Hits@1, Hits@3, Hits@5, Mean Reciprocal Rank (MRR).
   - **Generation Metrics**: Citation Precision, Source Coverage, Claim-Level Faithfulness.
4. All evaluation sessions run in ephemeral memory and **never** pollute your chat history.

---

## 🤖 7. Local AI Model Manager

Ragger.ai lets you run completely offline with local AI models:
1. Open the **"Model Manager"** in the sidebar.
2. **Hardware Inspection**: View your host CPU capabilities, physical RAM, and GPU VRAM tier.
3. **Model Catalog**:
   - **Direct GGUF Models**: Download optimized instruction models (e.g., Qwen 2.5, Llama 3.2).
   - **Direct ONNX Models**: Download fast, local dense embedding encoders (e.g., BGE-Small).
   - **Local Ollama Daemon**: Connect seamlessly to your existing Ollama installation.
4. **Resumable Downloads**: Pause, resume, and verify downloads with SHA-256 cryptographic checksums.
5. **Activation**: Activate any downloaded model for Generation or Evaluation with a single click.
