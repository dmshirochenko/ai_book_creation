# Children's Book Generator API

A FastAPI application that transforms stories into **print-ready PDF booklets** for young children (ages 2-4). Features LLM-powered story adaptation, AI-generated illustrations with visual consistency, and professional booklet formatting.

## Features

- 📖 **LLM-powered text adaptation** - Automatically simplifies stories for young children
- 🎨 **AI-generated illustrations** - Create unique, consistent images for each page
- 🔍 **Story visual analysis** - Extracts characters, setting, and color palette for consistent illustrations across all pages
- 🖨️ **Print-ready output** - PDF booklets with correct page ordering for double-sided printing
- 👀 **Review PDF** - Sequential A5 PDF for on-screen reading before printing
- 🌍 **Unicode support** - Works with multiple languages
- ⚡ **Async job processing** - Background task processing with status tracking
- 🗄️ **Image caching** - Cached images to reduce API costs

## Architecture

```
story input → Visual Analysis → LLM Adaptation → Image Generation → PDF Generation
                   ↓                  ↓                  ↓
            StoryVisualContext   Simplified Text    Consistent Images
```

**Pipeline:**
1. **Visual Analysis** - Extracts characters, setting, atmosphere, color palette (uses structured outputs)
2. **Story Adaptation** - Simplifies text for target age group
3. **Image Generation** - Creates illustrations with consistent visual context
4. **PDF Generation** - Produces booklet and review PDFs

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd book_generator

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Add your OPENROUTER_API_KEY to .env
```

Get an API key from [OpenRouter](https://openrouter.ai/keys) - this single key handles text adaptation, story analysis, and image generation.

## Quick Start

### Start the API Server

```bash
# Development mode with auto-reload
python main.py --reload

# Or with uvicorn directly
uvicorn src.api.app:app --reload --port 8000
```

The API will be available at `http://localhost:8000`

### API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/books/generate` | Generate book from JSON body |
| `POST` | `/api/v1/books/generate/file` | Generate book from uploaded file |
| `GET` | `/api/v1/books/{job_id}/status` | Check generation progress |
| `GET` | `/api/v1/books/{job_id}/download/{type}` | Download PDF (`booklet` or `review`) |
| `DELETE` | `/api/v1/books/{job_id}` | Delete job and files |
| `GET` | `/api/v1/health` | Health check |

## Usage Examples

### Generate a Book (cURL)

```bash
# Basic request
curl -X POST "http://localhost:8000/api/v1/books/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "story": "Once upon a time, there was a little bunny named Luna who loved to hop in the meadow under the stars.",
    "title": "Luna the Star Bunny",
    "generate_images": true
  }'

# Response
{
  "job_id": "abc123-def456",
  "message": "Book generation started"
}
```

### Check Job Status

```bash
curl "http://localhost:8000/api/v1/books/abc123-def456/status"

# Response
{
  "job_id": "abc123-def456",
  "status": "completed",
  "progress": "Book generation completed!",
  "title": "Luna the Star Bunny",
  "total_pages": 12,
  "booklet_filename": "Luna_the_Star_Bunny_20260125_143022_booklet.pdf",
  "review_filename": "Luna_the_Star_Bunny_20260125_143022_review.pdf"
}
```

### Download PDF

```bash
# Download booklet (for printing)
curl -O "http://localhost:8000/api/v1/books/abc123-def456/download/booklet"

# Download review (for screen reading)
curl -O "http://localhost:8000/api/v1/books/abc123-def456/download/review"
```

### Full Request with All Options

```bash
curl -X POST "http://localhost:8000/api/v1/books/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "story": "Your story text here...",
    "title": "My Story",
    "author": "A Bedtime Story",
    "age_min": 2,
    "age_max": 4,
    "language": "English",
    "font_size": 24,
    "title_font_size": 36,
    "skip_adaptation": false,
    "end_text": "The End",
    "generate_images": true,
    "image_model": "google/gemini-2.5-flash-image",
    "image_style": "children'\''s book illustration, soft watercolor style, gentle colors",
    "use_image_cache": true,
    "text_on_image": false
  }'
```

## Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `story` | string | **required** | Story text to convert |
| `title` | string | auto | Book title (extracted if not provided) |
| `author` | string | "A Bedtime Story" | Author name for cover |
| `age_min` | int | 2 | Minimum target age (1-10) |
| `age_max` | int | 4 | Maximum target age (1-10) |
| `language` | string | "English" | Target language |
| `font_size` | int | 24 | Content font size (12-48) |
| `title_font_size` | int | 36 | Title font size (18-72) |
| `skip_adaptation` | bool | false | Skip LLM text adaptation |
| `end_text` | string | "The End" | Final page text |
| `generate_images` | bool | false | Generate AI illustrations |
| `image_model` | string | "google/gemini-2.5-flash-image" | Image generation model |
| `image_style` | string | "soft watercolor style..." | Style for illustrations |
| `use_image_cache` | bool | true | Use cached images |
| `text_on_image` | bool | false | Render text on images |

## Pre-formatted Stories

Use `skip_adaptation: true` when your story is already formatted:

```
Title of the Story

First sentence for page 1.
Second sentence for page 2.
Another sentence for page 3.
```

- First line = book title
- Each subsequent line = one page
- Keep sentences short (1-2 per line)
- Aim for 8-16 content pages

## Output Files

| File | Format | Purpose |
|------|--------|---------|
| `*_booklet.pdf` | A4 landscape, booklet order | Double-sided printing & folding |
| `*_review.pdf` | A5 portrait, sequential | On-screen review |

## Project Structure

```
book_generator/
├── main.py                    # API server launcher
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
├── src/
│   ├── api/
│   │   ├── app.py             # FastAPI application
│   │   ├── schemas.py         # Pydantic models
│   │   └── routes/
│   │       ├── books.py       # Book generation endpoints
│   │       └── health.py      # Health check
│   └── core/
│       ├── config.py          # Configuration classes
│       ├── prompts.py         # All LLM prompts
│       ├── llm_connector.py   # OpenRouter client
│       ├── text_processor.py  # Text parsing
│       ├── image_generator.py # AI image generation
│       └── pdf_generator.py   # PDF booklet generation
├── examples/                  # Sample stories
├── image_cache/               # Cached images
└── output/                    # Generated PDFs
```

## Configuration

### Models

| Model | Default | Purpose |
|-------|---------|---------|
| `model` | `anthropic/claude-3-haiku` | Story adaptation |
| `analysis_model` | `google/gemini-2.5-flash` | Visual analysis (structured outputs) |
| `image_model` | `google/gemini-2.5-flash-image` | Image generation |

### Environment Variables

```bash
OPENROUTER_API_KEY=your_api_key_here
```

## Visual Consistency Feature

Before generating images, the API analyzes your story to extract:

- **Characters** - Name and visual description (e.g., "Luna: small fluffy white bunny with pink nose")
- **Setting** - Main location (e.g., "magical meadow with wildflowers")
- **Atmosphere** - Time, weather, mood (e.g., "warm sunset, peaceful")
- **Color Palette** - Suggested colors (e.g., "soft pastels, warm oranges")

This context is injected into every image prompt, ensuring characters look the same on every page.

## How to Print

1. **Print Settings:**
   - Paper: A4
   - Orientation: Landscape (automatic)
   - Duplex: Double-sided
   - Flip: Short edge

2. **After Printing:**
   - Take all sheets together
   - Fold in half
   - Your book is ready!

## Requirements

- Python 3.9+
- FastAPI & Uvicorn
- reportlab (PDF generation)
- httpx (API requests)
- python-dotenv (environment variables)

## License

MIT License - feel free to use and modify!
