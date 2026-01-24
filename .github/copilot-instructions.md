# Copilot Instructions for Children's Book Generator

## Project Overview

A Python CLI application that transforms stories into **print-ready PDF booklets** for young children (ages 2-4). The pipeline: story input → LLM adaptation → optional AI illustration → PDF generation (A4 landscape sheets that fold into A5 books).

## Architecture & Data Flow

```
main.py (CLI entry) → llm_connector.py (adapt text) → text_processor.py (paginate)
                                                                ↓
                    pdf_generator.py (booklet + review PDFs) ← image_generator.py (optional)
```

- **Single API Provider**: OpenRouter handles both text (Claude Haiku) and image generation (Gemini). One `OPENROUTER_API_KEY` in `.env` covers everything.
- **Dual PDF Output**: Always generates two PDFs—`_booklet.pdf` (imposition-ordered for duplex printing) and `_review.pdf` (sequential for screen reading).
- **Booklet Math**: Uses `BookletPageOrderer` in [pdf_generator.py](pdf_generator.py#L145) for page imposition. Pages must be multiples of 4; blanks are auto-inserted.

## Key Files

| File | Purpose |
|------|---------|
| [main.py](main.py) | CLI argument parsing, orchestration |
| [config.py](config.py) | Dataclasses: `BookConfig`, `LLMConfig`, `GeneratorConfig` |
| [llm_connector.py](llm_connector.py) | `OpenRouterClient` for story simplification |
| [text_processor.py](text_processor.py) | `TextProcessor` splits text into `BookPage` objects |
| [pdf_generator.py](pdf_generator.py) | `PDFBookletGenerator`, `FontManager`, page imposition |
| [image_generator.py](image_generator.py) | `BookImageGenerator` with file-based caching in `image_cache/` |

## Developer Workflow

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add OPENROUTER_API_KEY

# Basic run (text-only)
python main.py --file examples/sleepy_bunny.txt --no-adapt --title "The Sleepy Bunny"

# Full pipeline with images
python main.py --file examples/little_star.txt --generate-images -v
```

## Conventions & Patterns

1. **Pre-formatted Stories**: Use `--no-adapt` to skip LLM. Input format: first line = title, subsequent lines = one page each.
2. **Image Caching**: Images are cached by prompt hash in `image_cache/`. Use `--no-image-cache` to regenerate.
3. **Font Handling**: `FontManager` searches system paths for Unicode fonts (DejaVuSans preferred). Falls back to Helvetica.
4. **Error Tolerance**: LLM/image failures log warnings but don't halt execution—the book generates with available content.

## Adding New Features

- **New LLM provider**: Extend `OpenRouterClient` or create sibling class; the prompt template is in `_build_adaptation_prompt()`.
- **Custom page types**: Add to `PageType` enum in [text_processor.py](text_processor.py#L14), then handle in `_draw_page_content()` method.
- **New image model**: Pass via `--image-model`; ensure it supports OpenRouter's image output format.

## Output Structure

```
output/
  Story_Title_20260124_143022_booklet.pdf  # For printing (duplex, short-edge)
  Story_Title_20260124_143022_review.pdf   # For screen review
image_cache/
  <hash>.png  # Cached generated images
```
