"""
Configuration endpoints.

Public endpoints that expose non-sensitive application configuration.
"""

from fastapi import APIRouter
from src.api.schemas import TEXT_ON_IMAGE_SUPPORTED_LANGUAGES

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
