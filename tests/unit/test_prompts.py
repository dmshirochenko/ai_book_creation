"""Unit tests for src/core/prompts.py."""

import json

from src.core.prompts import (
    Character,
    StoryVisualContext,
    build_story_analysis_prompt,
    get_story_analysis_response_format,
    parse_story_analysis_response,
    build_image_style,
    build_text_instruction,
    build_cover_image_prompt,
    build_end_page_image_prompt,
    build_content_page_image_prompt,
    NO_TEXT_INSTRUCTION,
)


# =============================================================================
# Character
# =============================================================================


class TestCharacter:
    def test_to_prompt_string(self):
        char = Character(name="Luna", description="A white rabbit")
        result = char.to_prompt_string()
        assert result == "- Luna: A white rabbit"


# =============================================================================
# StoryVisualContext
# =============================================================================


class TestStoryVisualContext:
    def test_to_prompt_section_with_all_fields(self, sample_visual_context):
        section = sample_visual_context.to_prompt_section()
        assert "Ruby" in section
        assert "SETTING:" in section
        assert "ATMOSPHERE:" in section
        assert "COLOR PALETTE:" in section

    def test_to_prompt_section_empty(self):
        ctx = StoryVisualContext()
        assert ctx.to_prompt_section() == ""

    def test_is_empty_true(self):
        ctx = StoryVisualContext()
        assert ctx.is_empty() is True

    def test_is_empty_false_with_characters(self):
        ctx = StoryVisualContext(
            characters=[Character(name="X", description="Y")]
        )
        assert ctx.is_empty() is False

    def test_is_empty_false_with_setting(self):
        ctx = StoryVisualContext(setting="A forest")
        assert ctx.is_empty() is False


# =============================================================================
# build_story_analysis_prompt
# =============================================================================


class TestBuildStoryAnalysisPrompt:
    def test_contains_story(self):
        prompt = build_story_analysis_prompt("A fox found a gem.")
        assert "A fox found a gem." in prompt

    def test_contains_instructions(self):
        prompt = build_story_analysis_prompt("test")
        assert "CHARACTERS" in prompt
        assert "SETTING" in prompt


# =============================================================================
# get_story_analysis_response_format
# =============================================================================


class TestGetStoryAnalysisResponseFormat:
    def test_format_structure(self):
        fmt = get_story_analysis_response_format()
        assert fmt["type"] == "json_schema"
        assert "json_schema" in fmt
        schema = fmt["json_schema"]["schema"]
        assert "characters" in schema["properties"]
        assert "setting" in schema["properties"]


# =============================================================================
# parse_story_analysis_response
# =============================================================================


class TestParseStoryAnalysisResponse:
    def test_valid_json(self):
        data = {
            "characters": [
                {"name": "Luna", "description": "A rabbit"}
            ],
            "setting": "Forest",
            "atmosphere": "Sunny",
            "color_palette": "Greens",
            "background_color": "#FFF8E7",
        }
        result = parse_story_analysis_response(json.dumps(data))
        assert len(result.characters) == 1
        assert result.characters[0].name == "Luna"
        assert result.setting == "Forest"
        assert result.background_color == "#FFF8E7"

    def test_markdown_wrapped_json(self):
        data = {
            "characters": [],
            "setting": "Beach",
            "atmosphere": "Calm",
            "color_palette": "Blues",
            "background_color": "#F0F8FF",
        }
        wrapped = f"```json\n{json.dumps(data)}\n```"
        result = parse_story_analysis_response(wrapped)
        assert result.setting == "Beach"

    def test_invalid_json_returns_empty(self):
        result = parse_story_analysis_response("not json at all")
        assert result.is_empty()

    def test_missing_fields_returns_defaults(self):
        result = parse_story_analysis_response("{}")
        assert result.setting == ""
        assert result.characters == []

    def test_invalid_character_entries_skipped(self):
        data = {
            "characters": [
                {"name": "Valid", "description": "Desc"},
                {"bad": "data"},
                "not a dict",
            ],
            "setting": "",
            "atmosphere": "",
            "color_palette": "",
            "background_color": "",
        }
        result = parse_story_analysis_response(json.dumps(data))
        assert len(result.characters) == 1


# =============================================================================
# build_image_style
# =============================================================================


class TestBuildImageStyle:
    def test_includes_age_range(self):
        result = build_image_style("watercolor", 2, 4)
        assert "watercolor" in result
        assert "2-4" in result


# =============================================================================
# build_text_instruction
# =============================================================================


class TestBuildTextInstruction:
    def test_text_on_image_true(self):
        result = build_text_instruction(True, "Hello world")
        assert "Hello world" in result
        assert "TEXT ON IMAGE" in result

    def test_text_on_image_false(self):
        result = build_text_instruction(False)
        assert result == NO_TEXT_INSTRUCTION

    def test_text_on_image_true_but_empty_text(self):
        result = build_text_instruction(True, "")
        assert result == NO_TEXT_INSTRUCTION


# =============================================================================
# build_cover_image_prompt
# =============================================================================


class TestBuildCoverImagePrompt:
    def test_with_text(self):
        result = build_cover_image_prompt(
            style="watercolor",
            book_title="My Book",
            story_summary="A story about a fox",
            target_age=(2, 4),
            text_on_image=True,
        )
        assert "My Book" in result
        assert "cover" in result.lower()

    def test_without_text(self):
        result = build_cover_image_prompt(
            style="watercolor",
            book_title="My Book",
            story_summary="A story",
            target_age=(2, 4),
            text_on_image=False,
        )
        assert "No text" in result

    def test_with_visual_context(self, sample_visual_context):
        result = build_cover_image_prompt(
            style="watercolor",
            book_title="My Book",
            story_summary="A story",
            target_age=(2, 4),
            visual_context=sample_visual_context,
        )
        assert "Ruby" in result


# =============================================================================
# build_end_page_image_prompt
# =============================================================================


class TestBuildEndPageImagePrompt:
    def test_basic(self):
        result = build_end_page_image_prompt(
            style="watercolor",
            story_context="A fox adventure",
            target_age=(2, 4),
        )
        assert "concluding" in result.lower() or "ending" in result.lower() or "end" in result.lower()


# =============================================================================
# build_content_page_image_prompt
# =============================================================================


class TestBuildContentPageImagePrompt:
    def test_basic(self):
        result = build_content_page_image_prompt(
            style="watercolor",
            page_text="The fox jumped.",
            page_number=3,
            story_context="A fox story",
            target_age=(2, 4),
        )
        assert "The fox jumped." in result
        assert "page 3" in result.lower()

    def test_with_visual_context(self, sample_visual_context):
        result = build_content_page_image_prompt(
            style="watercolor",
            page_text="The fox jumped.",
            page_number=3,
            story_context="A fox story",
            target_age=(2, 4),
            visual_context=sample_visual_context,
        )
        assert "Ruby" in result
