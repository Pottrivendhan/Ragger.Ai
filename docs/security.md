# Ragger.ai — Security & Privacy Architecture

**Version:** 1.0.0-draft  
**Component:** Security, Local Privacy, Sandbox Boundaries & Credential Storage  
**Target Environment:** Local Windows Desktop / Enterprise Workstations

---

## 1. Local-First Privacy Guarantee & Data Isolation

Users frequently upload highly confidential files to Ragger.ai: internal company policies, patient records, financial disclosures, unpublished research, and customer data.

### 1.1 Local vs Cloud Processing Modes
The application interface strictly communicates the active processing boundary at all times:

| Mode | Processing Location | Data Transmission | Privacy Level |
| :--- | :--- | :--- | :--- |
| **Local Mode (Offline RAG Processing)** | Host Machine (CPU/GPU) | **Zero document, sample, or query data leaves the machine.** All parsing, vectorization, indexing, and inference execute entirely offline. | **Air-Gapped Privacy** |
| **Model Download (Explicit User Action)** | User-Initiated Download | Internet connection required solely to download public model weights from verified repositories and verify SHA-256 checksums. Internet can be disconnected immediately thereafter. | **Zero Data Ingestion** |
| **Hybrid Mode** | Local Ingestion + Cloud LLM | Chunks sent to configured LLM provider via HTTPS; vector index remains local. | **Controlled Cloud** |
| **Cloud Mode** | Cloud Embeddings + Cloud LLM | Ingestion remains local; embeddings and completions sent via encrypted HTTPS. | **Cloud Provider Policy** |

**Invariant**: In Local Mode, no user documents, queries, or knowledge structures ever leave the device. Outbound network requests occur solely when the user explicitly triggers a model download in the Model Manager.

---

## 2. Process Boundaries & IPC Hardening

### 2.1 Electron Renderer Sandboxing
- `nodeIntegration: false` (Prevents malicious scripts from calling Node APIs).
- `contextIsolation: true` (Ensures renderer JavaScript cannot tamper with preload scripts).
- `sandbox: true` (Restricts Chromium renderer process permissions).
- Navigation is strictly locked: external hyperlinks open in the user's default browser via `shell.openExternal`, never inside the application window.

### 2.2 Localhost API Authentication & Loopback Binding
The local Python FastAPI engine communicates over loopback (`127.0.0.1`). To prevent unauthorized local processes or malicious browser tabs from interacting with the RAG engine:

```text
[Electron Main]
      │ Generates random 256-bit Hex Token on launch
      │ Injects token into Python process environment (RAGGER_API_TOKEN)
      │
      ▼
[Python FastAPI Engine]
      │ Binds exclusively to 127.0.0.1 on random port
      │ Enforces Security Middleware:
      │   - Validates "Authorization: Bearer <RAGGER_API_TOKEN>"
      │   - Rejects non-loopback Origin headers
      │   - Returns 401 Unauthorized on missing/invalid token
```

---

## 3. Safe File Ingestion & Exploit Mitigation

### 3.1 Path Traversal Protection
User-provided filenames can contain malicious sequences (e.g., `../../../../Windows/System32/evil.dll`).
- All uploaded files are assigned a cryptographically random UUID upon arrival.
- Files are stored under the workspace source directory: `%LOCALAPPDATA%\RaggerAI\workspaces\<ws_id>\raw_sources\<uuid>.<ext>`.
- Path resolution is strictly validated using canonical path checks:
  ```python
  def safe_join(base_dir: Path, untrusted_filename: str) -> Path:
      sanitized = Path(untrusted_filename).name  # Strips directory paths
      target = (base_dir / sanitized).resolve()
      if not target.is_relative_to(base_dir.resolve()):
          raise SecurityException("Path traversal attempt detected.")
      return target
  ```

### 3.2 Zip Bomb & Decompression Bomb Protection
Formats based on ZIP archives (DOCX, XLSX, PPTX, EPUB) can be weaponized as decompression bombs.
- **Max Uncompressed Ratio**: Parsers enforce a maximum compression ratio of 100:1.
- **Max File Size**: Hard upload cap of 250MB per individual file.
- **Max Uncompressed Size**: Any archive unpacking to $>1.5\text{ GB}$ is aborted immediately.

### 3.3 XML External Entity (XXE) Prevention
XML, HTML, and Office XML parsers use `defusedxml` with entity expansion and external DTD resolution permanently disabled.

---

## 4. Rendered Content Sanitization (XSS Defense)

When displaying document excerpts, tables, markdown responses, or citation snippets in the chat interface:
- All dynamic HTML/Markdown is sanitized through `DOMPurify` before insertion into the React DOM.
- Content Security Policy (CSP) is enforced in `index.html`:
  ```html
  <meta http-equiv="Content-Security-Policy" content="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' http://127.0.0.1:*;">
  ```

---

## 5. Secure Credential Storage

For users configuring Cloud LLM providers (OpenAI, Anthropic, Cohere, Groq):
- **Never** store API keys in plain text files (`.env`, `config.json`, or SQLite).
- Keys are encrypted and stored via **Windows Credential Manager** (using the Windows Data Protection API / DPAPI via `keytar` in Electron):
  - Service: `RaggerAI`
  - Account: `provider:<provider_name>` (e.g., `provider:openai`)
- Keys are retrieved in Electron main and provided in-memory to the Python engine when executing cloud completions.

---

## 6. Audit Logging & Data Masking

- Diagnostic logs (`electron.log`, `engine.log`) are stored locally.
- **Sensitive Content Masking**: Raw document text, extracted paragraphs, and user chat prompts are **never** logged to disk at `INFO` or `ERROR` levels.
- Logs capture only structural telemetry: `source_id`, `chunk_count`, `duration_ms`, `http_status`, and error codes.
