"""Security and token verification middleware."""

import secrets
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from ragger_engine.core.config import settings


# Endpoints exempted from token authentication (e.g. liveness probe)
UNAUTHENTICATED_PATHS = {
    "/health",
}


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing Bearer token authentication on all protected routes."""

    async def dispatch(self, request: Request, call_next):
        # Allow OPTIONS for CORS preflights
        if request.method == "OPTIONS":
            return await call_next(request)

        # Allow explicit unauthenticated paths (e.g. basic /health probe)
        path = request.url.path
        if path in UNAUTHENTICATED_PATHS:
            return await call_next(request)

        expected_token = settings.ragger_api_token
        
        # If no token is configured in test/dev mode, fail closed unless explicitly disabled
        if not expected_token:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "type": "https://ragger.ai/errors/AUTH_NOT_CONFIGURED",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Engine authentication token has not been configured.",
                    "code": "AUTH_NOT_CONFIGURED",
                },
            )

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "type": "https://ragger.ai/errors/AUTH_MISSING_TOKEN",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Missing or malformed Authorization header. Expected Bearer <token>.",
                    "code": "AUTH_MISSING_TOKEN",
                },
            )

        provided_token = auth_header[7:].strip()

        # Constant-time comparison to prevent timing attacks
        if not secrets.compare_digest(provided_token, expected_token):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={
                    "type": "https://ragger.ai/errors/AUTH_INVALID_TOKEN",
                    "title": "Unauthorized",
                    "status": 401,
                    "detail": "Invalid authentication token.",
                    "code": "AUTH_INVALID_TOKEN",
                },
            )

        return await call_next(request)
