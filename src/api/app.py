"""
FastAPI application for Children's Book Generator.

Run with: python main.py --reload
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv

from src.api.routes import health, books, stories
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
    logger.info("🚀 Application starting up...")
    
    # Startup: ensure output directory exists
    import os
    os.makedirs("output", exist_ok=True)
    os.makedirs("image_cache", exist_ok=True)
    logger.info("📁 Output directories ready: output/, image_cache/")
    
    # Check for API key
    if os.getenv("OPENROUTER_API_KEY"):
        logger.info("✅ OpenRouter API key configured")
    else:
        logger.warning("⚠️  No OpenRouter API key found - LLM/image features disabled")
    
    # Initialize database
    await init_db()

    yield

    # Shutdown: cleanup
    await close_db()
    logger.info("👋 Application shutting down...")


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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
