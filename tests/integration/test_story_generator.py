"""Integration tests for src/core/story_generator.py (mocked LLM)."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.config import LLMConfig
from src.core.llm_connector import LLMResponse
from src.core.story_generator import StoryGenerator, StoryGenerationResult, StoryValidationResult, StoryResplitResult


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


class TestStoryValidation:
    async def test_validate_clean_story_passes(self, generator):
        validation_json = json.dumps({"status": "pass", "reasoning": ""})
        mock_response = LLMResponse(content=validation_json, tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.validate_story(
                title="The Happy Bunny",
                story_text="A bunny hops in a sunny garden. The bunny finds a pretty flower.",
                age_min=2,
                age_max=4,
            )
            assert result.status == "pass"
            assert result.reasoning == ""

    async def test_validate_unsafe_story_fails(self, generator):
        validation_json = json.dumps({
            "status": "fail",
            "reasoning": "The story contains violent content."
        })
        mock_response = LLMResponse(content=validation_json, tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.validate_story(
                title="Bad Story",
                story_text="A very violent story.",
                age_min=2,
                age_max=4,
            )
            assert result.status == "fail"
            assert "violent" in result.reasoning

    async def test_validate_copyrighted_story_fails_without_llm(self, generator):
        # Should fail on pre-validation without calling LLM
        result = await generator.validate_story(
            title="Elsa's Adventure",
            story_text="Elsa from Frozen goes on an adventure.",
            age_min=2,
            age_max=4,
        )
        assert result.status == "fail"
        assert "copyrighted" in result.reasoning.lower()

    async def test_validate_inappropriate_story_fails_without_llm(self, generator):
        result = await generator.validate_story(
            title="Scary Story",
            story_text="A scary zombie appears in the dark.",
            age_min=2,
            age_max=4,
        )
        assert result.status == "fail"
        assert "inappropriate" in result.reasoning.lower()

    async def test_validate_llm_failure_returns_fail(self, generator):
        mock_response = LLMResponse(content="", tokens_used=0, success=False, error="API timeout")
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.validate_story(
                title="A Story",
                story_text="Some story text here.",
                age_min=2,
                age_max=4,
            )
            assert result.status == "fail"
            assert "try again" in result.reasoning.lower()


class TestStoryResplit:
    async def test_resplit_story_success(self, generator):
        resplit_json = json.dumps({
            "title": "The Happy Bunny",
            "pages": [
                {"text": "A bunny hops in the garden."},
                {"text": "The bunny finds a flower."},
                {"text": "The bunny brings it home."},
            ]
        })
        mock_response = LLMResponse(content=resplit_json, tokens_used=100, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.resplit_story(
                title="The Happy Bunny",
                story_text="A bunny hops in the garden. The bunny finds a flower. The bunny brings it home.",
                age_min=2,
                age_max=4,
            )
            assert result.success is True
            assert result.page_count == 3
            assert result.story_structured["title"] == "The Happy Bunny"
            assert len(result.story_structured["pages"]) == 3

    async def test_resplit_story_llm_failure(self, generator):
        mock_response = LLMResponse(content="", tokens_used=0, success=False, error="API timeout")
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.resplit_story(
                title="A Story",
                story_text="Some story text here that needs splitting.",
                age_min=2,
                age_max=4,
            )
            assert result.success is False
            assert result.error is not None

    async def test_resplit_story_empty_pages(self, generator):
        resplit_json = json.dumps({"title": "Test", "pages": []})
        mock_response = LLMResponse(content=resplit_json, tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.resplit_story(
                title="Test",
                story_text="Some text that should have pages.",
                age_min=2,
                age_max=4,
            )
            assert result.success is False
            assert "pages" in result.error.lower() or "split" in result.error.lower()

    async def test_resplit_story_preserves_title(self, generator):
        resplit_json = json.dumps({
            "title": "My Custom Title",
            "pages": [{"text": "Page one."}]
        })
        mock_response = LLMResponse(content=resplit_json, tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.resplit_story(
                title="My Custom Title",
                story_text="Page one.",
                age_min=2,
                age_max=4,
            )
            assert result.success is True
            assert result.story_structured["title"] == "My Custom Title"

    async def test_resplit_story_unparseable_response(self, generator):
        mock_response = LLMResponse(content="this is not json", tokens_used=50, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.resplit_story(
                title="Test",
                story_text="Some story text here.",
                age_min=2,
                age_max=4,
            )
            assert result.success is False

    async def test_resplit_result_compatible_with_process_structured(self, generator):
        """Verify the output structure matches what TextProcessor.process_structured() expects."""
        resplit_json = json.dumps({
            "title": "The Happy Bunny",
            "pages": [
                {"text": "A bunny hops in the garden."},
                {"text": "The bunny finds a flower."},
            ]
        })
        mock_response = LLMResponse(content=resplit_json, tokens_used=100, success=True)
        with patch.object(generator.client, "_call_llm", return_value=mock_response):
            result = await generator.resplit_story(
                title="The Happy Bunny",
                story_text="A bunny hops in the garden. The bunny finds a flower.",
                age_min=2,
                age_max=4,
            )
            assert result.success is True
            structured = result.story_structured
            # Verify it has the expected keys for process_structured()
            assert "title" in structured
            assert "pages" in structured
            assert isinstance(structured["pages"], list)
            for page in structured["pages"]:
                assert "text" in page
                assert isinstance(page["text"], str)
