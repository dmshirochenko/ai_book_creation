# Remove BookConfig Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Delete the redundant `BookConfig` and `GeneratorConfig` dataclasses, passing `BookGenerateRequest` directly to core modules.

**Architecture:** `BookGenerateRequest` (Pydantic) becomes the single source of truth for book settings. Core modules (`pdf_generator`, `image_generator`) accept it directly instead of the intermediate `BookConfig` dataclass. Four previously-hardcoded fields (`font_family`, `margin_top`, `margin_left`, `margin_right`) move onto the API request with defaults.

**Tech Stack:** Python, FastAPI, Pydantic, ReportLab, pytest

---

### Task 1: Add new fields to BookGenerateRequest

**Files:**
- Modify: `src/api/schemas.py:11-51`

**Step 1: Add the 4 new fields to BookGenerateRequest**

Add these fields after `background_color` (line 35) in the `BookGenerateRequest` class:

```python
    font_family: str = Field("DejaVuSans", description="Font family for PDF text (Unicode-compatible)")
    margin_top: int = Field(50, ge=10, le=150, description="Top margin in points (72 points = 1 inch)")
    margin_left: int = Field(40, ge=10, le=150, description="Left margin in points")
    margin_right: int = Field(40, ge=10, le=150, description="Right margin in points")
```

**Step 2: Run tests to verify nothing breaks**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All 206 tests PASS (adding fields with defaults is backwards-compatible)

**Step 3: Commit**

```bash
git add src/api/schemas.py
git commit -m "feat: add font_family and margin fields to BookGenerateRequest"
```

---

### Task 2: Update pdf_generator to accept BookGenerateRequest

**Files:**
- Modify: `src/core/pdf_generator.py:27` (import)
- Modify: `src/core/pdf_generator.py:247-254` (BasePDFGenerator.__init__)
- Modify: `src/core/pdf_generator.py:626-637` (PDFBookletGenerator.__init__)
- Modify: `src/core/pdf_generator.py:703-737` (generate_booklet_pdf)
- Modify: `src/core/pdf_generator.py:743-754` (PDFSequentialGenerator.__init__)
- Modify: `src/core/pdf_generator.py:798-832` (generate_sequential_pdf)
- Modify: `src/core/pdf_generator.py:835-859` (generate_both_pdfs)

**Step 1: Update the import**

Change line 27 from:
```python
from src.core.config import BookConfig
```
to:
```python
from src.api.schemas import BookGenerateRequest
```

**Step 2: Update BasePDFGenerator.__init__ type annotation**

Change line 249 from:
```python
        config: BookConfig,
```
to:
```python
        config: BookGenerateRequest,
```

No field access changes needed — all field names (`font_family`, `font_size`, `title_font_size`, `margin_top`, `margin_left`, `margin_right`, `text_on_image`, `background_color`) already match between `BookConfig` and `BookGenerateRequest`.

**Step 3: Update PDFBookletGenerator.__init__ type annotation**

Change line 628 from:
```python
        config: BookConfig,
```
to:
```python
        config: BookGenerateRequest,
```

**Step 4: Update PDFSequentialGenerator.__init__ type annotation**

Change line 745 from:
```python
        config: BookConfig,
```
to:
```python
        config: BookGenerateRequest,
```

**Step 5: Update generate_booklet_pdf convenience function**

Change line 706 from:
```python
    config: Optional[BookConfig] = None,
```
to:
```python
    config: Optional[BookGenerateRequest] = None,
```

Change lines 727-728 from:
```python
    if config is None:
        config = BookConfig()
```
to:
```python
    if config is None:
        config = BookGenerateRequest(story="")
```

**Step 6: Update generate_sequential_pdf convenience function**

Change line 801 from:
```python
    config: Optional[BookConfig] = None,
```
to:
```python
    config: Optional[BookGenerateRequest] = None,
```

Change lines 822-823 from:
```python
    if config is None:
        config = BookConfig()
```
to:
```python
    if config is None:
        config = BookGenerateRequest(story="")
```

**Step 7: Update generate_both_pdfs function**

Change line 839 from:
```python
    config: Optional[BookConfig] = None,
```
to:
```python
    config: Optional[BookGenerateRequest] = None,
```

Change lines 858-859 from:
```python
    if config is None:
        config = BookConfig()
```
to:
```python
    if config is None:
        config = BookGenerateRequest(story="")
```

**Step 8: Run tests to verify**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All 206 tests PASS

**Step 9: Commit**

```bash
git add src/core/pdf_generator.py
git commit -m "refactor: pdf_generator accepts BookGenerateRequest instead of BookConfig"
```

---

### Task 3: Update image_generator to accept BookGenerateRequest

**Files:**
- Modify: `src/core/image_generator.py:19` (import)
- Modify: `src/core/image_generator.py:229` (BookImageGenerator.__init__ param type)
- Modify: `src/core/image_generator.py:236` (default fallback)
- Modify: `src/core/image_generator.py:298-299` (field access renames)

**Step 1: Update the import**

Change line 19 from:
```python
from src.core.config import BookConfig, DEFAULT_IMAGE_MODEL
```
to:
```python
from src.core.config import DEFAULT_IMAGE_MODEL
from src.api.schemas import BookGenerateRequest
```

**Step 2: Update BookImageGenerator.__init__ type and default**

Change line 229 from:
```python
        book_config: Optional[BookConfig] = None,
```
to:
```python
        book_config: Optional[BookGenerateRequest] = None,
```

Change line 236 from:
```python
        self.book_config = book_config or BookConfig()
```
to:
```python
        self.book_config = book_config or BookGenerateRequest(story="")
```

**Step 3: Update field access renames**

Change line 298 from:
```python
            book_title=self.book_config.cover_title or "Story Book",
```
to:
```python
            book_title=self.book_config.title or "Story Book",
```

Change line 299 from:
```python
            target_age=(self.book_config.target_age_min, self.book_config.target_age_max),
```
to:
```python
            target_age=(self.book_config.age_min, self.book_config.age_max),
```

**Step 4: Run tests to verify**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All 206 tests PASS

**Step 5: Commit**

```bash
git add src/core/image_generator.py
git commit -m "refactor: image_generator accepts BookGenerateRequest instead of BookConfig"
```

---

### Task 4: Update books.py route to pass request directly

**Files:**
- Modify: `src/api/routes/books.py:28` (remove BookConfig import)
- Modify: `src/api/routes/books.py:71-82` (delete BookConfig construction)
- Modify: `src/api/routes/books.py:155` (background_color override)
- Modify: `src/api/routes/books.py:186-188` (BookImageGenerator call)
- Modify: `src/api/routes/books.py:271-276` (generate_both_pdfs call)

**Step 1: Remove BookConfig import**

Change line 28 from:
```python
from src.core.config import BookConfig, LLMConfig
```
to:
```python
from src.core.config import LLMConfig
```

**Step 2: Delete the BookConfig construction block**

Delete lines 71-83 (the `book_config = BookConfig(...)` block and the log line after it). Replace with just a log line:

```python
            logger.info(f"[{job_id}] Book settings: age {request.age_min}-{request.age_max}, language: {request.language}")
```

**Step 3: Update background_color override from visual context**

Change line 155 from:
```python
                        if not request.background_color and visual_context.background_color:
                            book_config.background_color = visual_context.background_color
                            logger.info(f"[{job_id}] Using suggested background color: {visual_context.background_color}")
```
to:
```python
                        if not request.background_color and visual_context.background_color:
                            request.background_color = visual_context.background_color
                            logger.info(f"[{job_id}] Using suggested background color: {visual_context.background_color}")
```

**Step 4: Update BookImageGenerator instantiation**

Change the `BookImageGenerator(...)` call (around line 186) — replace `book_config` with `request`:

From:
```python
                    image_generator = BookImageGenerator(
                        image_config,
                        book_config,
                        visual_context,
```
to:
```python
                    image_generator = BookImageGenerator(
                        image_config,
                        request,
                        visual_context,
```

**Step 5: Update generate_both_pdfs call**

Change the `generate_both_pdfs(...)` call (around line 271) — replace `config=book_config` with `config=request`:

From:
```python
                generate_both_pdfs(
                    content=book_content,
                    booklet_path=booklet_path,
                    review_path=review_path,
                    config=book_config,
                    images=images,
                )
```
to:
```python
                generate_both_pdfs(
                    content=book_content,
                    booklet_path=booklet_path,
                    review_path=review_path,
                    config=request,
                    images=images,
                )
```

**Step 6: Run tests to verify**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All 206 tests PASS

**Step 7: Commit**

```bash
git add src/api/routes/books.py
git commit -m "refactor: pass BookGenerateRequest directly, remove BookConfig mapping"
```

---

### Task 5: Delete BookConfig and GeneratorConfig

**Files:**
- Modify: `src/core/config.py:18-61` (delete BookConfig class)
- Modify: `src/core/config.py:83-91` (delete GeneratorConfig class)
- Modify: `src/core/__init__.py:5,11-14` (remove exports)

**Step 1: Delete BookConfig class from config.py**

Remove the entire `BookConfig` dataclass (lines 18-61). Keep `LLMConfig` and the module-level constants.

**Step 2: Delete GeneratorConfig class from config.py**

Remove the entire `GeneratorConfig` dataclass (lines 83-91).

**Step 3: Update src/core/__init__.py**

Change line 5 from:
```python
from src.core.config import BookConfig, LLMConfig, GeneratorConfig
```
to:
```python
from src.core.config import LLMConfig
```

Remove `"BookConfig"` and `"GeneratorConfig"` from the `__all__` list (lines 12, 14).

**Step 4: Run tests to verify**

Run: `python -m pytest tests/ -v --tb=short`
Expected: FAIL — test_config.py still imports BookConfig. This is expected, we fix it in Task 6.

**Step 5: Commit**

```bash
git add src/core/config.py src/core/__init__.py
git commit -m "refactor: delete BookConfig and GeneratorConfig classes"
```

---

### Task 6: Update tests

**Files:**
- Modify: `tests/unit/test_config.py` (remove TestBookConfig, TestGeneratorConfig)
- Modify: `tests/conftest.py:6,23-25` (remove BookConfig fixture)
- Modify: `tests/integration/test_image_generator.py:12` (remove unused import)

**Step 1: Update test_config.py**

Replace the entire file with:

```python
"""Unit tests for src/core/config.py."""

import pytest

from src.core.config import LLMConfig


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.max_tokens == 2000
        assert config.temperature == 0.7

    def test_validate_with_key(self):
        config = LLMConfig(api_key="test-key")
        assert config.validate() is True

    def test_validate_without_key(self):
        config = LLMConfig(api_key="")
        assert config.validate() is False
```

**Step 2: Update conftest.py**

Change line 6 from:
```python
from src.core.config import BookConfig, LLMConfig
```
to:
```python
from src.core.config import LLMConfig
```

Delete lines 23-25 (the `book_config` fixture):
```python
@pytest.fixture
def book_config():
    return BookConfig()
```

**Step 3: Update test_image_generator.py**

Delete line 12 (unused import):
```python
from src.core.config import BookConfig
```

**Step 4: Run all tests to verify everything passes**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS (count will drop by 3: removed TestBookConfig.test_defaults, TestBookConfig.test_custom_values, TestGeneratorConfig.test_default_sub_configs)

**Step 5: Commit**

```bash
git add tests/unit/test_config.py tests/conftest.py tests/integration/test_image_generator.py
git commit -m "test: remove BookConfig and GeneratorConfig tests, clean up imports"
```

---

### Task 7: Update documentation

**Files:**
- Modify: `CLAUDE.md:43` (key data flow)
- Modify: `.github/copilot-instructions.md:32` (module table)

**Step 1: Update CLAUDE.md**

Change line 43 from:
```
- `BookGenerateRequest` (Pydantic) → `_generate_book_task` background task → `BookConfig`/`LLMConfig` dataclasses
```
to:
```
- `BookGenerateRequest` (Pydantic) → `_generate_book_task` background task → passed directly to `pdf_generator` and `image_generator`
```

**Step 2: Update .github/copilot-instructions.md**

Change line 32 from:
```
| [src/core/config.py](src/core/config.py) | Dataclasses: `BookConfig`, `LLMConfig` |
```
to:
```
| [src/core/config.py](src/core/config.py) | Dataclass: `LLMConfig`, model constants |
```

**Step 3: Run tests one final time**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

**Step 4: Commit**

```bash
git add CLAUDE.md .github/copilot-instructions.md
git commit -m "docs: update references after BookConfig removal"
```
