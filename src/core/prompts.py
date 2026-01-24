"""
Prompts for LLM and Image Generation.

This module centralizes all prompts sent to OpenRouter/LLMs
for story adaptation and image generation.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import json
import re


# =============================================================================
# DATA MODELS FOR STORY CONTEXT
# =============================================================================

@dataclass
class Character:
    """A character extracted from the story."""
    name: str
    description: str  # Visual description for consistent illustration
    
    def to_prompt_string(self) -> str:
        """Format character for image prompt."""
        return f"- {self.name}: {self.description}"


@dataclass
class StoryVisualContext:
    """Visual context extracted from story analysis for consistent illustrations."""
    characters: List[Character] = field(default_factory=list)
    setting: str = ""  # Main location/environment
    atmosphere: str = ""  # Time of day, mood, weather
    color_palette: str = ""  # Suggested colors for consistency
    
    def to_prompt_section(self) -> str:
        """Format the visual context as a section for image prompts."""
        sections = []
        
        if self.characters:
            char_lines = "\n".join(c.to_prompt_string() for c in self.characters)
            sections.append(f"CHARACTERS (draw consistently throughout the book):\n{char_lines}")
        
        if self.setting:
            sections.append(f"SETTING: {self.setting}")
        
        if self.atmosphere:
            sections.append(f"ATMOSPHERE: {self.atmosphere}")
        
        if self.color_palette:
            sections.append(f"COLOR PALETTE: {self.color_palette}")
        
        return "\n\n".join(sections) if sections else ""
    
    def is_empty(self) -> bool:
        """Check if context has any meaningful data."""
        return not (self.characters or self.setting or self.atmosphere or self.color_palette)


# =============================================================================
# STORY ANALYSIS PROMPT
# =============================================================================

STORY_ANALYSIS_PROMPT_TEMPLATE = """You are a children's book illustrator assistant. Analyze the following story and extract visual details that will help create consistent illustrations across all pages.

STORY TO ANALYZE:
{story}

Extract characters, setting, atmosphere, and color palette from this story."""


# JSON Schema for Structured Outputs (OpenRouter)
STORY_ANALYSIS_JSON_SCHEMA = {
    "name": "story_visual_context",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "characters": {
                "type": "array",
                "description": "List of characters in the story with visual descriptions",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Character name"
                        },
                        "description": {
                            "type": "string",
                            "description": "Detailed visual description: species/type, size, colors, distinctive features, typical clothing or accessories"
                        }
                    },
                    "required": ["name", "description"],
                    "additionalProperties": False
                }
            },
            "setting": {
                "type": "string",
                "description": "Main location or environment where the story takes place (be specific about visual elements)"
            },
            "atmosphere": {
                "type": "string",
                "description": "Time of day, season, weather, overall mood (e.g., 'warm sunny afternoon, peaceful and calm')"
            },
            "color_palette": {
                "type": "string",
                "description": "Suggested color scheme that fits the story mood (e.g., 'soft pastels, warm yellows and oranges, gentle greens')"
            }
        },
        "required": ["characters", "setting", "atmosphere", "color_palette"],
        "additionalProperties": False
    }
}


def build_story_analysis_prompt(story: str) -> str:
    """
    Build the prompt for story visual analysis.
    
    Args:
        story: The story text to analyze
        
    Returns:
        Formatted prompt string
    """
    return STORY_ANALYSIS_PROMPT_TEMPLATE.format(story=story)


def get_story_analysis_response_format() -> dict:
    """
    Get the response_format parameter for structured outputs.
    
    Returns:
        Dict with type and json_schema for OpenRouter API
    """
    return {
        "type": "json_schema",
        "json_schema": STORY_ANALYSIS_JSON_SCHEMA
    }


def parse_story_analysis_response(response_text: str) -> StoryVisualContext:
    """
    Parse the LLM response into a StoryVisualContext object.
    
    Args:
        response_text: Raw text response from LLM (should be valid JSON with structured outputs)
        
    Returns:
        StoryVisualContext with extracted data
    """
    try:
        # With structured outputs, response should be valid JSON directly
        # But we still handle potential markdown wrapping as fallback
        text = response_text.strip()
        
        # Try direct JSON parse first (structured outputs)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: extract JSON from potential markdown wrapping
            json_match = re.search(r'\{[\s\S]*\}', text)
            if not json_match:
                return StoryVisualContext()
            data = json.loads(json_match.group())
        
        characters = []
        for char_data in data.get("characters", []):
            if isinstance(char_data, dict) and "name" in char_data and "description" in char_data:
                characters.append(Character(
                    name=char_data["name"],
                    description=char_data["description"]
                ))
        
        return StoryVisualContext(
            characters=characters,
            setting=data.get("setting", ""),
            atmosphere=data.get("atmosphere", ""),
            color_palette=data.get("color_palette", "")
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return StoryVisualContext()


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

# Cover page prompts (with visual context)
IMAGE_COVER_WITH_TEXT_TEMPLATE = """Create a book cover illustration for a children's book.
Style: {base_style}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_summary}
{visual_context}
IMPORTANT: Include the title "{book_title}" prominently displayed on the cover in a fun, child-friendly font."""

IMAGE_COVER_NO_TEXT_TEMPLATE = """Create a book cover illustration for a children's book titled "{book_title}".
Style: {base_style}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_summary}
{visual_context}
No text in the image."""

# End page prompt (with visual context)
IMAGE_END_PAGE_TEMPLATE = """Create a peaceful, concluding illustration for a children's book.
Style: {base_style}
The scene should feel calm, complete, and satisfying - like a happy ending.
Context from the story: {story_context}
{visual_context}{text_instruction}"""

# Content page prompt (with visual context)
IMAGE_CONTENT_PAGE_TEMPLATE = """Create an illustration for page {page_number} of a children's book.
Style: {base_style}
Scene to illustrate: {page_text}
Overall story context: {story_context}
{visual_context}
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
    text_on_image: bool = False,
    visual_context: Optional[StoryVisualContext] = None
) -> str:
    """
    Build prompt for cover page illustration.
    
    Args:
        style: Base image style description
        book_title: Title of the book
        story_summary: Brief summary or first page text
        target_age: Tuple of (min_age, max_age)
        text_on_image: Whether to include title text on the image
        visual_context: Optional visual context for consistent illustrations
        
    Returns:
        Formatted prompt string
    """
    base_style = build_image_style(style, target_age[0], target_age[1])
    visual_section = visual_context.to_prompt_section() if visual_context and not visual_context.is_empty() else ""
    
    if text_on_image:
        return IMAGE_COVER_WITH_TEXT_TEMPLATE.format(
            base_style=base_style,
            story_summary=story_summary,
            book_title=book_title,
            visual_context=visual_section
        )
    else:
        return IMAGE_COVER_NO_TEXT_TEMPLATE.format(
            base_style=base_style,
            story_summary=story_summary,
            book_title=book_title,
            visual_context=visual_section
        )


def build_end_page_image_prompt(
    style: str,
    story_context: str,
    target_age: tuple[int, int],
    text_on_image: bool = False,
    page_text: str = "",
    visual_context: Optional[StoryVisualContext] = None
) -> str:
    """
    Build prompt for end page illustration.
    
    Args:
        style: Base image style description
        story_context: Context from the story
        target_age: Tuple of (min_age, max_age)
        text_on_image: Whether to include text on the image
        page_text: Text to overlay if text_on_image is True
        visual_context: Optional visual context for consistent illustrations
        
    Returns:
        Formatted prompt string
    """
    base_style = build_image_style(style, target_age[0], target_age[1])
    text_instruction = build_text_instruction(text_on_image, page_text)
    visual_section = visual_context.to_prompt_section() if visual_context and not visual_context.is_empty() else ""
    
    return IMAGE_END_PAGE_TEMPLATE.format(
        base_style=base_style,
        story_context=story_context,
        text_instruction=text_instruction,
        visual_context=visual_section
    )


def build_content_page_image_prompt(
    style: str,
    page_text: str,
    page_number: int,
    story_context: str,
    target_age: tuple[int, int],
    text_on_image: bool = False,
    visual_context: Optional[StoryVisualContext] = None
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
        visual_context: Optional visual context for consistent illustrations
        
    Returns:
        Formatted prompt string
    """
    base_style = build_image_style(style, target_age[0], target_age[1])
    text_instruction = build_text_instruction(text_on_image, page_text)
    visual_section = visual_context.to_prompt_section() if visual_context and not visual_context.is_empty() else ""
    
    return IMAGE_CONTENT_PAGE_TEMPLATE.format(
        base_style=base_style,
        page_text=page_text,
        page_number=page_number,
        story_context=story_context,
        text_instruction=text_instruction,
        visual_context=visual_section
    )
