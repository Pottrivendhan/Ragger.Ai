"""Main application entrypoint for Ragger Engine."""

import argparse
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ragger_engine.api.routes import router
from ragger_engine.core.config import settings
from ragger_engine.core.logging import setup_logging
from ragger_engine.core.security import TokenAuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events for FastAPI application."""
    setup_logging()
    yield


def create_app() -> FastAPI:
    """Factory function for FastAPI application."""
    app = FastAPI(
        title="Ragger.ai Engine",
        version=settings.app_version,
        lifespan=lifespan,
        docs_url=None,       # Disabled by default in production
        redoc_url=None,
        openapi_url=None,
    )

    # CORS restricted to loopback origins & Electron packaged app (file://, null)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|file://.*|null)$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Enforce token authentication
    app.add_middleware(TokenAuthMiddleware)

    # Mount API routes
    app.include_router(router)

    return app


app = create_app()


def parse_args():
    parser = argparse.ArgumentParser(description="Ragger.ai Python Engine")
    parser.add_argument("--host", default=settings.host, help="Host to bind (must be loopback)")
    parser.add_argument("--port", type=int, default=settings.port, help="Port to bind")
    parser.add_argument("--token", default=settings.ragger_api_token, help="API bearer token")
    parser.add_argument("--log-level", default=settings.log_level, help="Log level")
    return parser.parse_args()


def main():
    if getattr(sys, "frozen", False):
        import multiprocessing
        multiprocessing.freeze_support()

    args = parse_args()

    # Enforce loopback binding
    if args.host not in ("127.0.0.1", "localhost"):
        print(f"FATAL: Host '{args.host}' is not a permitted loopback address. Engine must bind to 127.0.0.1.", file=sys.stderr)
        sys.exit(1)

    settings.host = args.host
    settings.port = args.port
    if args.token:
        settings.ragger_api_token = args.token
    elif not settings.ragger_api_token:
        # Check if an existing dev session token is already in storage
        existing_token = None
        try:
            from ragger_engine.core.storage import get_storage_root
            dev_session_path = get_storage_root() / "dev_session.json"
            if dev_session_path.exists():
                import json
                session_data = json.loads(dev_session_path.read_text(encoding="utf-8"))
                existing_token = session_data.get("token")
        except Exception:
            pass

        if existing_token:
            settings.ragger_api_token = existing_token
        else:
            import secrets
            settings.ragger_api_token = secrets.token_hex(32)
    settings.log_level = args.log_level

    setup_logging()

    if not getattr(sys, "frozen", False):
        try:
            import json
            from datetime import datetime, timezone
            from ragger_engine.core.storage import get_storage_root
            dev_session = get_storage_root() / "dev_session.json"
            dev_session.write_text(
                json.dumps({
                    "host": settings.host,
                    "port": settings.port,
                    "token": settings.ragger_api_token,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,  # We use our custom logging configuration
    )


if __name__ == "__main__":
    main()
