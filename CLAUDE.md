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
- `BookGenerateRequest` (Pydantic) → `_generate_book_task` background task → passed directly to `pdf_generator` and `image_generator`
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
| `src/api/schemas.py` | Pydantic models: `BookGenerateRequest`, `JobStatus` |
| `src/api/routes/books.py` | All book generation endpoints and background task logic |

## Conventions

- **Single API provider**: OpenRouter handles story generation (Gemini Flash), analysis (Gemini), and image generation. One `OPENROUTER_API_KEY` covers everything.
- **Import style**: Use `from src.core.X import Y` for core modules, `from src.api.X import Y` for API modules
- **Structured outputs**: Story generation uses JSON Schema structured outputs for reliable parsing
- **Error tolerance**: LLM/image failures log warnings but don't halt generation
- **Visual consistency**: `StoryVisualContext` extracted before image generation is injected into all image prompts

## Output

```
output/
  Story_Title_YYYYMMDD_HHMMSS_booklet.pdf  # For printing (duplex, short-edge)
  Story_Title_YYYYMMDD_HHMMSS_review.pdf   # For screen review
image_cache/
  <hash>.png  # Cached generated images
```
