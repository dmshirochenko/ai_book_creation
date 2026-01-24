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
        return f"""You are a children's book editor specializing in books for ages {target_age_min}-{target_age_max}.

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
        if not self.config.validate():
            return LLMResponse(
                content="",
                tokens_used=0,
                success=False,
                error="OpenRouter API key not configured. Set OPENROUTER_API_KEY in .env file."
            )
        
        prompt = self._build_adaptation_prompt(
            story, target_age_min, target_age_max, language
        )
        
        payload = {
            "model": self.config.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature
        }
        
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
