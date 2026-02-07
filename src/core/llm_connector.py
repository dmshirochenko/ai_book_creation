"""
OpenRouter LLM Connector.

This module handles communication with OpenRouter API for story analysis
and other LLM operations.
"""

import httpx
import json
from typing import Optional
from dataclasses import dataclass

from src.core.config import LLMConfig
from src.core.prompts import (
    build_story_analysis_prompt,
    get_story_analysis_response_format,
    parse_story_analysis_response,
    StoryVisualContext,
)


@dataclass
class LLMResponse:
    """Response from LLM API."""
    content: str
    tokens_used: int
    success: bool
    error: Optional[str] = None


class OpenRouterClient:
    """Client for OpenRouter API for story analysis and generation."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/book-generator",
            "X-Title": "Children's Book Generator"
        }

    async def _call_llm(
        self,
        prompt: str,
        response_format: Optional[dict] = None,
        model_override: Optional[str] = None
    ) -> LLMResponse:
        """
        Make a call to the LLM API.

        Args:
            prompt: The prompt to send
            response_format: Optional response format for structured outputs
                            (e.g., {"type": "json_schema", "json_schema": {...}})
            model_override: Optional model to use instead of config.model

        Returns:
            LLMResponse with the result
        """
        if not self.config.validate():
            return LLMResponse(
                content="",
                tokens_used=0,
                success=False,
                error="OpenRouter API key not configured. Set OPENROUTER_API_KEY in .env file."
            )

        payload = {
            "model": model_override or self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature
        }

        # Add structured outputs if specified
        if response_format:
            payload["response_format"] = response_format

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.config.base_url}/chat/completions",
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()

                data = response.json()
                content = data["choices"][0]["message"]["content"]
                tokens = data.get("usage", {}).get("total_tokens", 0)

                return LLMResponse(
                    content=content.strip(),
                    tokens_used=tokens,
                    success=True
                )

        except httpx.HTTPStatusError as e:
            return LLMResponse(
                content="",
                tokens_used=0,
                success=False,
                error=f"API error: {e.response.status_code} - {e.response.text}"
            )
        except httpx.RequestError as e:
            return LLMResponse(
                content="",
                tokens_used=0,
                success=False,
                error=f"Request failed: {str(e)}"
            )
        except (KeyError, json.JSONDecodeError) as e:
            return LLMResponse(
                content="",
                tokens_used=0,
                success=False,
                error=f"Invalid response format: {str(e)}"
            )

    async def analyze_story(self, story: str) -> tuple[StoryVisualContext, LLMResponse]:
        """
        Analyze a story to extract visual context for consistent illustrations.
        Uses OpenRouter Structured Outputs for guaranteed valid JSON.
        Uses a separate model (analysis_model) that supports structured outputs.

        Args:
            story: The story text to analyze

        Returns:
            Tuple of (StoryVisualContext, LLMResponse)
        """
        prompt = build_story_analysis_prompt(story)
        response_format = get_story_analysis_response_format()

        # Use analysis_model which supports structured outputs
        response = await self._call_llm(
            prompt,
            response_format=response_format,
            model_override=self.config.analysis_model
        )

        if response.success:
            visual_context = parse_story_analysis_response(response.content)
            return visual_context, response
        else:
            return StoryVisualContext(), response

async def analyze_story_for_visuals(
    story: str,
    config: Optional[LLMConfig] = None,
) -> tuple[StoryVisualContext, LLMResponse]:
    """
    Convenience function to analyze a story for visual context.

    Args:
        story: The story text to analyze
        config: LLM configuration (uses defaults if not provided)

    Returns:
        Tuple of (StoryVisualContext, LLMResponse)
    """
    if config is None:
        config = LLMConfig()

    client = OpenRouterClient(config)
    return await client.analyze_story(story)
