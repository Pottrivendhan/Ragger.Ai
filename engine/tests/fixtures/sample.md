# Ragger.ai Engineering Guide

This document outlines architecture and coding principles.

## Core Directives

1. Maintain modular boundaries.
2. Deterministic execution over prompt chaos.

### Architecture Table

| Tier | Technology | Purpose |
| --- | --- | --- |
| Frontend | React + Vite | User Interface |
| Desktop | Electron | Process Host |
| Engine | Python FastAPI | Processing |

> "Always test real systems against real edge cases."

```python
def example():
    return "Hello Ragger"
```
