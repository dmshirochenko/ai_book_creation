# Remove BookConfig Design

## Problem

`BookConfig` is a redundant intermediate dataclass that:
- Duplicates defaults already defined in `BookGenerateRequest` (Pydantic API schema)
- Has 7 dead fields nobody reads (`language`, `author_name`, `end_page_text`, `paper_size`, `output_dpi`, `margin_bottom`, `max_sentences_per_page`, `max_characters_per_page`)
- Requires manual field-by-field mapping in `books.py:71-82` every time a field is added
- `GeneratorConfig` wrapper class is also completely unused in production

## Decision

Delete `BookConfig` and `GeneratorConfig`. Pass `BookGenerateRequest` directly to core modules (`pdf_generator`, `image_generator`).

### Rationale
- Core modules are only ever called from the FastAPI background task — no standalone usage
- Most field names already match between `BookConfig` and `BookGenerateRequest`
- Eliminates all mapping code and duplicated defaults
- 4 active fields not yet on the API request (`font_family`, `margin_top`, `margin_left`, `margin_right`) become new API fields with defaults — making them user-configurable for free

## Changes

### `src/core/config.py`
- Delete `BookConfig` class
- Delete `GeneratorConfig` class
- Keep `LLMConfig`, `DEFAULT_IMAGE_MODEL`, `DEFAULT_ANALYSIS_MODEL`

### `src/api/schemas.py`
- Add 4 new fields to `BookGenerateRequest`:
  - `font_family: str = Field("DejaVuSans")`
  - `margin_top: int = Field(50, ge=10, le=150)`
  - `margin_left: int = Field(40, ge=10, le=150)`
  - `margin_right: int = Field(40, ge=10, le=150)`

### `src/core/pdf_generator.py`
- Change `BasePDFGenerator.__init__` param type: `config: BookConfig` → `config: BookGenerateRequest`
- Same for `PDFBookletGenerator`, `PDFSequentialGenerator`, convenience functions
- Most field accesses unchanged (names match)
- Update import: `from src.core.config import BookConfig` → `from src.api.schemas import BookGenerateRequest`

### `src/core/image_generator.py`
- Change `BookImageGenerator.__init__` param type: `book_config: BookConfig` → `book_config: BookGenerateRequest`
- Rename field accesses:
  - `book_config.cover_title` → `book_config.title`
  - `book_config.target_age_min` → `book_config.age_min`
  - `book_config.target_age_max` → `book_config.age_max`
- Update import

### `src/api/routes/books.py`
- Delete `BookConfig` import and construction block (lines 71-82)
- Pass `request` directly to `BookImageGenerator` and `generate_both_pdfs`
- Visual context `background_color` override mutates `request.background_color` directly

### `src/core/__init__.py`
- Remove `BookConfig`, `GeneratorConfig` from exports

### Tests
- `tests/unit/test_config.py` — Remove `TestBookConfig`, `TestGeneratorConfig`
- `tests/conftest.py` — Replace `BookConfig` fixture with `BookGenerateRequest` fixture
- `tests/integration/test_image_generator.py` — Use `BookGenerateRequest`

### Docs
- Update `CLAUDE.md` to reflect simplified architecture
