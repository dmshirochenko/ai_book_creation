"""
Text Processor for Children's Book Generator.

This module handles text parsing, splitting, and validation
to prepare content for book pages.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum


class PageType(Enum):
    """Types of pages in the book."""
    COVER = "cover"
    CONTENT = "content"
    END = "end"
    BLANK = "blank"


@dataclass
class BookPage:
    """Represents a single page in the book."""
    page_type: PageType
    content: str
    page_number: int = 0
    
    def is_empty(self) -> bool:
        """Check if page has no content."""
        return not self.content.strip()


@dataclass
class BookContent:
    """Complete book content ready for PDF generation."""
    title: str
    pages: List[BookPage] = field(default_factory=list)
    author: str = "A Bedtime Story"
    language: str = "English"
    
    @property
    def total_pages(self) -> int:
        """Total number of pages including cover and end."""
        return len(self.pages)
    
    def is_valid_for_booklet(self) -> bool:
        """Check if page count is even (required for booklet printing)."""
        return self.total_pages % 2 == 0


class TextProcessor:
    """Process and prepare text for children's book pages."""
    
    def __init__(
        self,
        max_sentences_per_page: int = 2,
        max_chars_per_page: int = 100,
        end_page_text: str = "The End"
    ):
        self.max_sentences_per_page = max_sentences_per_page
        self.max_chars_per_page = max_chars_per_page
        self.end_page_text = end_page_text
    
    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences, handling various punctuation.
        """
        # Handle common sentence endings
        # This pattern keeps the punctuation with the sentence
        pattern = r'(?<=[.!?])\s+'
        sentences = re.split(pattern, text)
        
        # Clean up each sentence
        return [s.strip() for s in sentences if s.strip()]
    
    def _extract_title_and_content(self, adapted_text: str) -> tuple[str, str]:
        """
        Extract title from the first line and remaining content.
        """
        lines = adapted_text.strip().split('\n')
        
        if not lines:
            return "Untitled Story", ""
        
        # First non-empty line is the title
        title = ""
        content_start = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped:
                title = stripped
                content_start = i + 1
                break
        
        # Rest is content
        content_lines = [l.strip() for l in lines[content_start:] if l.strip()]
        content = '\n'.join(content_lines)
        
        return title, content
    
    def _split_text_to_pages(self, content: str) -> List[str]:
        """
        Split content into page-sized chunks.
        
        Priority:
        1. Respect line breaks (each line = one page)
        2. If a line is too long, split by sentences
        3. If a sentence is too long, it still gets its own page (no truncation)
        """
        lines = content.strip().split('\n')
        pages = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # If line fits, use it as-is
            if len(line) <= self.max_chars_per_page:
                pages.append(line)
            else:
                # Split by sentences if too long
                sentences = self._split_into_sentences(line)
                current_page = ""
                
                for sentence in sentences:
                    # If adding this sentence exceeds limit, start new page
                    potential = f"{current_page} {sentence}".strip() if current_page else sentence
                    
                    if len(potential) <= self.max_chars_per_page:
                        current_page = potential
                    else:
                        # Save current page if not empty
                        if current_page:
                            pages.append(current_page)
                        # This sentence gets its own page
                        current_page = sentence
                
                # Don't forget the last page
                if current_page:
                    pages.append(current_page)
        
        return pages
    
    def _ensure_even_pages(self, pages: List[BookPage]) -> List[BookPage]:
        """
        Ensure the book has an even number of pages for booklet printing.
        Adds blank pages if necessary.
        """
        if len(pages) % 2 == 0:
            return pages
        
        # Add a blank page before the end page
        end_page = pages[-1]
        pages = pages[:-1]
        
        blank = BookPage(
            page_type=PageType.BLANK,
            content="",
            page_number=len(pages) + 1
        )
        pages.append(blank)
        
        # Update end page number
        end_page.page_number = len(pages) + 1
        pages.append(end_page)
        
        return pages
    
    def process(
        self,
        adapted_text: str,
        author: str = "A Bedtime Story",
        language: str = "English",
        custom_title: Optional[str] = None
    ) -> BookContent:
        """
        Process adapted text into complete book content.
        
        Args:
            adapted_text: Text from LLM (first line = title, rest = content)
            author: Author name for cover
            language: Book language
            custom_title: Override extracted title
            
        Returns:
            BookContent ready for PDF generation
        """
        # Extract title and content
        extracted_title, content = self._extract_title_and_content(adapted_text)
        title = custom_title or extracted_title
        
        # Split content into page texts
        page_texts = self._split_text_to_pages(content)
        
        # Build page list
        pages: List[BookPage] = []
        
        # Cover page
        pages.append(BookPage(
            page_type=PageType.COVER,
            content=title,
            page_number=1
        ))
        
        # Content pages
        for i, text in enumerate(page_texts):
            pages.append(BookPage(
                page_type=PageType.CONTENT,
                content=text,
                page_number=i + 2  # +2 because cover is page 1
            ))
        
        # End page
        pages.append(BookPage(
            page_type=PageType.END,
            content=self.end_page_text,
            page_number=len(pages) + 1
        ))
        
        # Ensure even page count
        pages = self._ensure_even_pages(pages)
        
        # Renumber pages after adjustment
        for i, page in enumerate(pages):
            page.page_number = i + 1
        
        return BookContent(
            title=title,
            pages=pages,
            author=author,
            language=language
        )
    
    def process_raw_story(
        self,
        story: str,
        title: str = "My Story",
        author: str = "A Bedtime Story",
        language: str = "English"
    ) -> BookContent:
        """
        Process a raw story directly (without LLM adaptation).
        Useful for pre-adapted or manually written stories.

        Args:
            story: Story text (one sentence/paragraph per line, or a single paragraph)
            title: Book title
            author: Author name
            language: Book language

        Returns:
            BookContent ready for PDF generation
        """
        # Remove the title from story if it appears on the first line
        lines = story.strip().split('\n')
        if lines and lines[0].strip().lower() == title.lower():
            # First line is the title, skip it
            story = '\n'.join(lines[1:])

        # If story is a single paragraph (no line breaks), split into sentences
        # to create individual pages
        lines = story.strip().split('\n')
        if len(lines) == 1 and len(lines[0]) > self.max_chars_per_page:
            # Single long paragraph - split by sentences
            sentences = self._split_into_sentences(lines[0])
            # Join title with sentences separated by newlines
            story = f"{title}\n" + '\n'.join(sentences)
        else:
            # Multiple lines - prepend title
            story = f"{title}\n{story}"

        # Process the story content (first line will be extracted as title)
        return self.process(story, author, language, custom_title=title)


    def process_structured(
        self,
        story_data: dict,
        author: str = "A Bedtime Story",
        language: str = "English",
        custom_title: Optional[str] = None
    ) -> BookContent:
        """
        Process structured JSON story data into complete book content.

        Args:
            story_data: Dict with "title" (str) and "pages" (list of {"text": str})
            author: Author name for cover
            language: Book language
            custom_title: Override extracted title

        Returns:
            BookContent ready for PDF generation
        """
        title = custom_title or story_data.get("title", "Untitled Story")
        raw_pages = story_data.get("pages", [])

        pages: List[BookPage] = []

        # Cover page
        pages.append(BookPage(
            page_type=PageType.COVER,
            content=title,
            page_number=1
        ))

        # Content pages from structured data
        page_num = 2
        for page_data in raw_pages:
            text = page_data.get("text", "").strip()
            if not text:
                continue

            # Safety split for oversized pages
            if len(text) <= self.max_chars_per_page:
                pages.append(BookPage(
                    page_type=PageType.CONTENT,
                    content=text,
                    page_number=page_num
                ))
                page_num += 1
            else:
                # Split by sentences if too long
                sentences = self._split_into_sentences(text)
                current_page = ""

                for sentence in sentences:
                    potential = f"{current_page} {sentence}".strip() if current_page else sentence

                    if len(potential) <= self.max_chars_per_page:
                        current_page = potential
                    else:
                        if current_page:
                            pages.append(BookPage(
                                page_type=PageType.CONTENT,
                                content=current_page,
                                page_number=page_num
                            ))
                            page_num += 1
                        current_page = sentence

                if current_page:
                    pages.append(BookPage(
                        page_type=PageType.CONTENT,
                        content=current_page,
                        page_number=page_num
                    ))
                    page_num += 1

        # End page
        pages.append(BookPage(
            page_type=PageType.END,
            content=self.end_page_text,
            page_number=page_num
        ))

        # Ensure even page count
        pages = self._ensure_even_pages(pages)

        # Renumber pages after adjustment
        for i, page in enumerate(pages):
            page.page_number = i + 1

        return BookContent(
            title=title,
            pages=pages,
            author=author,
            language=language
        )


def validate_book_content(content: BookContent) -> List[str]:
    """
    Validate book content and return list of warnings.
    """
    warnings = []
    
    if not content.title:
        warnings.append("Book has no title")
    
    if content.total_pages < 4:
        warnings.append(f"Book has only {content.total_pages} pages (minimum recommended: 4)")
    
    if content.total_pages > 32:
        warnings.append(f"Book has {content.total_pages} pages (may be too long for young children)")
    
    if not content.is_valid_for_booklet():
        warnings.append("Page count is not even (required for booklet printing)")
    
    # Check for empty content pages
    empty_content_pages = [
        p for p in content.pages 
        if p.page_type == PageType.CONTENT and p.is_empty()
    ]
    if empty_content_pages:
        warnings.append(f"Found {len(empty_content_pages)} empty content pages")
    
    return warnings
