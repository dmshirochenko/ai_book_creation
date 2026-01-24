"""
Prompts for LLM and Image Generation.

This module centralizes all prompts sent to OpenRouter/LLMs
for story adaptation and image generation.
"""

# =============================================================================
# STORY ADAPTATION PROMPTS
# =============================================================================

STORY_ADAPTATION_PROMPT_TEMPLATE = """You are a children's book editor specializing in books for ages {target_age_min}-{target_age_max}.

Your task is to adapt the following story for young children. Follow these rules strictly:

CONTENT RULES:
1. Use simple, short sentences (5-10 words each)
2. Use a calm, gentle, reassuring tone
3. Avoid complex vocabulary - use words a {target_age_min}-year-old would understand
4. Remove any scary, violent, or intense content
5. Keep the core story but simplify it dramatically
6. Each sentence should be standalone and easy to read aloud

STRUCTURE RULES:
1. Start with a title line (just the title, no formatting)
2. Then provide the story as separate sentences, one per line
3. Each line should be 1-2 simple sentences maximum
4. Aim for 8-16 lines total (this will be an 8-16 page book)
5. End with a satisfying, calm conclusion

LANGUAGE:
- Write in {language}
- Use the simplest words in that language

ORIGINAL STORY:
{story}

ADAPTED STORY (title on first line, then one sentence per line):"""


def build_story_adaptation_prompt(
    story: str,
    target_age_min: int,
    target_age_max: int,
    language: str
) -> str:
    """
    Build the prompt for story adaptation.
    
    Args:
        story: The original story text to adapt
        target_age_min: Minimum target age
        target_age_max: Maximum target age
        language: Target language for the book
        
    Returns:
        Formatted prompt string
    """
    return STORY_ADAPTATION_PROMPT_TEMPLATE.format(
        target_age_min=target_age_min,
        target_age_max=target_age_max,
        language=language,
        story=story
    )


# =============================================================================
# IMAGE GENERATION PROMPTS
# =============================================================================

# Base style suffix added to all image prompts
IMAGE_STYLE_SUFFIX = "safe for children ages {target_age_min}-{target_age_max}"

# Cover page prompts
IMAGE_COVER_WITH_TEXT_TEMPLATE = """Create a book cover illustration for a children's book.
Style: {base_style}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_summary}

IMPORTANT: Include the title "{book_title}" prominently displayed on the cover in a fun, child-friendly font."""

IMAGE_COVER_NO_TEXT_TEMPLATE = """Create a book cover illustration for a children's book titled "{book_title}".
Style: {base_style}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_summary}
No text in the image."""

# End page prompt
IMAGE_END_PAGE_TEMPLATE = """Create a peaceful, concluding illustration for a children's book.
Style: {base_style}
The scene should feel calm, complete, and satisfying - like a happy ending.
Context from the story: {story_context}{text_instruction}"""

# Content page prompt
IMAGE_CONTENT_PAGE_TEMPLATE = """Create an illustration for page {page_number} of a children's book.
Style: {base_style}
Scene to illustrate: {page_text}
Overall story context: {story_context}
The illustration should be simple, clear, and directly related to the text.{text_instruction}"""

# Text overlay instructions
TEXT_OVERLAY_INSTRUCTION_TEMPLATE = """
IMPORTANT: Include the following text overlaid on the image in a clear, readable font suitable for children:
"{page_text}"
Place the text at the bottom of the image with a semi-transparent background for readability."""

NO_TEXT_INSTRUCTION = "\nNo text or words in the image."


def build_image_style(style: str, target_age_min: int, target_age_max: int) -> str:
    """
    Build the complete style string for image prompts.
    
    Args:
        style: Base image style description
        target_age_min: Minimum target age
        target_age_max: Maximum target age
        
    Returns:
        Complete style string
    """
    age_suffix = IMAGE_STYLE_SUFFIX.format(
        target_age_min=target_age_min,
        target_age_max=target_age_max
    )
    return f"{style}, {age_suffix}"


def build_text_instruction(text_on_image: bool, page_text: str = "") -> str:
    """
    Build text overlay instruction for image prompts.
    
    Args:
        text_on_image: Whether to include text on the image
        page_text: The text to overlay (if text_on_image is True)
        
    Returns:
        Text instruction string
    """
    if text_on_image and page_text:
        return TEXT_OVERLAY_INSTRUCTION_TEMPLATE.format(page_text=page_text)
    return NO_TEXT_INSTRUCTION


def build_cover_image_prompt(
    style: str,
    book_title: str,
    story_summary: str,
    target_age: tuple[int, int],
    text_on_image: bool = False
) -> str:
    """
    Build prompt for cover page illustration.
    
    Args:
        style: Base image style description
        book_title: Title of the book
        story_summary: Brief summary or first page text
        target_age: Tuple of (min_age, max_age)
        text_on_image: Whether to include title text on the image
        
    Returns:
        Formatted prompt string
    """
    base_style = build_image_style(style, target_age[0], target_age[1])
    
    if text_on_image:
        return IMAGE_COVER_WITH_TEXT_TEMPLATE.format(
            base_style=base_style,
            story_summary=story_summary,
            book_title=book_title
        )
    else:
        return IMAGE_COVER_NO_TEXT_TEMPLATE.format(
            base_style=base_style,
            story_summary=story_summary,
            book_title=book_title
        )


def build_end_page_image_prompt(
    style: str,
    story_context: str,
    target_age: tuple[int, int],
    text_on_image: bool = False,
    page_text: str = ""
) -> str:
    """
    Build prompt for end page illustration.
    
    Args:
        style: Base image style description
        story_context: Context from the story
        target_age: Tuple of (min_age, max_age)
        text_on_image: Whether to include text on the image
        page_text: Text to overlay if text_on_image is True
        
    Returns:
        Formatted prompt string
    """
    base_style = build_image_style(style, target_age[0], target_age[1])
    text_instruction = build_text_instruction(text_on_image, page_text)
    
    return IMAGE_END_PAGE_TEMPLATE.format(
        base_style=base_style,
        story_context=story_context,
        text_instruction=text_instruction
    )


def build_content_page_image_prompt(
    style: str,
    page_text: str,
    page_number: int,
    story_context: str,
    target_age: tuple[int, int],
    text_on_image: bool = False
) -> str:
    """
    Build prompt for content page illustration.
    
    Args:
        style: Base image style description
        page_text: Text content of this page
        page_number: Current page number
        story_context: Overall story context or book title
        target_age: Tuple of (min_age, max_age)
        text_on_image: Whether to include text on the image
        
    Returns:
        Formatted prompt string
    """
    base_style = build_image_style(style, target_age[0], target_age[1])
    text_instruction = build_text_instruction(text_on_image, page_text)
    
    return IMAGE_CONTENT_PAGE_TEMPLATE.format(
        base_style=base_style,
        page_text=page_text,
        page_number=page_number,
        story_context=story_context,
        text_instruction=text_instruction
    )
