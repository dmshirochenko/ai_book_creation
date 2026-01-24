"""
PDF Generator for Children's Book Booklets.

This module creates print-ready PDF booklets designed for:
- A4 paper, landscape orientation
- Double-sided printing
- Fold in half to create A5 book
- Correct page ordering for booklet assembly
"""

import os
import io
from pathlib import Path
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import black, white
from reportlab.lib.utils import ImageReader

from src.core.text_processor import BookContent, BookPage, PageType
from src.core.config import BookConfig


# A4 dimensions
A4_WIDTH, A4_HEIGHT = A4  # Portrait: 595.27 x 841.89 points
LANDSCAPE_WIDTH, LANDSCAPE_HEIGHT = landscape(A4)  # 841.89 x 595.27 points

# Half of A4 landscape = A5 portrait (for each page of the spread)
HALF_WIDTH = LANDSCAPE_WIDTH / 2


@dataclass
class SpreadLayout:
    """Layout information for a two-page spread."""
    left_page: Optional[BookPage]
    right_page: Optional[BookPage]
    sheet_number: int  # Physical sheet number for printing
    front_side: bool  # True = front of sheet, False = back


class FontManager:
    """Manage font registration and Unicode support."""
    
    # Common system font paths for different OS
    FONT_SEARCH_PATHS = [
        # macOS
        "/System/Library/Fonts",
        "/Library/Fonts",
        "~/Library/Fonts",
        # Linux
        "/usr/share/fonts/truetype",
        "/usr/share/fonts/TTF",
        "/usr/local/share/fonts",
        "~/.fonts",
        # Windows
        "C:/Windows/Fonts",
        # Project local
        "./fonts",
    ]
    
    # Preferred fonts with good Unicode support
    UNICODE_FONTS = [
        ("DejaVuSans", "DejaVuSans.ttf"),
        ("DejaVuSans-Bold", "DejaVuSans-Bold.ttf"),
        ("NotoSans", "NotoSans-Regular.ttf"),
        ("NotoSans-Bold", "NotoSans-Bold.ttf"),
        ("FreeSans", "FreeSans.ttf"),
        ("Arial", "Arial.ttf"),
        ("ArialUnicode", "Arial Unicode.ttf"),
    ]
    
    def __init__(self):
        self.registered_fonts = {}
        self._register_system_fonts()
    
    def _register_system_fonts(self):
        """Find and register Unicode-compatible fonts."""
        for font_name, font_file in self.UNICODE_FONTS:
            font_path = self._find_font(font_file)
            if font_path:
                try:
                    pdfmetrics.registerFont(TTFont(font_name, font_path))
                    self.registered_fonts[font_name] = font_path
                except Exception:
                    pass  # Skip fonts that fail to register
    
    def _find_font(self, font_file: str) -> Optional[str]:
        """Search for a font file in common locations."""
        for search_path in self.FONT_SEARCH_PATHS:
            expanded_path = os.path.expanduser(search_path)
            if os.path.isdir(expanded_path):
                for root, _, files in os.walk(expanded_path):
                    if font_file in files:
                        return os.path.join(root, font_file)
        return None
    
    def get_available_font(self, preferred: str = "DejaVuSans") -> str:
        """
        Get an available font, falling back to Helvetica if needed.
        Helvetica is always available but may not support all Unicode.
        """
        if preferred in self.registered_fonts:
            return preferred
        
        # Try other registered fonts
        for font_name in self.registered_fonts:
            return font_name
        
        # Fall back to Helvetica (always available)
        return "Helvetica"


class BookletPageOrderer:
    """
    Calculate correct page ordering for booklet printing.
    
    For a booklet, pages are printed on sheets that are folded.
    Each sheet has a front and back, each containing two book pages.
    
    Example for 8-page booklet (2 sheets):
    Sheet 1 Front: Page 8 (left), Page 1 (right)
    Sheet 1 Back:  Page 2 (left), Page 7 (right)
    Sheet 2 Front: Page 6 (left), Page 3 (right)
    Sheet 2 Back:  Page 4 (left), Page 5 (right)
    """
    
    @staticmethod
    def calculate_spreads(total_pages: int) -> List[Tuple[int, int]]:
        """
        Calculate the page pairs for each spread in printing order.
        
        Returns list of tuples: (left_page_num, right_page_num)
        Page numbers are 1-indexed, 0 means blank.
        """
        # Ensure we have a multiple of 4 pages (each sheet = 4 pages)
        sheets_needed = (total_pages + 3) // 4
        total_slots = sheets_needed * 4
        
        spreads = []
        
        for sheet in range(sheets_needed):
            # Front of sheet
            # Left side: total_slots - (sheet * 2)
            # Right side: (sheet * 2) + 1
            left_front = total_slots - (sheet * 2)
            right_front = (sheet * 2) + 1
            spreads.append((left_front, right_front))
            
            # Back of sheet (printed upside down, so reversed)
            # Left side: (sheet * 2) + 2
            # Right side: total_slots - (sheet * 2) - 1
            left_back = (sheet * 2) + 2
            right_back = total_slots - (sheet * 2) - 1
            spreads.append((left_back, right_back))
        
        return spreads
    
    @staticmethod
    def get_page_or_blank(pages: List[BookPage], page_num: int) -> Optional[BookPage]:
        """Get page by number (1-indexed) or None for blank/out-of-range."""
        if 1 <= page_num <= len(pages):
            return pages[page_num - 1]
        return None


class PDFBookletGenerator:
    """Generate print-ready PDF booklets."""
    
    def __init__(self, config: BookConfig, images: Optional[Dict[int, bytes]] = None):
        self.config = config
        self.font_manager = FontManager()
        self.font = self.font_manager.get_available_font(config.font_family)
        self.images = images or {}  # page_number -> image_bytes
    
    def _get_image_reader(self, page_num: int) -> Optional[ImageReader]:
        """Get ImageReader for a page's image if available."""
        if page_num in self.images and self.images[page_num]:
            try:
                return ImageReader(io.BytesIO(self.images[page_num]))
            except Exception:
                return None
        return None
    
    def _draw_page_content(
        self,
        c: canvas.Canvas,
        page: Optional[BookPage],
        x_offset: float,
        y_offset: float,
        page_width: float,
        page_height: float
    ):
        """Draw content for a single page within a spread."""
        if page is None:
            return  # Leave blank
        
        # Check if we have an image for this page
        image_reader = self._get_image_reader(page.page_number)
        
        # Calculate text area
        text_x = x_offset + self.config.margin_left
        text_width = page_width - self.config.margin_left - self.config.margin_right
        text_center_x = x_offset + page_width / 2
        
        if image_reader:
            # Layout with image: image on top, text at bottom
            self._draw_page_with_image(
                c, page, image_reader,
                x_offset, y_offset, page_width, page_height,
                text_center_x, text_width
            )
        else:
            # Text-only layout (centered)
            text_y = y_offset + page_height / 2
            
            if page.page_type == PageType.COVER:
                self._draw_cover(c, page, text_center_x, text_y, text_width)
            elif page.page_type == PageType.END:
                self._draw_end_page(c, page, text_center_x, text_y)
            elif page.page_type == PageType.CONTENT:
                self._draw_content_page(c, page, text_center_x, text_y, text_width)
    
    def _draw_page_with_image(
        self,
        c: canvas.Canvas,
        page: BookPage,
        image_reader: ImageReader,
        x_offset: float,
        y_offset: float,
        page_width: float,
        page_height: float,
        text_center_x: float,
        text_width: float
    ):
        """Draw a page with image on top and text at bottom."""
        margin = self.config.margin_top
        
        # Calculate image area (top 60% of page)
        image_area_height = (page_height - 2 * margin) * 0.60
        text_area_height = (page_height - 2 * margin) * 0.35
        gap = (page_height - 2 * margin) * 0.05
        
        # Image dimensions (maintain aspect ratio)
        img_width, img_height = image_reader.getSize()
        aspect_ratio = img_width / img_height
        
        # Fit image within available space
        available_width = page_width - 2 * margin
        
        if aspect_ratio > (available_width / image_area_height):
            # Width-constrained
            draw_width = available_width
            draw_height = draw_width / aspect_ratio
        else:
            # Height-constrained
            draw_height = image_area_height
            draw_width = draw_height * aspect_ratio
        
        # Center image horizontally
        img_x = x_offset + (page_width - draw_width) / 2
        img_y = y_offset + margin + text_area_height + gap
        
        # Draw image
        c.drawImage(
            image_reader,
            img_x, img_y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            anchor='sw'
        )
        
        # Draw text below image
        text_y = y_offset + margin + text_area_height / 2
        
        if page.page_type == PageType.COVER:
            c.setFont(self.font, self.config.title_font_size)
            title_lines = self._wrap_text(
                page.content, self.font,
                self.config.title_font_size, text_width
            )
            line_height = self.config.title_font_size * 1.3
            total_height = len(title_lines) * line_height
            start_y = text_y + total_height / 2
            for i, line in enumerate(title_lines):
                c.drawCentredString(text_center_x, start_y - (i * line_height), line)
        
        elif page.page_type == PageType.END:
            c.setFont(self.font, self.config.title_font_size)
            c.drawCentredString(text_center_x, text_y, page.content)
        
        elif page.page_type == PageType.CONTENT:
            c.setFont(self.font, self.config.font_size)
            lines = self._wrap_text(
                page.content, self.font,
                self.config.font_size, text_width
            )
            line_height = self.config.font_size * 1.4
            total_height = len(lines) * line_height
            start_y = text_y + total_height / 2
            for i, line in enumerate(lines):
                c.drawCentredString(text_center_x, start_y - (i * line_height), line)
    
    def _draw_cover(
        self,
        c: canvas.Canvas,
        page: BookPage,
        center_x: float,
        center_y: float,
        max_width: float
    ):
        """Draw the cover page with title."""
        c.setFont(self.font, self.config.title_font_size)
        
        # Title (centered, possibly wrapped)
        title_lines = self._wrap_text(
            page.content,
            self.font,
            self.config.title_font_size,
            max_width
        )
        
        line_height = self.config.title_font_size * 1.3
        total_height = len(title_lines) * line_height
        start_y = center_y + total_height / 2
        
        for i, line in enumerate(title_lines):
            y = start_y - (i * line_height)
            c.drawCentredString(center_x, y, line)
    
    def _draw_end_page(
        self,
        c: canvas.Canvas,
        page: BookPage,
        center_x: float,
        center_y: float
    ):
        """Draw the end page."""
        c.setFont(self.font, self.config.title_font_size)
        c.drawCentredString(center_x, center_y, page.content)
    
    def _draw_content_page(
        self,
        c: canvas.Canvas,
        page: BookPage,
        center_x: float,
        center_y: float,
        max_width: float
    ):
        """Draw a content page with story text."""
        c.setFont(self.font, self.config.font_size)
        
        # Wrap text if needed
        lines = self._wrap_text(
            page.content,
            self.font,
            self.config.font_size,
            max_width
        )
        
        line_height = self.config.font_size * 1.4
        total_height = len(lines) * line_height
        start_y = center_y + total_height / 2
        
        for i, line in enumerate(lines):
            y = start_y - (i * line_height)
            c.drawCentredString(center_x, y, line)
    
    def _wrap_text(
        self,
        text: str,
        font_name: str,
        font_size: float,
        max_width: float
    ) -> List[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            width = pdfmetrics.stringWidth(test_line, font_name, font_size)
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines if lines else [text]
    
    def generate(
        self,
        content: BookContent,
        output_path: str
    ) -> str:
        """
        Generate the PDF booklet.
        
        Args:
            content: BookContent with all pages
            output_path: Path for output PDF
            
        Returns:
            Path to generated PDF
        """
        # Ensure output directory exists
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Calculate spreads
        orderer = BookletPageOrderer()
        spreads = orderer.calculate_spreads(content.total_pages)
        
        # Create PDF
        c = canvas.Canvas(
            output_path,
            pagesize=landscape(A4)
        )
        
        # Set metadata
        c.setTitle(content.title)
        c.setAuthor(content.author)
        
        # Draw each spread
        for left_num, right_num in spreads:
            left_page = orderer.get_page_or_blank(content.pages, left_num)
            right_page = orderer.get_page_or_blank(content.pages, right_num)
            
            # Draw left page (left half of A4 landscape)
            self._draw_page_content(
                c, left_page,
                x_offset=0,
                y_offset=0,
                page_width=HALF_WIDTH,
                page_height=LANDSCAPE_HEIGHT
            )
            
            # Draw right page (right half of A4 landscape)
            self._draw_page_content(
                c, right_page,
                x_offset=HALF_WIDTH,
                y_offset=0,
                page_width=HALF_WIDTH,
                page_height=LANDSCAPE_HEIGHT
            )
            
            c.showPage()
        
        c.save()
        return output_path


def generate_booklet_pdf(
    content: BookContent,
    output_path: str,
    config: Optional[BookConfig] = None,
    images: Optional[Dict[int, bytes]] = None
) -> str:
    """
    Convenience function to generate a PDF booklet.
    
    Args:
        content: BookContent with pages
        output_path: Output file path
        config: Book configuration (uses defaults if not provided)
        images: Optional dict mapping page_number to image bytes
        
    Returns:
        Path to generated PDF
    """
    if config is None:
        config = BookConfig()
    
    generator = PDFBookletGenerator(config, images)
    return generator.generate(content, output_path)


class PDFSequentialGenerator:
    """Generate normal sequential PDF for review (A5 portrait, one page per sheet)."""
    
    # A5 dimensions in points (portrait)
    A5_WIDTH = A4_HEIGHT / 2  # 420.94 points
    A5_HEIGHT = A4_WIDTH      # 595.27 points
    
    def __init__(self, config: BookConfig, images: Optional[Dict[int, bytes]] = None):
        self.config = config
        self.font_manager = FontManager()
        self.font = self.font_manager.get_available_font(config.font_family)
        self.images = images or {}
    
    def _get_image_reader(self, page_num: int) -> Optional[ImageReader]:
        """Get ImageReader for a page's image if available."""
        if page_num in self.images and self.images[page_num]:
            try:
                return ImageReader(io.BytesIO(self.images[page_num]))
            except Exception:
                return None
        return None
    
    def _draw_page_content(
        self,
        c: canvas.Canvas,
        page: Optional[BookPage],
        page_width: float,
        page_height: float
    ):
        """Draw content for a single A5 page."""
        if page is None:
            return
        
        # Check if we have an image for this page
        image_reader = self._get_image_reader(page.page_number)
        
        # Calculate text area
        text_center_x = page_width / 2
        text_width = page_width - self.config.margin_left - self.config.margin_right
        
        if image_reader:
            # Layout with image
            self._draw_page_with_image(
                c, page, image_reader,
                page_width, page_height,
                text_center_x, text_width
            )
        else:
            # Text-only layout
            text_y = page_height / 2
            
            if page.page_type == PageType.COVER:
                self._draw_cover(c, page, text_center_x, text_y, text_width)
            elif page.page_type == PageType.END:
                self._draw_end_page(c, page, text_center_x, text_y)
            elif page.page_type == PageType.CONTENT:
                self._draw_content_page(c, page, text_center_x, text_y, text_width)
    
    def _draw_page_with_image(
        self,
        c: canvas.Canvas,
        page: BookPage,
        image_reader: ImageReader,
        page_width: float,
        page_height: float,
        text_center_x: float,
        text_width: float
    ):
        """Draw a page with image on top and text at bottom."""
        margin = self.config.margin_top
        
        # Calculate image area (top 60% of page)
        image_area_height = (page_height - 2 * margin) * 0.60
        text_area_height = (page_height - 2 * margin) * 0.35
        gap = (page_height - 2 * margin) * 0.05
        
        # Image dimensions (maintain aspect ratio)
        img_width, img_height = image_reader.getSize()
        aspect_ratio = img_width / img_height
        
        # Fit image within available space
        available_width = page_width - 2 * margin
        
        if aspect_ratio > (available_width / image_area_height):
            draw_width = available_width
            draw_height = draw_width / aspect_ratio
        else:
            draw_height = image_area_height
            draw_width = draw_height * aspect_ratio
        
        # Center image horizontally
        img_x = (page_width - draw_width) / 2
        img_y = margin + text_area_height + gap
        
        # Draw image
        c.drawImage(
            image_reader,
            img_x, img_y,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            anchor='sw'
        )
        
        # Draw text below image
        text_y = margin + text_area_height / 2
        
        if page.page_type == PageType.COVER:
            c.setFont(self.font, self.config.title_font_size)
            title_lines = self._wrap_text(
                page.content, self.font,
                self.config.title_font_size, text_width
            )
            line_height = self.config.title_font_size * 1.3
            total_height = len(title_lines) * line_height
            start_y = text_y + total_height / 2
            for i, line in enumerate(title_lines):
                c.drawCentredString(text_center_x, start_y - (i * line_height), line)
        
        elif page.page_type == PageType.END:
            c.setFont(self.font, self.config.title_font_size)
            c.drawCentredString(text_center_x, text_y, page.content)
        
        elif page.page_type == PageType.CONTENT:
            c.setFont(self.font, self.config.font_size)
            lines = self._wrap_text(
                page.content, self.font,
                self.config.font_size, text_width
            )
            line_height = self.config.font_size * 1.4
            total_height = len(lines) * line_height
            start_y = text_y + total_height / 2
            for i, line in enumerate(lines):
                c.drawCentredString(text_center_x, start_y - (i * line_height), line)
    
    def _draw_cover(
        self,
        c: canvas.Canvas,
        page: BookPage,
        center_x: float,
        center_y: float,
        max_width: float
    ):
        """Draw the cover page with title."""
        c.setFont(self.font, self.config.title_font_size)
        
        title_lines = self._wrap_text(
            page.content,
            self.font,
            self.config.title_font_size,
            max_width
        )
        
        line_height = self.config.title_font_size * 1.3
        total_height = len(title_lines) * line_height
        start_y = center_y + total_height / 2
        
        for i, line in enumerate(title_lines):
            y = start_y - (i * line_height)
            c.drawCentredString(center_x, y, line)
    
    def _draw_end_page(
        self,
        c: canvas.Canvas,
        page: BookPage,
        center_x: float,
        center_y: float
    ):
        """Draw the end page."""
        c.setFont(self.font, self.config.title_font_size)
        c.drawCentredString(center_x, center_y, page.content)
    
    def _draw_content_page(
        self,
        c: canvas.Canvas,
        page: BookPage,
        center_x: float,
        center_y: float,
        max_width: float
    ):
        """Draw a content page with story text."""
        c.setFont(self.font, self.config.font_size)
        
        lines = self._wrap_text(
            page.content,
            self.font,
            self.config.font_size,
            max_width
        )
        
        line_height = self.config.font_size * 1.4
        total_height = len(lines) * line_height
        start_y = center_y + total_height / 2
        
        for i, line in enumerate(lines):
            y = start_y - (i * line_height)
            c.drawCentredString(center_x, y, line)
    
    def _wrap_text(
        self,
        text: str,
        font_name: str,
        font_size: float,
        max_width: float
    ) -> List[str]:
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            width = pdfmetrics.stringWidth(test_line, font_name, font_size)
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines if lines else [text]
    
    def generate(
        self,
        content: BookContent,
        output_path: str
    ) -> str:
        """
        Generate the sequential PDF for review.
        
        Args:
            content: BookContent with all pages
            output_path: Path for output PDF
            
        Returns:
            Path to generated PDF
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Create PDF with A5 portrait size
        c = canvas.Canvas(
            output_path,
            pagesize=(self.A5_WIDTH, self.A5_HEIGHT)
        )
        
        c.setTitle(content.title)
        c.setAuthor(content.author)
        
        # Draw each page in sequential order
        for page in content.pages:
            if page.page_type != PageType.BLANK:
                self._draw_page_content(
                    c, page,
                    page_width=self.A5_WIDTH,
                    page_height=self.A5_HEIGHT
                )
                c.showPage()
        
        c.save()
        return output_path


def generate_sequential_pdf(
    content: BookContent,
    output_path: str,
    config: Optional[BookConfig] = None,
    images: Optional[Dict[int, bytes]] = None
) -> str:
    """
    Generate a normal sequential PDF for review (A5 portrait).
    
    Args:
        content: BookContent with pages
        output_path: Output file path
        config: Book configuration (uses defaults if not provided)
        images: Optional dict mapping page_number to image bytes
        
    Returns:
        Path to generated PDF
    """
    if config is None:
        config = BookConfig()
    
    generator = PDFSequentialGenerator(config, images)
    return generator.generate(content, output_path)


def generate_both_pdfs(
    content: BookContent,
    booklet_path: str,
    review_path: str,
    config: Optional[BookConfig] = None,
    images: Optional[Dict[int, bytes]] = None
) -> Tuple[str, str]:
    """
    Generate both booklet and sequential PDFs.
    
    Args:
        content: BookContent with pages
        booklet_path: Output path for booklet PDF
        review_path: Output path for review PDF
        config: Book configuration
        images: Optional dict mapping page_number to image bytes
        
    Returns:
        Tuple of (booklet_path, review_path)
    """
    if config is None:
        config = BookConfig()
    
    booklet = generate_booklet_pdf(content, booklet_path, config, images)
    review = generate_sequential_pdf(content, review_path, config, images)
    
    return booklet, review


def get_print_instructions(language: str = "English") -> str:
    """Get printing instructions for the booklet."""
    instructions = {
        "English": """
PRINTING INSTRUCTIONS
=====================

1. Print the PDF using these settings:
   - Paper size: A4
   - Orientation: Landscape (should be automatic)
   - Print: Double-sided / Duplex

2. Duplex settings:
   - Flip on SHORT EDGE

3. After printing:
   - Take all sheets together
   - Fold in half
   - The book is ready!

Note: If your printer doesn't support duplex, print odd pages first,
then reinsert the paper and print even pages on the back.
""",
        "German": """
DRUCKANLEITUNG
==============

1. PDF mit diesen Einstellungen drucken:
   - Papierformat: A4
   - Ausrichtung: Querformat (sollte automatisch sein)
   - Druck: Beidseitig / Duplex

2. Duplex-Einstellungen:
   - An kurzer Kante spiegeln

3. Nach dem Drucken:
   - Alle Blätter zusammennehmen
   - In der Mitte falten
   - Das Buch ist fertig!
""",
        "Spanish": """
INSTRUCCIONES DE IMPRESIÓN
==========================

1. Imprima el PDF con estos ajustes:
   - Tamaño de papel: A4
   - Orientación: Horizontal (debería ser automático)
   - Impresión: A doble cara / Dúplex

2. Configuración de dúplex:
   - Voltear en el BORDE CORTO

3. Después de imprimir:
   - Tome todas las hojas juntas
   - Dóblelas por la mitad
   - ¡El libro está listo!
"""
    }
    
    return instructions.get(language, instructions["English"])
