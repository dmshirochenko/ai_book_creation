"""
Configuration endpoints.

Public endpoints that expose non-sensitive application configuration.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_db
from src.api.schemas import (
    TEXT_ON_IMAGE_SUPPORTED_LANGUAGES,
    IllustrationStyleItem,
    IllustrationStylesResponse,
)
from src.db import repository as repo

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.get("/text-on-image-languages")
async def get_text_on_image_languages() -> dict:
    """
    Get the list of language codes that support text-on-image rendering.

    Returns ISO 639-1 codes for languages where AI image models
    can reliably render text. The frontend uses this to enable/disable
    the "Text on Image" toggle in book configuration.
    """
    return {"supported_languages": TEXT_ON_IMAGE_SUPPORTED_LANGUAGES}


@router.get("/illustration-styles", response_model=IllustrationStylesResponse)
async def get_illustration_styles(
    db: AsyncSession = Depends(get_db),
) -> IllustrationStylesResponse:
    """
    Get available illustration styles for book generation.

    Returns active styles ordered by display_order. The frontend uses
    slug for style selection and icon_name for Lucide icon mapping.
    """
    styles = await repo.list_active_illustration_styles(db)
    return IllustrationStylesResponse(
        styles=[
            IllustrationStyleItem(
                slug=s.slug,
                icon_name=s.icon_name,
                display_order=s.display_order,
                preview_image_url=s.preview_image_url,
            )
            for s in styles
        ]
    )
