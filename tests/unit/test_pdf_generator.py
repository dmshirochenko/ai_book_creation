"""Unit tests for src/core/pdf_generator.py (pure-logic parts)."""

import pytest

from src.core.pdf_generator import (
    BookletPageOrderer,
    TextWrapCache,
    ImageCache,
    get_print_instructions,
)


# =============================================================================
# BookletPageOrderer
# =============================================================================


class TestBookletPageOrderer:
    def test_4_pages(self):
        spreads = BookletPageOrderer.calculate_spreads(4)
        # 1 sheet, front: (4, 1), back: (2, 3)
        assert len(spreads) == 2
        assert spreads[0] == (4, 1)
        assert spreads[1] == (2, 3)

    def test_8_pages(self):
        spreads = BookletPageOrderer.calculate_spreads(8)
        # 2 sheets
        assert len(spreads) == 4
        assert spreads[0] == (8, 1)
        assert spreads[1] == (2, 7)
        assert spreads[2] == (6, 3)
        assert spreads[3] == (4, 5)

    def test_odd_total_rounds_up(self):
        # 5 pages → needs 2 sheets (8 slots)
        spreads = BookletPageOrderer.calculate_spreads(5)
        assert len(spreads) == 4  # 2 sheets × 2 sides

    def test_get_page_or_blank_valid(self, sample_book_content):
        page = BookletPageOrderer.get_page_or_blank(sample_book_content.pages, 1)
        assert page is not None
        assert page.page_number == 1

    def test_get_page_or_blank_out_of_range(self, sample_book_content):
        page = BookletPageOrderer.get_page_or_blank(sample_book_content.pages, 100)
        assert page is None

    def test_get_page_or_blank_zero(self, sample_book_content):
        page = BookletPageOrderer.get_page_or_blank(sample_book_content.pages, 0)
        assert page is None


# =============================================================================
# TextWrapCache
# =============================================================================


class TestTextWrapCache:
    def test_cache_miss(self):
        cache = TextWrapCache()
        assert cache.get_wrapped("hello", "Helvetica", 12, 200) is None

    def test_cache_hit(self):
        cache = TextWrapCache()
        cache.set_wrapped("hello world", "Helvetica", 12, 200, ["hello", "world"])
        result = cache.get_wrapped("hello world", "Helvetica", 12, 200)
        assert result == ["hello", "world"]

    def test_different_params_different_keys(self):
        cache = TextWrapCache()
        cache.set_wrapped("text", "Helvetica", 12, 200, ["line1"])
        cache.set_wrapped("text", "Helvetica", 14, 200, ["line2"])
        assert cache.get_wrapped("text", "Helvetica", 12, 200) == ["line1"]
        assert cache.get_wrapped("text", "Helvetica", 14, 200) == ["line2"]


# =============================================================================
# ImageCache
# =============================================================================


class TestImageCache:
    def test_no_images(self):
        cache = ImageCache()
        assert cache.get_image_reader(1) is None

    def test_valid_png_image(self):
        # Minimal 1x1 PNG
        import base64
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        png_bytes = base64.b64decode(png_b64)
        cache = ImageCache({1: png_bytes})
        reader = cache.get_image_reader(1)
        assert reader is not None

    def test_missing_page(self):
        cache = ImageCache({1: b"data"})
        assert cache.get_image_reader(5) is None

    def test_invalid_image_data_returns_none(self):
        cache = ImageCache({1: b"not a real image"})
        reader = cache.get_image_reader(1)
        assert reader is None

    def test_caches_result(self):
        import base64
        png_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        png_bytes = base64.b64decode(png_b64)
        cache = ImageCache({1: png_bytes})
        reader1 = cache.get_image_reader(1)
        reader2 = cache.get_image_reader(1)
        assert reader1 is reader2  # Same object returned


# =============================================================================
# get_print_instructions
# =============================================================================


class TestGetPrintInstructions:
    def test_english(self):
        instructions = get_print_instructions("English")
        assert "PRINTING INSTRUCTIONS" in instructions
        assert "A4" in instructions

    def test_german(self):
        instructions = get_print_instructions("German")
        assert "DRUCKANLEITUNG" in instructions

    def test_spanish(self):
        instructions = get_print_instructions("Spanish")
        assert "INSTRUCCIONES" in instructions

    def test_unknown_language_falls_back_to_english(self):
        instructions = get_print_instructions("Japanese")
        assert "PRINTING INSTRUCTIONS" in instructions
