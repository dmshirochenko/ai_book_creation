"""Unit tests for src/core/text_processor.py."""

import pytest

from src.core.text_processor import (
    TextProcessor,
    BookContent,
    BookPage,
    PageType,
    validate_book_content,
)


# =============================================================================
# BookPage
# =============================================================================


class TestBookPage:
    def test_is_empty_with_blank_content(self):
        page = BookPage(page_type=PageType.CONTENT, content="")
        assert page.is_empty() is True

    def test_is_empty_with_whitespace(self):
        page = BookPage(page_type=PageType.CONTENT, content="   \n ")
        assert page.is_empty() is True

    def test_is_empty_with_real_content(self):
        page = BookPage(page_type=PageType.CONTENT, content="Hello")
        assert page.is_empty() is False


# =============================================================================
# BookContent
# =============================================================================


class TestBookContent:
    def test_total_pages(self, sample_book_content):
        assert sample_book_content.total_pages == 8

    def test_is_valid_for_booklet_even(self, sample_book_content):
        assert sample_book_content.is_valid_for_booklet() is True

    def test_is_valid_for_booklet_odd(self):
        content = BookContent(title="Test", pages=[
            BookPage(page_type=PageType.COVER, content="T", page_number=1),
            BookPage(page_type=PageType.CONTENT, content="A", page_number=2),
            BookPage(page_type=PageType.END, content="The End", page_number=3),
        ])
        assert content.is_valid_for_booklet() is False


# =============================================================================
# TextProcessor._split_into_sentences
# =============================================================================


class TestSplitIntoSentences:
    def test_simple_sentences(self, text_processor):
        result = text_processor._split_into_sentences("Hello world. How are you?")
        assert result == ["Hello world.", "How are you?"]

    def test_exclamation_marks(self, text_processor):
        result = text_processor._split_into_sentences("Wow! Amazing!")
        assert result == ["Wow!", "Amazing!"]

    def test_single_sentence(self, text_processor):
        result = text_processor._split_into_sentences("Just one sentence.")
        assert result == ["Just one sentence."]

    def test_empty_string(self, text_processor):
        result = text_processor._split_into_sentences("")
        assert result == []

    def test_whitespace_only(self, text_processor):
        result = text_processor._split_into_sentences("   ")
        assert result == []


# =============================================================================
# TextProcessor._extract_title_and_content
# =============================================================================


class TestExtractTitleAndContent:
    def test_normal_story(self, text_processor):
        text = "My Title\nLine one.\nLine two."
        title, content = text_processor._extract_title_and_content(text)
        assert title == "My Title"
        assert "Line one." in content
        assert "Line two." in content

    def test_empty_text(self, text_processor):
        title, content = text_processor._extract_title_and_content("")
        # Empty string after strip+split yields [''], no non-empty line found
        assert title == ""
        assert content == ""

    def test_only_title(self, text_processor):
        title, content = text_processor._extract_title_and_content("Just A Title")
        assert title == "Just A Title"
        assert content == ""

    def test_leading_blank_lines(self, text_processor):
        text = "\n\n  My Title\nContent here."
        title, content = text_processor._extract_title_and_content(text)
        assert title == "My Title"
        assert "Content here." in content


# =============================================================================
# TextProcessor._split_text_to_pages
# =============================================================================


class TestSplitTextToPages:
    def test_short_lines_stay_as_pages(self, text_processor):
        content = "Line one.\nLine two.\nLine three."
        pages = text_processor._split_text_to_pages(content)
        assert len(pages) == 3

    def test_long_line_split_by_sentence(self):
        processor = TextProcessor(max_chars_per_page=30)
        content = "A very long sentence here. Another sentence follows."
        pages = processor._split_text_to_pages(content)
        assert len(pages) == 2

    def test_empty_content(self, text_processor):
        pages = text_processor._split_text_to_pages("")
        assert pages == []

    def test_blank_lines_skipped(self, text_processor):
        content = "Line one.\n\n\nLine two."
        pages = text_processor._split_text_to_pages(content)
        assert len(pages) == 2


# =============================================================================
# TextProcessor._ensure_even_pages
# =============================================================================


class TestEnsureEvenPages:
    def test_even_count_unchanged(self, text_processor):
        pages = [
            BookPage(page_type=PageType.COVER, content="T", page_number=1),
            BookPage(page_type=PageType.END, content="The End", page_number=2),
        ]
        result = text_processor._ensure_even_pages(pages)
        assert len(result) == 2

    def test_odd_count_adds_blank(self, text_processor):
        pages = [
            BookPage(page_type=PageType.COVER, content="T", page_number=1),
            BookPage(page_type=PageType.CONTENT, content="A", page_number=2),
            BookPage(page_type=PageType.END, content="The End", page_number=3),
        ]
        result = text_processor._ensure_even_pages(pages)
        assert len(result) == 4
        assert result[2].page_type == PageType.BLANK
        assert result[3].page_type == PageType.END


# =============================================================================
# TextProcessor.process
# =============================================================================


class TestProcess:
    def test_basic_processing(self, text_processor, sample_story_text):
        result = text_processor.process(sample_story_text)
        assert result.title == "The Friendly Fox"
        assert result.total_pages % 2 == 0
        assert result.pages[0].page_type == PageType.COVER
        assert result.pages[-1].page_type in (PageType.END, PageType.BLANK)

    def test_custom_title_override(self, text_processor, sample_story_text):
        result = text_processor.process(sample_story_text, custom_title="Override Title")
        assert result.title == "Override Title"

    def test_pages_are_numbered(self, text_processor, sample_story_text):
        result = text_processor.process(sample_story_text)
        for i, page in enumerate(result.pages):
            assert page.page_number == i + 1


# =============================================================================
# TextProcessor.process_raw_story
# =============================================================================


class TestProcessRawStory:
    def test_basic_raw_story(self, text_processor):
        story = "Line one.\nLine two.\nLine three."
        result = text_processor.process_raw_story(story, title="Raw Story")
        assert result.title == "Raw Story"
        assert result.pages[0].page_type == PageType.COVER
        assert result.total_pages % 2 == 0

    def test_single_long_paragraph(self):
        processor = TextProcessor(max_chars_per_page=30)
        story = "A short sentence. Another short sentence. And one more."
        result = processor.process_raw_story(story, title="Long Para")
        # Should split the single paragraph into multiple pages
        content_pages = [p for p in result.pages if p.page_type == PageType.CONTENT]
        assert len(content_pages) >= 2

    def test_title_deduplication(self, text_processor):
        story = "My Story\nSome content here."
        result = text_processor.process_raw_story(story, title="My Story")
        # Title should not appear as content
        content_pages = [p for p in result.pages if p.page_type == PageType.CONTENT]
        for page in content_pages:
            assert page.content != "My Story"


# =============================================================================
# TextProcessor.process_structured
# =============================================================================


class TestProcessStructured:
    def test_basic_structured(self, text_processor, sample_structured_story):
        result = text_processor.process_structured(sample_structured_story)
        assert result.title == "The Friendly Fox"
        assert result.total_pages % 2 == 0
        assert result.pages[0].page_type == PageType.COVER

    def test_custom_title_override(self, text_processor, sample_structured_story):
        result = text_processor.process_structured(
            sample_structured_story, custom_title="My Custom Title"
        )
        assert result.title == "My Custom Title"

    def test_empty_pages_skipped(self, text_processor):
        data = {
            "title": "Test",
            "pages": [
                {"text": "Real content."},
                {"text": ""},
                {"text": "   "},
                {"text": "More content."},
            ],
        }
        result = text_processor.process_structured(data)
        content_pages = [p for p in result.pages if p.page_type == PageType.CONTENT]
        assert len(content_pages) == 2

    def test_oversized_page_split(self):
        processor = TextProcessor(max_chars_per_page=30)
        data = {
            "title": "Test",
            "pages": [
                {"text": "This sentence is rather long. And another long sentence here."},
            ],
        }
        result = processor.process_structured(data)
        content_pages = [p for p in result.pages if p.page_type == PageType.CONTENT]
        assert len(content_pages) >= 2

    def test_missing_title_uses_default(self, text_processor):
        data = {"pages": [{"text": "Content."}]}
        result = text_processor.process_structured(data)
        assert result.title == "Untitled Story"


# =============================================================================
# validate_book_content
# =============================================================================


class TestValidateBookContent:
    def test_valid_content_no_warnings(self, sample_book_content):
        warnings = validate_book_content(sample_book_content)
        assert len(warnings) == 0

    def test_no_title_warning(self):
        content = BookContent(
            title="",
            pages=[
                BookPage(page_type=PageType.COVER, content="", page_number=1),
                BookPage(page_type=PageType.CONTENT, content="A", page_number=2),
                BookPage(page_type=PageType.END, content="The End", page_number=3),
                BookPage(page_type=PageType.BLANK, content="", page_number=4),
            ],
        )
        warnings = validate_book_content(content)
        assert any("no title" in w.lower() for w in warnings)

    def test_too_few_pages_warning(self):
        content = BookContent(
            title="T",
            pages=[
                BookPage(page_type=PageType.COVER, content="T", page_number=1),
                BookPage(page_type=PageType.END, content="End", page_number=2),
            ],
        )
        warnings = validate_book_content(content)
        assert any("minimum" in w.lower() for w in warnings)

    def test_odd_page_count_warning(self):
        content = BookContent(
            title="T",
            pages=[
                BookPage(page_type=PageType.COVER, content="T", page_number=1),
                BookPage(page_type=PageType.CONTENT, content="A", page_number=2),
                BookPage(page_type=PageType.CONTENT, content="B", page_number=3),
                BookPage(page_type=PageType.CONTENT, content="C", page_number=4),
                BookPage(page_type=PageType.END, content="End", page_number=5),
            ],
        )
        warnings = validate_book_content(content)
        assert any("not even" in w.lower() for w in warnings)

    def test_empty_content_pages_warning(self):
        content = BookContent(
            title="T",
            pages=[
                BookPage(page_type=PageType.COVER, content="T", page_number=1),
                BookPage(page_type=PageType.CONTENT, content="", page_number=2),
                BookPage(page_type=PageType.CONTENT, content="Good", page_number=3),
                BookPage(page_type=PageType.END, content="End", page_number=4),
            ],
        )
        warnings = validate_book_content(content)
        assert any("empty content" in w.lower() for w in warnings)
