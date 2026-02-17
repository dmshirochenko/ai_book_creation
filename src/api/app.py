"""
FastAPI application for Children's Book Generator.

Run with: python main.py --reload
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from dotenv import load_dotenv

from src.api.routes import health, books, stories
from src.core.cloudwatch_logging import setup_cloudwatch_logging, flush_cloudwatch_logging
from src.db.engine import init_db, close_db


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("Application starting up...")

    # CloudWatch logging (sends pipeline logs only, opt-in via CLOUDWATCH_ENABLED=true)
    setup_cloudwatch_logging()

    import os
    from src.core.storage import is_r2_configured

    # Check for API key
    if os.getenv("OPENROUTER_API_KEY"):
        logger.info("OpenRouter API key configured")
    else:
        logger.warning("No OpenRouter API key found - LLM/image features disabled")

    # Check R2 storage
    if is_r2_configured():
        logger.info("Cloudflare R2 storage configured")
    else:
        logger.warning("R2 storage not configured - file storage will fail")

    # Initialize database
    await init_db()

    yield

    # Shutdown: cleanup
    await close_db()
    logger.info("Application shutting down...")
    flush_cloudwatch_logging()


app = FastAPI(
    title="Children's Book Generator API",
    description="""
Generate print-ready PDF booklets from stories for young children.

## Features
- **Original Story Creation** - Generate age-appropriate stories from prompts with safety guardrails
- **LLM-powered text adaptation** - Automatically simplifies stories for ages 2-4
- **AI-generated illustrations** - Create unique images via OpenRouter
- **Print-ready output** - PDF booklets with correct page ordering for double-sided printing
- **Review PDF** - Sequential A5 PDF for on-screen reading

## Workflow

### Option 1: Create Original Story
1. **POST** `/api/v1/stories/create` - Generate a story from your prompt
2. **GET** `/api/v1/stories/{job_id}/status` - Check status and get generated story
3. **POST** `/api/v1/books/generate` - Convert story to book (use generated story text)
4. **GET** `/api/v1/books/{job_id}/download/booklet` - Download print-ready PDF

### Option 2: Use Existing Story
1. **POST** `/api/v1/books/generate` - Submit a story for processing
2. **GET** `/api/v1/books/{job_id}/status` - Check generation progress
3. **GET** `/api/v1/books/{job_id}/download/booklet` - Download print-ready PDF
4. **GET** `/api/v1/books/{job_id}/download/review` - Download review PDF
    """,
    version="1.0.0",
    lifespan=lifespan,
)

# Trusted Host middleware — reject requests with unexpected Host headers
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["api.talehop.com", "localhost", "127.0.0.1"],
)

# CORS middleware — only allow frontend and Supabase origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://talehop.com",
        "https://www.talehop.com",
        "http://localhost:8080",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-User-Id"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(books.router, prefix="/api/v1")
app.include_router(stories.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    """Redirect to API documentation."""
    return {
        "message": "Children's Book Generator API",
        "docs": "/docs",
        "redoc": "/redoc",
    }
