"""
OpenRouter LLM Connector for text adaptation.

This module handles communication with OpenRouter API to adapt stories
for young children.
"""

import httpx
import json
from typing import Optional
from dataclasses import dataclass

from src.core.config import LLMConfig
from src.core.prompts import (
    build_story_adaptation_prompt,
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
    """Client for OpenRouter API to adapt text for children's books."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/book-generator",
            "X-Title": "Children's Book Generator"
        }
    
    def _build_adaptation_prompt(
        self,
        story: str,
        target_age_min: int,
        target_age_max: int,
        language: str
    ) -> str:
        """Build the prompt for story adaptation."""
        return build_story_adaptation_prompt(
            story=story,
            target_age_min=target_age_min,
            target_age_max=target_age_max,
            language=language
        )

    def _call_llm(
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
            with httpx.Client(timeout=60.0) as client:
                response = client.post(
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

    def analyze_story(self, story: str) -> tuple[StoryVisualContext, LLMResponse]:
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
        response = self._call_llm(
            prompt,
            response_format=response_format,
            model_override=self.config.analysis_model
        )
        
        if response.success:
            visual_context = parse_story_analysis_response(response.content)
            return visual_context, response
        else:
            return StoryVisualContext(), response

    def adapt_story(
        self,
        story: str,
        target_age_min: int = 2,
        target_age_max: int = 4,
        language: str = "English"
    ) -> LLMResponse:
        """
        Adapt a story for young children using the LLM.
        
        Args:
            story: The original story text
            target_age_min: Minimum target age
            target_age_max: Maximum target age
            language: Target language for the book
            
        Returns:
            LLMResponse with adapted text
        """
        prompt = self._build_adaptation_prompt(
            story, target_age_min, target_age_max, language
        )
        return self._call_llm(prompt)


def adapt_story_for_children(
    story: str,
    config: Optional[LLMConfig] = None,
    target_age_min: int = 2,
    target_age_max: int = 4,
    language: str = "English"
) -> LLMResponse:
    """
    Convenience function to adapt a story for children.
    
    Args:
        story: The original story text
        config: LLM configuration (uses defaults if not provided)
        target_age_min: Minimum target age
        target_age_max: Maximum target age
        language: Target language
        
    Returns:
        LLMResponse with adapted text
    """
    if config is None:
        config = LLMConfig()
    
    client = OpenRouterClient(config)
    return client.adapt_story(story, target_age_min, target_age_max, language)


def analyze_story_for_visuals(
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
    return client.analyze_story(story)
