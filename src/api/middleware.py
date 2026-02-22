"""
Custom middleware for API security.
"""

import logging
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Validates X-Api-Key header against a shared secret.

    When api_key is None (not configured), the middleware is disabled
    and all requests pass through — this allows local development
    without the secret.
    """

    def __init__(self, app, api_key: Optional[str] = None, exempt_paths: Optional[set[str]] = None):
        super().__init__(app)
        self._api_key = api_key
        self._exempt_paths = exempt_paths or set()

    async def dispatch(self, request: Request, call_next):
        # Disabled if no secret configured
        if not self._api_key:
            return await call_next(request)

        # Skip validation for CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Skip validation for exempt paths (health, root)
        if request.url.path in self._exempt_paths:
            return await call_next(request)

        # Validate the key
        provided_key = request.headers.get("X-Api-Key")
        if not provided_key or provided_key != self._api_key:
            logger.warning(f"Rejected request to {request.url.path}: invalid API key")
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)
