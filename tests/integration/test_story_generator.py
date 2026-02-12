"""Integration tests for src/core/story_generator.py (mocked LLM)."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.config import LLMConfig
from src.core.llm_connector import LLMResponse
from src.core.story_generator import StoryGenerator, StoryGenerationResult


@pytest.fixture
def generator(llm_config):
    return StoryGenerator(llm_config)


class TestStoryGeneratorValidation:
    async def test_copyrighted_character_rejected(self, generator):
        result = await generator.generate_story("A story about Elsa from Frozen")
        assert result.success is False
        assert len(result.safety_violations) > 0
        assert any("copyrighted" in v.lower() for v in result.safety_violations)
        assert result.safety_status == "unsafe"
        assert result.safety_reasoning != ""

    async def test_inappropriate_content_rejected(self, generator):
        result = await generator.generate_story("A scary zombie story with blood")
        assert result.success is False
        assert len(result.safety_violations) > 0
        assert result.safety_status == "unsafe"

    async def test_clean_prompt_passes_validation(self, generator):
        # Mock the LLM call since validation should pass
        story_json = json.dumps({
            "safety_status": "safe",
            "safety_reasoning": "",
            "title": "The Happy Bunny",
            "pages": [{"text": "A bunny hops."}, {"text": "The bunny smiles."}],
        })
        mock_response = LLMResponse(content=story_json, tokens_used=100, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.generate_story("A happy bunny in a garden")
            assert result.success is True
            assert result.title == "The Happy Bunny"
            assert result.page_count == 2
            assert result.safety_status == "safe"


class TestStoryGeneratorGeneration:
    async def test_successful_generation(self, generator):
        story_json = json.dumps({
            "safety_status": "safe",
            "safety_reasoning": "",
            "title": "Sunny Day",
            "pages": [
                {"text": "The sun rises."},
                {"text": "Birds sing."},
                {"text": "Everyone is happy."},
            ],
        })
        mock_response = LLMResponse(content=story_json, tokens_used=200, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.generate_story("A sunny day adventure")
            assert result.success is True
            assert result.title == "Sunny Day"
            assert result.page_count == 3
            assert result.tokens_used == 200
            assert "The sun rises." in result.story
            assert result.story_structured["title"] == "Sunny Day"
            assert result.safety_status == "safe"

    async def test_llm_failure(self, generator):
        mock_response = LLMResponse(
            content="", tokens_used=0, success=False, error="API timeout"
        )
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.generate_story("A simple story")
            assert result.success is False
            assert "API timeout" in result.error

    async def test_unparseable_response(self, generator):
        mock_response = LLMResponse(
            content="this is not json", tokens_used=50, success=True
        )
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.generate_story("A simple story")
            assert result.success is False

    async def test_llm_refusal_detected(self, generator):
        story_json = json.dumps({
            "safety_status": "safe",
            "safety_reasoning": "",
            "title": "I cannot create that story",
            "pages": [{"text": "The content was inappropriate."}],
        })
        mock_response = LLMResponse(content=story_json, tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.generate_story("A valid prompt")
            assert result.success is False
            assert "safety" in result.error.lower()
            assert result.safety_status == "unsafe"

    async def test_llm_flags_unsafe(self, generator):
        """Test that LLM safety_status=unsafe is properly detected."""
        story_json = json.dumps({
            "safety_status": "unsafe",
            "safety_reasoning": "The story contains violent themes not suitable for children.",
            "title": "",
            "pages": [],
        })
        mock_response = LLMResponse(content=story_json, tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.generate_story("A valid prompt")
            assert result.success is False
            assert result.safety_status == "unsafe"
            assert "violent themes" in result.safety_reasoning

    async def test_empty_pages_response(self, generator):
        story_json = json.dumps({
            "safety_status": "safe",
            "safety_reasoning": "",
            "title": "Empty",
            "pages": [],
        })
        mock_response = LLMResponse(content=story_json, tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.generate_story("A story about nothing")
            assert result.success is False
