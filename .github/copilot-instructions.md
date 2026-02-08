# Copilot Instructions for Children's Book Generator

## Project Overview

A Python application that transforms stories into **print-ready PDF booklets** for young children (ages 2-4). Exposes a **FastAPI REST API** for book generation. Pipeline: story input → optional AI illustration → PDF generation (A4 landscape sheets that fold into A5 books). Story generation uses structured JSON outputs via Gemini Flash.

## Architecture & Data Flow

```
main.py (API launcher)
    ↓
src/api/app.py → src/api/routes/books.py
                        ↓
              src/core/llm_connector.py → src/core/text_processor.py
                                                    ↓
                        src/core/pdf_generator.py ← src/core/image_generator.py (optional)
```

- **Single API Provider**: OpenRouter handles story generation (Gemini Flash), analysis (Gemini), and image generation. One `OPENROUTER_API_KEY` in `.env` covers everything.
- **Dual PDF Output**: Always generates two PDFs—`_booklet.pdf` (imposition-ordered for duplex printing) and `_review.pdf` (sequential for screen reading).
- **Async Job Processing**: API uses FastAPI `BackgroundTasks` for long-running generation; jobs tracked in-memory via `jobs` dict in [src/api/routes/books.py](src/api/routes/books.py).

## Key Files

| File | Purpose |
|------|---------|
| [main.py](main.py) | API server launcher (uvicorn with argparse) |
| [src/api/app.py](src/api/app.py) | FastAPI app, CORS, lifespan |
| [src/api/schemas.py](src/api/schemas.py) | Pydantic models: `BookGenerateRequest`, `JobStatus` |
| [src/api/routes/books.py](src/api/routes/books.py) | `/generate`, `/status`, `/download` endpoints |
| [src/api/routes/health.py](src/api/routes/health.py) | Health check endpoint |
| [src/core/config.py](src/core/config.py) | Dataclass: `LLMConfig`, model constants |
| [src/core/prompts.py](src/core/prompts.py) | Visual analysis and image generation prompts |
| [src/core/llm_connector.py](src/core/llm_connector.py) | `OpenRouterClient` for story analysis and LLM calls |
| [src/core/text_processor.py](src/core/text_processor.py) | `TextProcessor` splits text into `BookPage` objects |
| [src/core/pdf_generator.py](src/core/pdf_generator.py) | `PDFBookletGenerator`, `FontManager`, page imposition |
| [src/core/image_generator.py](src/core/image_generator.py) | `BookImageGenerator` with file-based caching |

## Developer Workflow

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add OPENROUTER_API_KEY

# Run API server
python main.py --reload

# Or directly with uvicorn
uvicorn src.api.app:app --reload --port 8000
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/books/generate` | Generate book from JSON body |
| `GET` | `/api/v1/books/{job_id}/status` | Check generation progress |
| `GET` | `/api/v1/books/{job_id}/download/{type}` | Download PDF (`booklet` or `review`) |
| `DELETE` | `/api/v1/books/{job_id}` | Delete job and files |
| `GET` | `/api/v1/health` | Health check |

## Conventions & Patterns

1. **Job-based async**: Generation runs in background; poll `/status` for completion.
2. **Pydantic validation**: All request bodies validated via schemas in [src/api/schemas.py](src/api/schemas.py).
3. **Pre-formatted Stories**: Input: first line = title, subsequent lines = one page each.
4. **Image Caching**: Images cached by prompt hash in `image_cache/`. Set `use_image_cache: false` to regenerate.
5. **Error Tolerance**: LLM/image failures log warnings but don't halt—book generates with available content.
6. **Import Convention**: Use `from src.core.X import Y` for core modules and `from src.api.X import Y` for API modules.
7. **Visual Consistency**: Before image generation, story is analyzed to extract `StoryVisualContext` (characters, setting, atmosphere, color palette) which is injected into all image prompts for consistent illustrations.

## Output Structure

```
output/
  Story_Title_20260124_143022_booklet.pdf  # For printing (duplex, short-edge)
  Story_Title_20260124_143022_review.pdf   # For screen review
image_cache/
  <hash>.png  # Cached generated images
```
