# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A FastAPI application that transforms stories into print-ready PDF booklets for young children (ages 2-4). Uses LLM-powered story adaptation, AI-generated illustrations with visual consistency, and professional booklet formatting.

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
story input → Visual Analysis → LLM Adaptation → Image Generation → PDF Generation
                   ↓                  ↓                  ↓
            StoryVisualContext   Simplified Text    Consistent Images
```

**Pipeline stages:**
1. **Visual Analysis** (`llm_connector.analyze_story`) - Extracts `StoryVisualContext` (characters, setting, atmosphere, color palette) using structured outputs for consistent illustrations
2. **Story Adaptation** (`llm_connector.adapt_story`) - Simplifies text for target age group via Claude Haiku
3. **Image Generation** (`image_generator.BookImageGenerator`) - Creates illustrations with visual context injected into prompts; file-based caching by prompt hash
4. **PDF Generation** (`pdf_generator.generate_both_pdfs`) - Produces both `_booklet.pdf` (imposition-ordered for duplex printing) and `_review.pdf` (sequential for screen)

**Key data flow:**
- `BookGenerateRequest` (Pydantic) → `_generate_book_task` background task → `BookConfig`/`LLMConfig` dataclasses
- Text processing: `TextProcessor.process()` → `BookContent` with `BookPage` objects
- Jobs tracked in-memory via `jobs` dict in `src/api/routes/books.py`

## Key Modules

| Module | Purpose |
|--------|---------|
| `src/core/prompts.py` | All LLM prompts and `StoryVisualContext`/`Character` dataclasses |
| `src/core/llm_connector.py` | `OpenRouterClient` for text adaptation and story analysis |
| `src/core/text_processor.py` | `TextProcessor` splits text into `BookPage` objects |
| `src/core/pdf_generator.py` | `PDFBookletGenerator`, `FontManager`, page imposition logic |
| `src/core/image_generator.py` | `BookImageGenerator` with file-based caching in `image_cache/` |
| `src/api/schemas.py` | Pydantic models: `BookGenerateRequest`, `JobStatus` |
| `src/api/routes/books.py` | All book generation endpoints and background task logic |

## Conventions

- **Single API provider**: OpenRouter handles text (Claude Haiku), analysis (Gemini), and image generation. One `OPENROUTER_API_KEY` covers everything.
- **Import style**: Use `from src.core.X import Y` for core modules, `from src.api.X import Y` for API modules
- **Pre-formatted stories**: Use `skip_adaptation: true` when story is already formatted (first line = title, subsequent lines = one page each)
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
