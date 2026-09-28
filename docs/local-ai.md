# Ragger.ai — Local AI & Model Manager Specification

**Version:** 1.0.0-draft  
**Component:** Local Model Execution, Model Manager & Hardware Adaptation  
**Target Environment:** Windows 10/11 Desktop (CPU AVX2 / Vulkan / NVIDIA CUDA)

---

## 1. The Core Packaging & Distribution Invariant

> **CRITICAL RULE**: Large model weights (1GB–10GB+) must **NEVER** be packaged inside the Ragger.ai installer (`RaggerAI-Setup.exe`).

### Why this is non-negotiable:
1. **Download Friction**: A 6GB+ installer leads to high download drop-offs and failed installations on slower connections.
2. **Update Inefficiency**: Minor bug fixes or UI updates would require users to re-download the entire multi-gigabyte bundle.
3. **Hardware Variance**: Different machines require different model sizes and quantizations (e.g., an 8GB RAM ultrabook vs a 64GB RAM workstation with an RTX 4090).

### The Dual-Artifact Architecture:
```text
RaggerAI-Setup.exe (~250MB - 350MB)
├── Electron Desktop Shell
├── React UI Bundle
├── Bundled Standalone Python Runtime
├── Core RAG Engine & Parsers
├── Local Vector Database Engine (DuckDB / LanceDB / Chroma)
└── Model Manager Engine
         │
         ▼ (Post-Installation User Action)
Downloaded Separately via Model Manager:
%LOCALAPPDATA%\RaggerAI\models\
├── analyzer/     (e.g., Qwen2.5-1.5B-Instruct-Q4_K_M.gguf)
├── embeddings/   (e.g., bge-small-en-v1.5.onnx)
└── generation/   (e.g., Llama-3.2-3B-Instruct-Q4_K_M.gguf)
```

---

## 2. Separation of Model Responsibilities

Ragger.ai does not attempt to force a single massive model to execute every pipeline task. It separates responsibilities into three distinct model tiers:

```text
┌─────────────────────────┐   ┌─────────────────────────┐   ┌─────────────────────────┐
│     ANALYZER LLM        │   │     EMBEDDING MODEL     │   │     GENERATION LLM      │
│ (Fast Structural Scout) │   │ (Vector Representation) │   │  (Grounded Synthesis)   │
├─────────────────────────┤   ├─────────────────────────┤   ├─────────────────────────┤
│ Target: 1.0B - 2.5B     │   │ Target: 384 / 768 dims  │   │ Target: 3B - 8B / Cloud │
│ Speed: >40 tokens/sec   │   │ Speed: Batched ONNX     │   │ Speed: 15-30 tokens/sec │
│ Purpose: JSON extraction│   │ Purpose: Dense vectors  │   │ Purpose: Cited answers  │
└─────────────────────────┘   └─────────────────────────┘   └─────────────────────────┘
```

---

## 3. Local Model Manager (`ModelManager`)

The Model Manager is a first-class citizen in the Ragger.ai desktop experience, controlling the lifecycle of all local weights.

```python
class ModelSpec(BaseModel):
    model_id: str                 # e.g., "qwen-2.5-1.5b-q4"
    name: str                     # "Analyzer Mini"
    category: str                 # "analyzer", "embedding", "generation"
    file_name: str
    download_url: str
    sha256_checksum: str
    file_size_bytes: int
    ram_required_mb: int
    gpu_recommended: bool
    context_window: int
    quantization: str             # "Q4_K_M", "Q5_K_M", "FP16"

class DownloadProgress(BaseModel):
    model_id: str
    status: str                   # "idle", "downloading", "paused", "verifying", "ready", "error"
    downloaded_bytes: int
    total_bytes: int
    speed_bytes_per_sec: float
    eta_seconds: int
    error_message: Optional[str] = None
```

### Supported Lifecycle Operations:
- **`download(model_id)`**: Initiates chunked HTTP download with `Range` header support.
- **`pause(model_id)`**: Closes active connection, persisting partial download file (`.part`).
- **`resume(model_id)`**: Resumes download from exact byte offset.
- **`cancel(model_id)`**: Aborts stream and deletes temporary partial files.
- **`verify(model_id)`**: Computes SHA-256 hash of complete download against `sha256_checksum`.
- **`delete(model_id)`**: Unloads model from memory and deletes weight file from disk.

---

## 4. Local Inference Runtime

### 4.1 LLM Backend: `llama-cpp-python`
- **Format**: GGUF (Quantized weights).
- **Execution**: Direct C++ binding to `llama.cpp` compiled for Windows with AVX2 and Vulkan support.
- **Offloading**: Automatically queries GPU memory and offloads $N$ layers (`n_gpu_layers`) if compatible hardware is detected.

### 4.2 Embedding Backend: `FastEmbed` / `ONNX Runtime`
- **Format**: ONNX Optimized models.
- **Execution**: Pure C++/Rust inference runtime via `onnxruntime-directml` or CPU fallback.
- **No PyTorch Dependency**: Eliminates the massive 2GB+ PyTorch wheel from the installer, keeping runtime lean.

---

## 5. Hardware Detection & Recommendation Heuristics

On first launch, the application probes system hardware:
- Available Physical RAM (via Windows `GlobalMemoryStatusEx`)
- CPU Cores & AVX/AVX2 instruction support
- GPU Adapter Name & Dedicated Video Memory (VRAM via DXGI / DirectML)

### Recommendation Matrix:
| System Profile | Recommended Analyzer | Recommended Generator | Recommended Embedding |
| :--- | :--- | :--- | :--- |
| **Basic (8GB RAM, Integrated GPU)** | Qwen-2.5-0.5B (Q4_K_M, 450MB) | Qwen-2.5-1.5B (Q4_K_M, 1.1GB) | BGE-small-en-v1.5 (ONNX, 130MB) |
| **Standard (16GB RAM, 4GB+ GPU)** | Qwen-2.5-1.5B (Q4_K_M, 1.1GB) | Llama-3.2-3B (Q4_K_M, 2.0GB) | BGE-base-en-v1.5 (ONNX, 430MB) |
| **High Performance (32GB+ RAM, 8GB+ GPU)**| Qwen-2.5-3B (Q5_K_M, 2.4GB) | Llama-3.1-8B (Q4_K_M, 4.9GB) | BGE-large-en-v1.5 (ONNX, 1.3GB) |

---

## 6. UI Transparency & Zero-Fake-State Principle

If a workspace requires a model that is not present on disk:
- The UI **must never fake availability** or attempt to run dummy stubs.
- The UI displays a clear status card: `Download Required (2.1 GB)`.
- Clicking `Download Model` opens the integrated downloader drawer showing real progress, speed, and ETA.
- The user is also offered the option to provide an external API key (e.g. OpenAI / Groq / Anthropic) to bypass local model download entirely.
