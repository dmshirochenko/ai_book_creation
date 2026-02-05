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
    background_color: str = ""  # Suggested PDF background color (hex)

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

STORY_ANALYSIS_PROMPT_TEMPLATE = """You are an expert children's book art director responsible for ensuring visual consistency across all illustrations in a picture book. Your task is to analyze a story and extract comprehensive visual details that illustrators will use to maintain character and scene consistency throughout the book.

---

## YOUR TASK

Analyze the story below and extract detailed visual specifications for:
1. **Characters** - Every character that appears, with precise visual descriptions
2. **Setting** - The world, locations, and environments
3. **Atmosphere** - Mood, time, weather, and emotional tone
4. **Color Palette** - Colors that unify the book's visual identity
5. **Background Color** - A soft, child-friendly background color for the book pages

---

## EXTRACTION GUIDELINES

### CHARACTERS
For EACH character (main and supporting), provide:
- **Physical appearance**: Species/type, body shape, size (relative to others), proportions
- **Distinctive features**: Unique markings, colors, patterns, textures (fur/scales/skin tone)
- **Facial characteristics**: Eye color/shape, expression tendencies, any distinctive facial features
- **Clothing/accessories**: What they wear, items they carry, recurring objects
- **Movement style**: How they move (bouncy, graceful, clumsy, etc.)
- **Age indicators**: Visual cues that suggest their age

Example format: "Luna the rabbit: Small white rabbit with oversized floppy ears that drag on the ground. Soft fluffy fur with a pink nose and large round blue eyes that sparkle with curiosity. Wears a tiny red scarf with yellow stars. Moves with excited little hops."

### SETTING
Describe the visual environment:
- **Primary location(s)**: Where does most of the story happen?
- **Architectural style**: Buildings, structures, natural formations
- **Flora and fauna**: Plants, trees, background animals
- **Scale and perspective**: How big is the world relative to characters?
- **Recurring visual elements**: Objects or landmarks that appear multiple times

### ATMOSPHERE
Capture the story's mood through:
- **Time of day**: Morning light, golden hour, night sky, etc.
- **Season**: Spring blossoms, autumn leaves, winter snow, summer warmth
- **Weather**: Sunny, cloudy, rainy, misty, starlit
- **Emotional tone**: Cozy, adventurous, mysterious, joyful, peaceful
- **Lighting quality**: Soft and diffused, bright and cheerful, warm and glowing

### COLOR PALETTE
Suggest 4-6 dominant colors that:
- Match the story's emotional tone
- Provide visual harmony across all pages
- Consider the target audience (young children respond to warm, saturated colors)
- Include both primary scene colors and accent colors

### BACKGROUND COLOR
Suggest a single soft background color for the PDF pages:
- Must be a valid hex color code (e.g., "#FFF8E7")
- Should be very light/pale to ensure text readability
- Should complement the story's mood (warm cream for cozy stories, light blue for calm/water themes, pale yellow for cheerful stories, etc.)
- Avoid pure white (#FFFFFF) - pick something with subtle warmth or character

---

## STORY TO ANALYZE

{story}

---

## OUTPUT REQUIREMENTS

Provide thorough, illustration-ready descriptions. Be specific enough that different illustrators would draw the same characters. Avoid vague terms like "cute" or "nice" - instead describe exactly what makes something appear that way visually."""


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
            },
            "background_color": {
                "type": "string",
                "description": "A soft, light hex color for PDF page background that complements the story mood (e.g., '#FFF8E7' for warm cream, '#F0F8FF' for calm blue, '#FFFACD' for cheerful yellow)"
            }
        },
        "required": ["characters", "setting", "atmosphere", "color_palette", "background_color"],
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
            color_palette=data.get("color_palette", ""),
            background_color=data.get("background_color", "")
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

# Portrait format close to A5 with soft edges for seamless page blending
IMAGE_SIZE_INSTRUCTION = """IMAGE FORMAT: Portrait orientation (taller than wide), 3:4 aspect ratio.
Generate at 1800x2400 pixels for print quality. The image MUST be vertical/portrait, not square or landscape.
EDGES: The illustration should have soft, gently fading edges that gradually blend into white around the borders, creating a vignette-like effect. Avoid hard or sharp edges at the image boundary."""

# Base style suffix added to all image prompts
IMAGE_STYLE_SUFFIX = "safe for children ages {target_age_min}-{target_age_max}"

# Cover page prompts (with visual context)
IMAGE_COVER_WITH_TEXT_TEMPLATE = """Create a book cover illustration for a children's book.
Style: {base_style}
{size_instruction}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_summary}
{visual_context}
IMPORTANT: Include the title "{book_title}" prominently displayed on the cover in a fun, child-friendly font."""

IMAGE_COVER_NO_TEXT_TEMPLATE = """Create a book cover illustration for a children's book titled "{book_title}".
Style: {base_style}
{size_instruction}
The image should be inviting, magical, and set the tone for the story.
Story summary: {story_summary}
{visual_context}
No text in the image."""

# End page prompt (with visual context)
IMAGE_END_PAGE_TEMPLATE = """Create a peaceful, concluding illustration for a children's book.
Style: {base_style}
{size_instruction}
The scene should feel calm, complete, and satisfying - like a happy ending.
Context from the story: {story_context}
{visual_context}
{text_instruction}"""

# Content page prompt (with visual context)
IMAGE_CONTENT_PAGE_TEMPLATE = """Create an illustration for page {page_number} of a children's book.
Style: {base_style}
{size_instruction}
Scene to illustrate: {page_text}
Overall story context: {story_context}
{visual_context}
The illustration should be simple, clear, and directly related to the text.{text_instruction}"""

# Text overlay instructions
TEXT_OVERLAY_INSTRUCTION_TEMPLATE = """
TEXT ON IMAGE REQUIREMENTS:
Include the following text directly on the illustration:
"{page_text}"

Text styling:
- Font: Large, rounded, child-friendly font (like a storybook font)
- Size: Very large and easy to read for young children
- Color: Dark text (black or dark brown) with a soft white or cream glow/shadow for readability
- Background: Subtle light wash or soft gradient behind text area to ensure readability
- Style: Friendly and playful, matching children's picture book aesthetics

The text must be clearly legible and an integral part of the illustration design."""

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
            size_instruction=IMAGE_SIZE_INSTRUCTION,
            story_summary=story_summary,
            book_title=book_title,
            visual_context=visual_section
        )
    else:
        return IMAGE_COVER_NO_TEXT_TEMPLATE.format(
            base_style=base_style,
            size_instruction=IMAGE_SIZE_INSTRUCTION,
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
        size_instruction=IMAGE_SIZE_INSTRUCTION,
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
        size_instruction=IMAGE_SIZE_INSTRUCTION,
        page_text=page_text,
        page_number=page_number,
        story_context=story_context,
        text_instruction=text_instruction,
        visual_context=visual_section
    )
