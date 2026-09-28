# Ragger.ai — Windows Production Packaging & Distribution

**Version:** 1.0.0-draft  
**Component:** Desktop Packaging, Embedded Runtime & NSIS Installer  
**Target Output:** `RaggerAI-Setup.exe` (Single Windows Installer)

---

## 1. Distribution Objective & Invariants

The target consumer executable for Ragger.ai is a single Windows setup file:

```text
RaggerAI-Setup.exe
```

### Non-Negotiable Invariants:
1. **Zero Developer Toolchain Prerequisites**: The end user must **never** be required to install:
   - Python
   - Node.js / npm / yarn
   - pip / virtualenv
   - Git
   - Visual C++ Build Tools
2. **Hermetic Runtime Isolation**: The bundled Python engine must run within its own sandboxed environment. It must not touch, alter, or depend on any system-level Python installations or global registry keys.
3. **Clean Sandbox Verification**: A release is not considered production-ready until it installs, runs, and successfully executes a RAG workflow on a pristine Windows Sandbox / fresh VM with zero developer tools.

---

## 2. Packaging Architecture

```text
RaggerAI-Setup.exe (NSIS Installer)
 │
 ▼ Installs to: %LOCALAPPDATA%\Programs\RaggerAI\
 ├── RaggerAI.exe                  # Electron executable
 ├── resources/
 │   ├── app.asar                  # Packaged Electron main, preload & React frontend
 │   └── engine/                   # Bundled Python Standalone Engine
 │       ├── ragger-engine.exe     # PyInstaller one-dir binary OR python.exe embed
 │       ├── python311.dll         # Standalone CPython DLL
 │       ├── lib/                  # Vendored dependencies (FastAPI, Polars, Chroma, etc.)
 │       └── llama.dll / onnx.dll  # Native C++ inference runtimes
 └── uninstall.exe
```

---

## 3. Python Engine Bundling Strategy

To achieve high reliability and rapid startup, Ragger.ai utilizes a **Two-Tier Frozen Python Architecture**:

### 3.1 Distribution Engine Strategy: PyInstaller (`onedir` mode)
Rather than `onefile` mode (which unpacks several hundred megabytes into `%TEMP%` on every single launch, adding 5–10 seconds of startup latency), we package the engine using PyInstaller `onedir` mode:

```bash
pyinstaller \
    --noconfirm \
    --onedir \
    --windowed \
    --name ragger-engine \
    --add-data "ragger_engine/recommendation/catalog:ragger_engine/recommendation/catalog" \
    --hidden-import uvicorn.logging \
    --hidden-import uvicorn.loops.auto \
    --hidden-import uvicorn.protocols.http.auto \
    --hidden-import uvicorn.lifespan.on \
    ragger_engine/main.py
```

### 3.2 Vendored Binaries & Binary Stripping
- **Torch Exclusion**: By standardizing on `onnxruntime` and `llama-cpp-python` for local inference, we eliminate the need for `torch`, `torchvision`, and `CUDA` runtime wheels, reducing Python bundle size from ~3.5GB down to ~160MB.
- **Fast Tabular Processing**: Using `polars` (Rust-based) instead of full heavy data science distributions keeps startup under 200ms.

---

## 4. Electron Packaging (`electron-builder.yml`)

```yaml
appId: ai.ragger.desktop
productName: Ragger.ai
directories:
  output: dist-installer
  buildResources: build
files:
  - "dist/main/**/*"
  - "dist/preload/**/*"
  - "dist/renderer/**/*"
extraResources:
  - from: "engine/dist/ragger-engine"
    to: "engine"
    filter:
      - "**/*"
nsis:
  oneClick: false
  allowToChangeInstallationDirectory: true
  perMachine: false                      # Installs to user AppData without UAC elevation
  createDesktopShortcut: always
  createStartMenuShortcut: true
  shortcutName: "Ragger.ai"
  uninstallDisplayName: "Ragger.ai Knowledge Platform"
win:
  target:
    - target: nsis
      arch:
        - x64
```

---

## 5. Development vs Production Execution Flow

The desktop shell detects its execution environment via `app.isPackaged`:

```typescript
// apps/desktop/src/main/supervisor.ts
export function getEngineExecutionCommand(): { cmd: string; args: string[] } {
  if (app.isPackaged) {
    // Production Mode: Execute bundled frozen binary
    const enginePath = path.join(
      process.resourcesPath,
      'engine',
      'ragger-engine.exe'
    );
    return { cmd: enginePath, args: [] };
  } else {
    // Development Mode: Execute local virtualenv python
    const venvPython = process.platform === 'win32'
      ? path.join(__dirname, '../../../../engine/.venv/Scripts/python.exe')
      : path.join(__dirname, '../../../../engine/.venv/bin/python');
    return { 
      cmd: venvPython, 
      args: ['-m', 'ragger_engine.main'] 
    };
  }
}
```

---

## 6. Installer QA & Clean Machine Verification Protocol

Before any release milestone, execute the automated packaging validation script:

1. **Build Step**:
   - `npm run build:frontend`
   - `python packaging/build_engine.py`
   - `npm run package:desktop`
2. **Verification in Windows Sandbox**:
   - Spin up a fresh `Windows Sandbox` container (`.wsb` script).
   - Copy `RaggerAI-Setup.exe` into sandbox.
   - Run installer without administrator prompts.
   - Launch application from Start Menu.
   - Verify health check: Electron connects to `ragger-engine.exe` on loopback port within 3 seconds.
   - Upload sample PDF (`company_policy.pdf`) and CSV (`sales_data.csv`).
   - Confirm parsing and sample extraction succeed.
   - Confirm Model Manager can query catalog and initiate a verified download.
