# Children's Book Generator

A Python application that creates **print-ready PDF booklets** from stories, designed specifically for young children. The output is formatted for A4 paper, double-sided printing, folded in half to create an A5 book.

## Features

- 📖 **LLM-powered text adaptation** - Automatically simplifies stories for young children (ages 2-4)
- 🎨 **AI-generated illustrations** - Create unique images for each page via OpenRouter
- 🖨️ **Print-ready output** - PDF booklets with correct page ordering for double-sided printing
- 👀 **Review PDF** - Sequential A5 PDF for on-screen reading before printing
- 🌍 **Unicode support** - Works with multiple languages
- 📐 **Proper booklet layout** - A4 landscape spreads that fold into A5 portrait pages
- ⚙️ **Configurable** - Font sizes, target age, language, image styles, and more

## Installation

1. Clone or download this project
2. Create a virtual environment and install dependencies:

```bash
cd book_generator
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Configure OpenRouter API key in `.env`:
   - Copy `.env.example` to `.env`
   - Get an API key from [OpenRouter](https://openrouter.ai/keys)
   - This single key is used for both text adaptation AND image generation

## Quick Start

### Basic Usage (Text Only)

```bash
# Generate from a text file
python main.py --file examples/little_star.txt

# Generate from inline text
python main.py --story "Once upon a time, there was a happy little cloud..."

# Skip LLM adaptation (use pre-formatted text)
python main.py --file examples/sleepy_bunny.txt --no-adapt --title "The Sleepy Bunny"
```

### With AI-Generated Illustrations

```bash
# Generate with images (uses OpenRouter)
python main.py --file examples/little_star.txt --generate-images

# Use a different image model
python main.py --file examples/little_star.txt --generate-images --image-model "stabilityai/stable-diffusion-xl"

# Custom image style
python main.py --file examples/little_star.txt --generate-images \
  --image-style "cute cartoon style, bright colors, simple shapes"

# Verbose output to see progress
python main.py --file examples/little_star.txt --generate-images -v
```

### With Options

```bash
# Specify language and target age
python main.py --file story.txt --language German --age 3 5

# Custom output path
python main.py --file story.txt --output my_book.pdf

# Larger font for very young children
python main.py --file story.txt --font-size 28 --title-font-size 42

# With printing instructions
python main.py --file story.txt --print-instructions

# Full example with images
python main.py --file examples/sleepy_bunny.txt \
  --no-adapt --title "The Sleepy Bunny" \
  --generate-images \
  --verbose --print-instructions
```

## Command Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--story`, `-s` | Story text as string | - |
| `--file`, `-f` | Path to story text file | - |
| `--title`, `-t` | Book title | Extracted from story |
| `--author`, `-a` | Author name | "A Bedtime Story" |
| `--age MIN MAX` | Target age range | 2 4 |
| `--language`, `-l` | Target language | English |
| `--font-size` | Content font size (pt) | 24 |
| `--title-font-size` | Title font size (pt) | 36 |
| `--output`, `-o` | Output PDF path | Auto-generated |
| `--output-dir` | Output directory | `output/` |
| `--no-adapt` | Skip LLM adaptation | False |
| `--end-text` | Final page text | "The End" |
| `--generate-images` | Generate AI illustrations via OpenRouter | False |
| `--image-model` | OpenRouter image model | openai/dall-e-3 |
| `--image-style` | Style description for images | watercolor children's book |
| `--no-image-cache` | Regenerate all images | False |
| `--verbose`, `-v` | Enable verbose output | False |
| `--print-instructions` | Show printing guide | False |

## Output Files

The generator produces **two PDF files**:

| File | Format | Purpose |
|------|--------|---------|
| `*_booklet.pdf` | A4 landscape, booklet page order | For double-sided printing & folding |
| `*_review.pdf` | A5 portrait, sequential pages | For on-screen review before printing |

## Story Format

When using `--no-adapt`, format your story as:

```
Title of the Story

First sentence of page 1.
Second sentence for page 2.
Another sentence for page 3.
...
```

- First line = book title
- Each subsequent line = one page
- Keep sentences short (1-2 per line)
- Aim for 8-16 content pages

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

## Project Structure

```
book_generator/
├── main.py              # CLI entry point
├── config.py            # Configuration classes
├── llm_connector.py     # OpenRouter API client for text
├── image_generator.py   # AI image generation (DALL-E, Stability, etc.)
├── text_processor.py    # Text parsing and page splitting
├── pdf_generator.py     # PDF booklet generation with images
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── examples/            # Sample stories
│   ├── little_star.txt
│   └── sleepy_bunny.txt
├── image_cache/         # Cached generated images
└── output/              # Generated PDFs
```

## API Usage

You can also use the modules programmatically:

```python
from config import BookConfig
from llm_connector import adapt_story_for_children
from text_processor import TextProcessor
from image_generator import ImageConfig, ImageProvider, BookImageGenerator
from pdf_generator import generate_both_pdfs

# Configure
book_config = BookConfig(target_age_min=2, target_age_max=4)

# Process story into pages
processor = TextProcessor()
book_content = processor.process_raw_story(
    story="Your pre-formatted story...",
    title="My Book"
)

# Generate images (optional)
image_config = ImageConfig(provider=ImageProvider.OPENAI)
image_gen = BookImageGenerator(image_config, book_config)

page_data = [{'page_number': p.page_number, 'content': p.content, 
              'page_type': p.page_type.value} for p in book_content.pages]
image_results = image_gen.generate_all_images(page_data, "Story context...")

images = {num: r.image_data for num, r in image_results.items() if r.success}

# Generate PDFs
generate_both_pdfs(
    content=book_content,
    booklet_path="output/book_booklet.pdf",
    review_path="output/book_review.pdf",
    config=book_config,
    images=images
)
```

## Image Caching

Generated images are cached in `image_cache/` to avoid regenerating identical images. This saves API costs and time on subsequent runs. Use `--no-image-cache` to force regeneration.

## Requirements

- Python 3.9+
- reportlab (PDF generation)
- httpx (API requests)
- python-dotenv (environment variables)

## Font Support

The generator automatically searches for Unicode-compatible fonts:
- DejaVu Sans (recommended)
- Noto Sans
- Free Sans
- Arial

If no Unicode font is found, it falls back to Helvetica (may not support all characters).

## License

MIT License - feel free to use and modify!
