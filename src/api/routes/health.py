"""
Health check endpoint.
"""

import os
from fastapi import APIRouter

from src.api.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Check API health and configuration status.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        openrouter_configured=bool(os.getenv("OPENROUTER_API_KEY"))
    )
