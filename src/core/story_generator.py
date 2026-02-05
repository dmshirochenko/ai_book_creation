"""
Story generation logic with safety validation.

This module provides the StoryGenerator class for creating original children's
stories from user prompts with comprehensive safety guardrails.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional, List

from src.core.config import LLMConfig
from src.core.llm_connector import OpenRouterClient, LLMResponse
from src.core.story_prompts import (
    build_story_creation_prompt,
    check_copyrighted_content,
    check_inappropriate_keywords,
    is_refusal_response,
)


logger = logging.getLogger(__name__)


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class StoryGenerationResult:
    """Result of story generation."""
    success: bool
    title: str = ""
    story: str = ""  # Full formatted story (one sentence per line)
    page_count: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    safety_violations: List[str] = field(default_factory=list)


# =============================================================================
# STORY GENERATOR
# =============================================================================

class StoryGenerator:
    """Generates original children's stories with safety guardrails."""

    def __init__(self, config: LLMConfig):
        """
        Initialize the story generator.

        Args:
            config: LLM configuration
        """
        self.config = config
        self.client = OpenRouterClient(config)

    def _validate_prompt_safety(self, prompt: str) -> tuple[bool, List[str]]:
        """
        Pre-generation safety validation.

        Args:
            prompt: User's story prompt

        Returns:
            Tuple of (is_safe, list of violations)
        """
        violations = []

        # Check copyrighted content
        has_copyright, characters = check_copyrighted_content(prompt)
        if has_copyright:
            violations.extend([f"Copyrighted character: {c}" for c in characters])

        # Check inappropriate keywords
        has_inappropriate, keywords = check_inappropriate_keywords(prompt)
        if has_inappropriate:
            violations.extend([f"Inappropriate keyword: {k}" for k in keywords])

        return (len(violations) == 0, violations)

    async def generate_story(
        self,
        user_prompt: str,
        age_min: int = 2,
        age_max: int = 4,
        tone: str = "cheerful",
        length: str = "medium",
        language: str = "English"
    ) -> StoryGenerationResult:
        """
        Generate a story from user prompt with safety checks.

        Args:
            user_prompt: User's story idea/prompt
            age_min: Minimum target age
            age_max: Maximum target age
            tone: Story tone (cheerful, calm, adventurous, silly)
            length: Story length (short, medium, long)
            language: Target language

        Returns:
            StoryGenerationResult with the generated story or error
        """
        logger.info(f"Generating story: prompt='{user_prompt[:50]}...', age={age_min}-{age_max}, tone={tone}")

        # Pre-validation
        is_safe, violations = self._validate_prompt_safety(user_prompt)
        if not is_safe:
            logger.warning(f"Story prompt failed safety validation: {violations}")
            return StoryGenerationResult(
                success=False,
                error=f"Safety violation detected: {', '.join(violations)}",
                safety_violations=violations
            )

        # Build prompt with safety instructions
        prompt = build_story_creation_prompt(
            user_prompt=user_prompt,
            age_min=age_min,
            age_max=age_max,
            tone=tone,
            length=length,
            language=language
        )

        # Call LLM
        logger.info(f"Calling LLM for story generation with {self.config.max_tokens} max tokens")
        response: LLMResponse = await self.client._call_llm(
            prompt,
            model_override=None  # Use default model from config
        )

        if not response.success:
            logger.error(f"LLM call failed: {response.error}")
            return StoryGenerationResult(
                success=False,
                error=response.error or "LLM call failed"
            )

        # Check if LLM refused the request
        if is_refusal_response(response.content):
            logger.warning("LLM refused to generate story due to safety concerns")
            return StoryGenerationResult(
                success=False,
                error="Story request was rejected by the AI due to safety concerns",
                safety_violations=["LLM refused to generate content"]
            )

        # Parse story (title on first line, story on following lines)
        lines = response.content.strip().split('\n')
        lines = [line.strip() for line in lines if line.strip()]

        if not lines:
            logger.error("Generated story is empty")
            return StoryGenerationResult(
                success=False,
                error="Generated story is empty"
            )

        # Extract title and story
        title = lines[0]
        story_lines = lines[1:] if len(lines) > 1 else []

        # Remove any markdown formatting from title
        title = title.strip('#').strip('*').strip()

        formatted_story = '\n'.join(story_lines)

        logger.info(f"Story generated successfully: '{title}', {len(story_lines)} pages, {response.tokens_used} tokens")

        return StoryGenerationResult(
            success=True,
            title=title,
            story=formatted_story,
            page_count=len(story_lines),
            tokens_used=response.tokens_used
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def generate_story_from_prompt(
    user_prompt: str,
    config: Optional[LLMConfig] = None,
    age_min: int = 2,
    age_max: int = 4,
    tone: str = "cheerful",
    length: str = "medium",
    language: str = "English"
) -> StoryGenerationResult:
    """
    Convenience function to generate a story from a user prompt.

    Args:
        user_prompt: User's story idea/prompt
        config: LLM configuration (uses defaults if not provided)
        age_min: Minimum target age
        age_max: Maximum target age
        tone: Story tone (cheerful, calm, adventurous, silly)
        length: Story length (short, medium, long)
        language: Target language

    Returns:
        StoryGenerationResult with the generated story or error
    """
    if config is None:
        config = LLMConfig()

    # Increase max_tokens for story generation (stories need more space)
    config.max_tokens = 3000

    generator = StoryGenerator(config)
    return await generator.generate_story(
        user_prompt=user_prompt,
        age_min=age_min,
        age_max=age_max,
        tone=tone,
        length=length,
        language=language
    )
