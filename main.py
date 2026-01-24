#!/usr/bin/env python3
"""
Children's Book Generator - Main Entry Point

This script generates print-ready PDF booklets from stories,
adapted for young children using LLM.

Usage:
    python main.py --story "Your story text here"
    python main.py --file story.txt
    python main.py --file story.txt --title "My Story" --language German
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime

from config import GeneratorConfig, BookConfig, LLMConfig
from llm_connector import adapt_story_for_children
from text_processor import TextProcessor, validate_book_content
from pdf_generator import generate_both_pdfs, get_print_instructions


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate printable children's book PDFs from stories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --story "Once upon a time, there was a little bunny..."
  %(prog)s --file my_story.txt --title "The Little Bunny"
  %(prog)s --file story.txt --age 3 5 --language German
  %(prog)s --file story.txt --no-adapt  # Skip LLM adaptation
        """
    )
    
    # Input options (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--story", "-s",
        type=str,
        help="Story text directly as a string"
    )
    input_group.add_argument(
        "--file", "-f",
        type=str,
        help="Path to text file containing the story"
    )
    
    # Book metadata
    parser.add_argument(
        "--title", "-t",
        type=str,
        help="Book title (overrides extracted title)"
    )
    parser.add_argument(
        "--author", "-a",
        type=str,
        default="A Bedtime Story",
        help="Author name (default: 'A Bedtime Story')"
    )
    
    # Target audience
    parser.add_argument(
        "--age",
        type=int,
        nargs=2,
        default=[2, 4],
        metavar=("MIN", "MAX"),
        help="Target age range (default: 2 4)"
    )
    
    # Language
    parser.add_argument(
        "--language", "-l",
        type=str,
        default="English",
        help="Target language (default: English)"
    )
    
    # Typography
    parser.add_argument(
        "--font-size",
        type=int,
        default=24,
        help="Content font size in points (default: 24)"
    )
    parser.add_argument(
        "--title-font-size",
        type=int,
        default=36,
        help="Title font size in points (default: 36)"
    )
    
    # Output
    parser.add_argument(
        "--output", "-o",
        type=str,
        help="Output PDF path (default: output/<title>_<timestamp>.pdf)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Output directory (default: output)"
    )
    
    # Processing options
    parser.add_argument(
        "--no-adapt",
        action="store_true",
        help="Skip LLM adaptation (use story as-is, assuming it's pre-formatted)"
    )
    parser.add_argument(
        "--end-text",
        type=str,
        default="The End",
        help="Text for the final page (default: 'The End')"
    )
    
    # Image generation options
    parser.add_argument(
        "--generate-images",
        action="store_true",
        help="Generate AI illustrations for each page (uses OpenRouter)"
    )
    parser.add_argument(
        "--image-model",
        type=str,
        default="google/gemini-3-pro-image-preview",
        help="OpenRouter image model (default: google/gemini-3-pro-image-preview)"
    )
    parser.add_argument(
        "--image-style",
        type=str,
        default="children's book illustration, soft watercolor style, gentle colors, simple shapes, cute and friendly",
        help="Style description for generated images"
    )
    parser.add_argument(
        "--no-image-cache",
        action="store_true",
        help="Disable image caching (regenerate all images)"
    )
    parser.add_argument(
        "--text-on-image",
        action="store_true",
        help="Ask LLM to render story text directly on the generated images"
    )
    
    # Debug
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "--print-instructions",
        action="store_true",
        help="Print printing instructions after generation"
    )
    
    return parser


def read_story_file(file_path: str) -> str:
    """Read story from file."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Story file not found: {file_path}")
    
    return path.read_text(encoding="utf-8")


def generate_output_filename(title: str, output_dir: str, suffix: str = "") -> str:
    """Generate output filename from title and timestamp."""
    # Clean title for filename
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in title)
    safe_title = safe_title.strip().replace(" ", "_")[:50]
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    if suffix:
        filename = f"{safe_title}_{timestamp}_{suffix}.pdf"
    else:
        filename = f"{safe_title}_{timestamp}.pdf"
    
    return str(Path(output_dir) / filename)


def main():
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Get story text
    if args.story:
        story_text = args.story
    else:
        try:
            story_text = read_story_file(args.file)
            if args.verbose:
                print(f"Read story from: {args.file}")
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    if args.verbose:
        print(f"Story length: {len(story_text)} characters")
    
    # Configure
    book_config = BookConfig(
        target_age_min=args.age[0],
        target_age_max=args.age[1],
        language=args.language,
        font_size=args.font_size,
        title_font_size=args.title_font_size,
        cover_title=args.title,
        author_name=args.author,
        end_page_text=args.end_text
    )
    
    llm_config = LLMConfig()
    
    # Adapt story (or use as-is)
    if args.no_adapt:
        if args.verbose:
            print("Skipping LLM adaptation (--no-adapt)")
        adapted_text = story_text
        
        # If no-adapt and no title provided, try to get from first line
        if not args.title:
            lines = story_text.strip().split('\n')
            if lines:
                args.title = lines[0].strip()
    else:
        if not llm_config.validate():
            print("Warning: OpenRouter API key not configured.", file=sys.stderr)
            print("Set OPENROUTER_API_KEY in .env file or use --no-adapt", file=sys.stderr)
            print("Falling back to using story as-is...", file=sys.stderr)
            adapted_text = story_text
        else:
            if args.verbose:
                print("Adapting story with LLM...")
            
            response = adapt_story_for_children(
                story=story_text,
                config=llm_config,
                target_age_min=args.age[0],
                target_age_max=args.age[1],
                language=args.language
            )
            
            if not response.success:
                print(f"Error adapting story: {response.error}", file=sys.stderr)
                print("Falling back to using story as-is...", file=sys.stderr)
                adapted_text = story_text
            else:
                adapted_text = response.content
                if args.verbose:
                    print(f"Adaptation complete. Tokens used: {response.tokens_used}")
    
    # Process text
    processor = TextProcessor(
        max_sentences_per_page=2,
        max_chars_per_page=100,
        end_page_text=args.end_text
    )
    
    if args.no_adapt and args.title:
        book_content = processor.process_raw_story(
            story=adapted_text,
            title=args.title,
            author=args.author,
            language=args.language
        )
    else:
        book_content = processor.process(
            adapted_text=adapted_text,
            author=args.author,
            language=args.language,
            custom_title=args.title
        )
    
    if args.verbose:
        print(f"Book: '{book_content.title}'")
        print(f"Total pages: {book_content.total_pages}")
    
    # Validate
    warnings = validate_book_content(book_content)
    if warnings:
        for warning in warnings:
            print(f"Warning: {warning}", file=sys.stderr)
    
    # Generate images if requested
    images = None
    if args.generate_images:
        from image_generator import ImageConfig, BookImageGenerator
        
        image_config = ImageConfig(
            model=args.image_model,
            image_style=args.image_style,
            use_cache=not args.no_image_cache,
            text_on_image=args.text_on_image
        )
        
        if not image_config.validate():
            print("Warning: OPENROUTER_API_KEY not configured.", file=sys.stderr)
            print("Set OPENROUTER_API_KEY in .env file", file=sys.stderr)
            print("Continuing without images...", file=sys.stderr)
        else:
            if args.verbose:
                print(f"Generating images with OpenRouter ({args.image_model})...")
            
            image_generator = BookImageGenerator(image_config, book_config)
            
            # Prepare page data for image generation
            page_data = [
                {
                    'page_number': p.page_number,
                    'content': p.content,
                    'page_type': p.page_type.value
                }
                for p in book_content.pages
            ]
            
            # Get story context (first few sentences for context)
            story_context = ' '.join([
                p.content for p in book_content.pages 
                if p.page_type.value == 'content'
            ][:3])
            
            def progress_callback(current, total, page_num):
                if args.verbose:
                    print(f"  Generating image {current}/{total} (page {page_num})...")
            
            image_results = image_generator.generate_all_images(
                pages=page_data,
                story_context=story_context,
                progress_callback=progress_callback if args.verbose else None
            )
            
            # Collect successful images
            images = {}
            success_count = 0
            for page_num, result in image_results.items():
                if result.success and result.image_data:
                    images[page_num] = result.image_data
                    success_count += 1
                    if args.verbose and result.cached:
                        print(f"    Page {page_num}: loaded from cache")
                elif not result.success and args.verbose:
                    print(f"    Page {page_num}: failed - {result.error}")
            
            if args.verbose:
                print(f"Generated {success_count}/{len(image_results)} images successfully")
    
    # Determine output paths
    if args.output:
        # If user specified output, create both with suffixes
        base_path = args.output.rsplit('.pdf', 1)[0]
        booklet_path = f"{base_path}_booklet.pdf"
        review_path = f"{base_path}_review.pdf"
    else:
        os.makedirs(args.output_dir, exist_ok=True)
        booklet_path = generate_output_filename(book_content.title, args.output_dir, "booklet")
        review_path = generate_output_filename(book_content.title, args.output_dir, "review")
    
    # Generate both PDFs
    if args.verbose:
        print(f"Generating PDFs...")
    
    try:
        booklet_result, review_result = generate_both_pdfs(
            content=book_content,
            booklet_path=booklet_path,
            review_path=review_path,
            config=book_config,
            images=images
        )
        print(f"✓ Booklet (for printing): {booklet_result}")
        print(f"✓ Review (sequential A5): {review_result}")
    except Exception as e:
        print(f"Error generating PDF: {e}", file=sys.stderr)
        return 1
    
    # Print instructions
    if args.print_instructions:
        print(get_print_instructions(args.language))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
