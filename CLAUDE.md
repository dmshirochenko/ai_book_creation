# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastAPI application that transforms stories into print-ready PDF booklets for young children (ages 2-4). Uses LLM-powered story generation with structured JSON outputs, AI-generated illustrations with visual consistency, and professional booklet formatting.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add OPENROUTER_API_KEY

# Run API server (development)
python main.py --reload

# Or directly with uvicorn
uvicorn src.api.app:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`

## Architecture

```
story input → Visual Analysis → Image Generation → PDF Generation
                   ↓                  ↓
            StoryVisualContext    Consistent Images

POST /stories/create → Structured JSON generation (Gemini Flash) → Book PDF
```

**Pipeline stages:**
1. **Story Generation** (`story_generator.StoryGenerator`) - Generates original stories via structured JSON outputs (Gemini Flash), returns `{"title": "...", "pages": [{"text": "..."}]}`
2. **Visual Analysis** (`llm_connector.analyze_story`) - Extracts `StoryVisualContext` (characters, setting, atmosphere, color palette) using structured outputs for consistent illustrations
3. **Image Generation** (`image_generator.BookImageGenerator`) - Creates illustrations with visual context injected into prompts; file-based caching by prompt hash
4. **PDF Generation** (`pdf_generator.generate_both_pdfs`) - Produces both `_booklet.pdf` (imposition-ordered for duplex printing) and `_review.pdf` (sequential for screen)

**Key data flow:**
- `BookGenerateRequest` (Pydantic) → `generate_book_task` background task (`src/tasks/book_tasks.py`) → passed directly to `pdf_generator` and `image_generator`
- Text processing: `TextProcessor.process_raw_story()` or `TextProcessor.process_structured()` → `BookContent` with `BookPage` objects
- Story generation returns structured JSON stored as JSONB in `story_jobs.generated_story_json`

## Key Modules

| Module | Purpose |
|--------|---------|
| `src/core/prompts.py` | Visual analysis prompts, image prompts, `StoryVisualContext`/`Character` dataclasses |
| `src/core/story_prompts.py` | Story creation prompts, JSON schema for structured outputs, safety validation |
| `src/core/story_generator.py` | `StoryGenerator` for original story creation with safety guardrails |
| `src/core/llm_connector.py` | `OpenRouterClient` for story analysis and LLM calls |
| `src/core/text_processor.py` | `TextProcessor` splits text into `BookPage` objects |
| `src/core/pdf_generator.py` | `PDFBookletGenerator`, `FontManager`, page imposition logic |
| `src/core/image_generator.py` | `BookImageGenerator` with file-based caching in `image_cache/` |
| `src/core/config.py` | `LLMConfig` dataclass with dotenv, model constants |
| `src/core/retry.py` | `@async_retry` decorator with exponential backoff |
| `src/core/storage.py` | R2 storage singleton — upload, download, presigned URLs |
| `src/core/cloudwatch_logging.py` | Selective CloudWatch logging (pipeline modules only) |
| `src/api/schemas.py` | Pydantic models: `BookGenerateRequest`, `JobStatus` |
| `src/api/routes/books.py` | Book generation endpoints (thin handlers — validate, dispatch, respond) |
| `src/api/routes/stories.py` | Story creation endpoints (thin handlers) |
| `src/api/deps.py` | FastAPI dependencies — DB session, user ID from `X-User-Id` header |
| `src/api/rate_limit.py` | `slowapi` rate limiting by User-ID or IP fallback |
| `src/api/middleware.py` | `X-Api-Key` validation middleware (disabled in dev) |
| `src/db/repository.py` | Functional CRUD layer — module-level async functions per entity |
| `src/services/credit_service.py` | Credit balance, FIFO batch consumption, reserve/confirm/release |
| `src/tasks/book_tasks.py` | Background tasks: `generate_book_task`, `regenerate_book_task` |
| `src/tasks/story_tasks.py` | Background task: `create_story_task` |

## Data Access Patterns

- **Functional repository**: `src/db/repository.py` uses module-level async functions (not class-based). One function per operation, organized by entity (BookJobs, StoryJobs, etc.). Naming: `create_X`, `get_X`, `update_X`, `list_X`, `delete_X`.
- **Service layer**: Services are instantiated per-request with session injection — `CreditService(db)`. Don't use singletons or class methods for services.
- **Credit transactions**: Use the reserve → confirm/release pattern. `reserve()` locks rows with `SELECT...FOR UPDATE` for FIFO batch consumption. `confirm()` on success, `release()` on failure to return credits.

## Background Tasks

- Route handlers dispatch via `BackgroundTasks.add_task()` — complex async logic lives in `src/tasks/`, not in route handlers.
- Background tasks acquire their own DB session via `get_session_factory()` (never share the request session).
- Long-running tasks are wrapped in `asyncio.wait_for(timeout=...)` for safety.
- On failure, always `release()` reserved credits before re-raising.
- Periodic cleanup: `_cleanup_stale_reservations()` runs every 5 minutes via `asyncio.create_task()` in the app lifespan.

## Database

- **Migrations**: Always use Alembic with manually written migration scripts. Do NOT use `Base.metadata.create_all()` for schema changes or attempt autogenerate without a live DB connection.
- **Migrations are DDL only**: Alembic migrations must contain only schema/table changes (CREATE, ALTER, DROP). Never insert seed data, configuration rows, or any DML (INSERT/UPDATE/DELETE) in migrations. Use separate scripts or admin endpoints for data seeding.
- **ORM models in migrations**: Always use SQLAlchemy ORM column types and operations (`op.add_column`, `op.create_table`, etc.) in Alembic migrations. Never write raw/pure SQL.
- **ORM style**: SQLAlchemy 2.0 with `Mapped[type]` and `mapped_column()`. UUID primary keys, JSONB for flexible metadata, `CheckConstraint` for validation, `Index` for query performance.
- **Production**: Uses Supabase with pgbouncer — requires `statement_cache_size=0` for asyncpg connections.
- **Sessions**: Use async SQLAlchemy sessions. Avoid sharing sessions across concurrent tasks (use `asyncio.gather()` carefully).

## Testing

- Run the full test suite after any code changes: `.venv/bin/python -m pytest tests/ -v` (no `--timeout` flag — pytest-timeout is not installed).
- The project has 260+ tests — verify all pass before committing.
- After refactors or removals, run tests immediately to catch circular imports and broken references.
- **Autouse fixture**: `_clear_env_keys` automatically clears API keys in all tests to prevent real service calls.
- **Unit-test services**: Use `AsyncMock()` for the DB session — don't hit a real database.
- **API tests**: Use the `async_client` fixture which patches `init_db` to avoid DB connections.

## Conventions

- **Single API provider**: OpenRouter handles story generation (Gemini Flash), analysis (Gemini), and image generation. One `OPENROUTER_API_KEY` covers everything.
- **Import style**: Use `from src.core.X import Y` for core modules, `from src.api.X import Y` for API modules, `from src.tasks.X import Y` for background tasks.
- **Thin controllers**: Route handlers only validate input, dispatch background tasks, and return responses. Business/orchestration logic lives in `src/tasks/`.
- **Structured outputs**: Story generation uses JSON Schema structured outputs for reliable parsing.
- **Error tolerance**: LLM/image failures log warnings but don't halt generation.
- **Visual consistency**: `StoryVisualContext` extracted before image generation is injected into all image prompts.
- **Config**: Uses `@dataclass` (`LLMConfig`) with `python-dotenv`, not Pydantic BaseSettings.
- **Rate limiting**: `@limiter.limit("3/minute")` decorator, keyed by `X-User-Id` header with IP fallback.
- **Inter-service auth**: Supabase Edge Functions send `X-Api-Key` header, validated by `ApiKeyMiddleware`. Middleware is disabled when key is not configured (dev mode).
- **Dev mode**: When `DATABASE_URL` is unset, `get_current_user_id()` falls back to a fixed dev UUID for local testing.
- **Storage**: Use `get_storage()` singleton for all R2 operations (upload, download, presigned URLs, batch delete).
- **Retry**: Use `@async_retry(max_attempts=3, backoff_base=2.0)` decorator for flaky external calls (image generation, LLM).

## Output

```
output/
  Story_Title_YYYYMMDD_HHMMSS_booklet.pdf  # For printing (duplex, short-edge)
  Story_Title_YYYYMMDD_HHMMSS_review.pdf   # For screen review
image_cache/
  <hash>.png  # Cached generated images
```
