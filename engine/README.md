# Ragger.ai — Python RAG Engine

The core backend service for Ragger.ai.

## Phase 1 Scope
- Fast, secure, loopback-only service on dynamic port `127.0.0.1:<dynamic_port>`.
- Token-authenticated endpoints (`/api/v1/health`, `/api/v1/runtime`).
- Unauthenticated liveness probe (`/health`).
- Supervised lifecycle management via Electron main process.

## Running in Development
```bash
# Set environment
set RAGGER_API_TOKEN=test-token-12345
python -m ragger_engine.main --host 127.0.0.1 --port 8000
```
