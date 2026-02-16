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
    get_story_creation_response_format,
    parse_story_output_response,
    build_story_validation_prompt,
    get_story_validation_response_format,
    parse_story_validation_response,
    build_story_resplit_prompt,
    get_story_resplit_response_format,
    parse_story_resplit_response,
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
    story: str = ""  # Full formatted story (one sentence per line, backward compat)
    story_structured: dict = field(default_factory=dict)  # Raw JSON: {"title": str, "pages": [{"text": str}]}
    page_count: int = 0
    tokens_used: int = 0
    error: Optional[str] = None
    safety_violations: List[str] = field(default_factory=list)
    safety_status: str = "safe"
    safety_reasoning: str = ""


@dataclass
class StoryValidationResult:
    """Result of story validation."""
    status: str  # "pass" or "fail"
    reasoning: str = ""
    error: Optional[str] = None


@dataclass
class StoryResplitResult:
    """Result of story re-splitting."""
    success: bool
    story_structured: dict = field(default_factory=dict)  # {"title": str, "pages": [{"text": str}]}
    page_count: int = 0
    error: Optional[str] = None


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
        # Pre-validation
        is_safe, violations = self._validate_prompt_safety(user_prompt)
        if not is_safe:
            logger.warning(f"Story prompt failed safety validation: {violations}")
            return StoryGenerationResult(
                success=False,
                error=f"Safety violation detected: {', '.join(violations)}",
                safety_violations=violations,
                safety_status="unsafe",
                safety_reasoning=f"Your prompt contains content that is not allowed: {', '.join(violations)}",
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

        # Call LLM with structured JSON output
        response_format = get_story_creation_response_format()
        logger.info(f"Calling LLM for story generation with {self.config.max_tokens} max tokens (structured JSON)")
        response: LLMResponse = await self.client._call_llm(
            prompt,
            response_format=response_format,
            model_override=self.config.analysis_model  # Use Gemini Flash for structured outputs
        )

        if not response.success:
            logger.error(f"LLM call failed: {response.error}")
            return StoryGenerationResult(
                success=False,
                error=response.error or "LLM call failed"
            )

        # Parse structured JSON response
        parsed = parse_story_output_response(response.content)

        if not parsed["title"] and not parsed["pages"]:
            # Check if this is an unsafe response (empty title/pages is expected for unsafe)
            if parsed.get("safety_status") == "unsafe":
                safety_reasoning = parsed.get("safety_reasoning", "")
                logger.warning(f"LLM flagged story as unsafe: {safety_reasoning}")
                return StoryGenerationResult(
                    success=False,
                    error=f"Story content is not suitable: {safety_reasoning}",
                    safety_violations=["LLM safety check: " + safety_reasoning],
                    safety_status="unsafe",
                    safety_reasoning=safety_reasoning,
                    tokens_used=response.tokens_used,
                )
            logger.error("Failed to parse story JSON response")
            return StoryGenerationResult(
                success=False,
                error="Failed to parse story response"
            )

        # Check safety status from LLM response
        safety_status = parsed.get("safety_status", "safe")
        safety_reasoning = parsed.get("safety_reasoning", "")

        if safety_status == "unsafe":
            logger.warning(f"LLM flagged story as unsafe: {safety_reasoning}")
            return StoryGenerationResult(
                success=False,
                error=f"Story content is not suitable: {safety_reasoning}",
                safety_violations=["LLM safety check: " + safety_reasoning],
                safety_status="unsafe",
                safety_reasoning=safety_reasoning,
                tokens_used=response.tokens_used,
            )

        # Check if LLM refused the request (title contains refusal pattern — fallback)
        if is_refusal_response(parsed["title"]):
            logger.warning("LLM refused to generate story due to safety concerns")
            return StoryGenerationResult(
                success=False,
                error="Story request was rejected by the AI due to safety concerns",
                safety_violations=["LLM refused to generate content"],
                safety_status="unsafe",
                safety_reasoning="The AI determined this story prompt is not suitable for children.",
            )

        # Check for empty pages (another refusal indicator)
        if not parsed["pages"]:
            logger.error("Generated story has no pages")
            return StoryGenerationResult(
                success=False,
                error="Generated story has no pages"
            )

        title = parsed["title"]
        story_lines = [page["text"] for page in parsed["pages"]]
        formatted_story = '\n'.join(story_lines)

        logger.info(f"Story generated successfully: '{title}', {len(story_lines)} pages, {response.tokens_used} tokens")

        return StoryGenerationResult(
            success=True,
            title=title,
            story=formatted_story,
            story_structured=parsed,
            page_count=len(story_lines),
            tokens_used=response.tokens_used,
            safety_status="safe",
        )

    async def validate_story(
        self,
        title: str,
        story_text: str,
        age_min: int = 2,
        age_max: int = 4,
    ) -> StoryValidationResult:
        """
        Validate an edited story for safety, age-appropriateness, and coherence.

        This is a synchronous check (not a background task). It calls the LLM
        with a validation-only prompt and returns pass/fail with reasoning.

        Args:
            title: Story title
            story_text: Full story text
            age_min: Minimum target age
            age_max: Maximum target age

        Returns:
            StoryValidationResult with pass/fail status and reasoning
        """
        logger.info(f"Validating story: title='{title[:50]}', age={age_min}-{age_max}")

        # Pre-validation: check the story text (title + text) for obvious issues
        combined_text = f"{title} {story_text}"
        has_copyright, characters = check_copyrighted_content(combined_text)
        if has_copyright:
            return StoryValidationResult(
                status="fail",
                reasoning=f"The story contains copyrighted characters: {', '.join(characters)}. Please remove or replace them with original characters.",
            )

        has_inappropriate, keywords = check_inappropriate_keywords(combined_text)
        if has_inappropriate:
            return StoryValidationResult(
                status="fail",
                reasoning=f"The story contains inappropriate content ({', '.join(keywords)}). Please revise the story to be suitable for children.",
            )

        # Build validation prompt
        prompt = build_story_validation_prompt(
            title=title,
            story_text=story_text,
            age_min=age_min,
            age_max=age_max,
        )

        # Call LLM with structured JSON output
        response_format = get_story_validation_response_format()
        response = await self.client._call_llm(
            prompt,
            response_format=response_format,
            model_override=self.config.analysis_model,
        )

        if not response.success:
            logger.error(f"LLM validation call failed: {response.error}")
            return StoryValidationResult(
                status="fail",
                reasoning="Unable to validate story at this time. Please try again.",
                error=response.error,
            )

        # Parse response
        parsed = parse_story_validation_response(response.content)
        logger.info(f"Story validation result: status={parsed['status']}, reasoning='{parsed['reasoning'][:80]}'")

        return StoryValidationResult(
            status=parsed["status"],
            reasoning=parsed["reasoning"],
        )

    async def resplit_story(
        self,
        title: str,
        story_text: str,
        age_min: int = 2,
        age_max: int = 4,
    ) -> StoryResplitResult:
        """
        Re-split an edited story into narrative-aware pages using an LLM.

        This does NOT rewrite the story -- it only decides where to break pages.
        The output format matches what process_structured() expects.

        Args:
            title: Story title
            story_text: Full story text to split into pages
            age_min: Minimum target age
            age_max: Maximum target age

        Returns:
            StoryResplitResult with structured story data or error
        """
        logger.info(f"Re-splitting story: title='{title[:50]}', age={age_min}-{age_max}, text_len={len(story_text)}")

        # Build re-split prompt
        prompt = build_story_resplit_prompt(
            title=title,
            story_text=story_text,
            age_min=age_min,
            age_max=age_max,
        )

        # Call LLM with structured JSON output
        response_format = get_story_resplit_response_format()
        response = await self.client._call_llm(
            prompt,
            response_format=response_format,
            model_override=self.config.analysis_model,
        )

        if not response.success:
            logger.error(f"LLM re-split call failed: {response.error}")
            return StoryResplitResult(
                success=False,
                error=response.error or "LLM call failed",
            )

        # Parse response
        parsed = parse_story_resplit_response(response.content)

        if not parsed["pages"]:
            logger.error("Re-split response has no pages")
            return StoryResplitResult(
                success=False,
                error="Failed to split story into pages",
            )

        logger.info(f"Story re-split successfully: {len(parsed['pages'])} pages")

        return StoryResplitResult(
            success=True,
            story_structured=parsed,
            page_count=len(parsed["pages"]),
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
