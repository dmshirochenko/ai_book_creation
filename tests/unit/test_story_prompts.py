"""Unit tests for src/core/story_prompts.py."""

import json

from src.core.story_prompts import (
    check_copyrighted_content,
    check_inappropriate_keywords,
    is_refusal_response,
    build_story_creation_prompt,
    get_story_creation_response_format,
    parse_story_output_response,
    LENGTH_TO_PAGES,
    build_story_validation_prompt,
    get_story_validation_response_format,
    parse_story_validation_response,
    STORY_VALIDATION_JSON_SCHEMA,
    build_story_resplit_prompt,
    get_story_resplit_response_format,
    parse_story_resplit_response,
    STORY_RESPLIT_JSON_SCHEMA,
)


# =============================================================================
# check_copyrighted_content
# =============================================================================


class TestCheckCopyrightedContent:
    def test_clean_prompt(self):
        has_violation, found = check_copyrighted_content("A little fox goes on an adventure")
        assert has_violation is False
        assert found == []

    def test_disney_character(self):
        has_violation, found = check_copyrighted_content("Tell me a story about Elsa from Frozen")
        assert has_violation is True
        assert "elsa" in found
        assert "frozen" in found

    def test_marvel_character(self):
        has_violation, found = check_copyrighted_content("Spider-Man saves the day")
        assert has_violation is True
        assert "spider-man" in found

    def test_case_insensitive(self):
        has_violation, found = check_copyrighted_content("MICKEY MOUSE is here")
        assert has_violation is True
        assert "mickey mouse" in found

    def test_word_boundary_no_false_positive(self):
        # "chip" should match on its own but not inside "chipmunk"
        has_violation, found = check_copyrighted_content("A story about chip")
        assert has_violation is True
        # Test that partial matches within larger words don't trigger
        has_violation2, found2 = check_copyrighted_content("A story about a microchip device")
        assert "chip" not in found2


# =============================================================================
# check_inappropriate_keywords
# =============================================================================


class TestCheckInappropriateKeywords:
    def test_clean_prompt(self):
        has_violation, found = check_inappropriate_keywords("A bunny hops in the garden")
        assert has_violation is False
        assert found == []

    def test_violence_keyword(self):
        has_violation, found = check_inappropriate_keywords("The knight will kill the dragon")
        assert has_violation is True
        assert "kill" in found

    def test_scary_keyword(self):
        has_violation, found = check_inappropriate_keywords("A scary zombie story")
        assert has_violation is True
        assert "scary" in found
        assert "zombie" in found

    def test_profanity(self):
        has_violation, found = check_inappropriate_keywords("What the hell is that")
        assert has_violation is True
        assert "hell" in found

    def test_word_boundary(self):
        # "hit" should not match in "white"
        has_violation, found = check_inappropriate_keywords("A white rabbit")
        assert "hit" not in found


# =============================================================================
# is_refusal_response
# =============================================================================


class TestIsRefusalResponse:
    def test_normal_story_not_refusal(self):
        assert is_refusal_response("Once upon a time a bunny hopped.") is False

    def test_refusal_title(self):
        assert is_refusal_response("I cannot create that story because it's inappropriate") is True

    def test_refusal_variant(self):
        assert is_refusal_response("I can't create this kind of content") is True

    def test_case_insensitive(self):
        assert is_refusal_response("I CANNOT CREATE THAT STORY") is True


# =============================================================================
# build_story_creation_prompt
# =============================================================================


class TestBuildStoryCreationPrompt:
    def test_includes_user_prompt(self):
        result = build_story_creation_prompt(
            user_prompt="A kitten finds a ball",
            age_min=2, age_max=4,
            tone="cheerful", length="medium",
            language="English",
        )
        assert "A kitten finds a ball" in result

    def test_includes_age_range(self):
        result = build_story_creation_prompt(
            user_prompt="test",
            age_min=3, age_max=5,
            tone="calm", length="short",
            language="English",
        )
        assert "3" in result
        assert "5" in result

    def test_includes_tone(self):
        result = build_story_creation_prompt(
            user_prompt="test",
            age_min=2, age_max=4,
            tone="silly", length="medium",
            language="English",
        )
        assert "silly" in result

    def test_unknown_length_defaults(self):
        result = build_story_creation_prompt(
            user_prompt="test",
            age_min=2, age_max=4,
            tone="cheerful", length="unknown",
            language="English",
        )
        # Should still produce a valid prompt using default (10, 12)
        assert "10-12" in result


# =============================================================================
# get_story_creation_response_format
# =============================================================================


class TestGetStoryCreationResponseFormat:
    def test_format_structure(self):
        fmt = get_story_creation_response_format()
        assert fmt["type"] == "json_schema"
        schema = fmt["json_schema"]["schema"]
        assert "safety_status" in schema["properties"]
        assert "safety_reasoning" in schema["properties"]
        assert "title" in schema["properties"]
        assert "pages" in schema["properties"]


# =============================================================================
# parse_story_output_response
# =============================================================================


class TestParseStoryOutputResponse:
    def test_valid_json(self):
        data = {
            "safety_status": "safe",
            "safety_reasoning": "",
            "title": "Happy Fox",
            "pages": [
                {"text": "Page one."},
                {"text": "Page two."},
            ],
        }
        result = parse_story_output_response(json.dumps(data))
        assert result["title"] == "Happy Fox"
        assert len(result["pages"]) == 2
        assert result["safety_status"] == "safe"
        assert result["safety_reasoning"] == ""

    def test_unsafe_response(self):
        data = {
            "safety_status": "unsafe",
            "safety_reasoning": "The prompt contains violent content.",
            "title": "",
            "pages": [],
        }
        result = parse_story_output_response(json.dumps(data))
        assert result["safety_status"] == "unsafe"
        assert result["safety_reasoning"] == "The prompt contains violent content."
        assert result["title"] == ""
        assert result["pages"] == []

    def test_missing_safety_fields_defaults_to_safe(self):
        data = {
            "title": "Happy Fox",
            "pages": [{"text": "Page one."}],
        }
        result = parse_story_output_response(json.dumps(data))
        assert result["safety_status"] == "safe"
        assert result["safety_reasoning"] == ""
        assert result["title"] == "Happy Fox"

    def test_markdown_wrapped(self):
        data = {"safety_status": "safe", "safety_reasoning": "", "title": "T", "pages": [{"text": "P"}]}
        wrapped = f"```json\n{json.dumps(data)}\n```"
        result = parse_story_output_response(wrapped)
        assert result["title"] == "T"
        assert result["safety_status"] == "safe"

    def test_invalid_json(self):
        result = parse_story_output_response("not json")
        assert result == {"title": "", "pages": [], "safety_status": "safe", "safety_reasoning": ""}

    def test_not_a_dict(self):
        result = parse_story_output_response(json.dumps([1, 2, 3]))
        assert result == {"title": "", "pages": [], "safety_status": "safe", "safety_reasoning": ""}

    def test_pages_not_a_list(self):
        result = parse_story_output_response(json.dumps({"title": "T", "pages": "bad"}))
        assert result == {"title": "", "pages": [], "safety_status": "safe", "safety_reasoning": ""}

    def test_invalid_page_entries_skipped(self):
        data = {
            "title": "T",
            "pages": [
                {"text": "Valid"},
                {"bad": "entry"},
                "not a dict",
            ],
        }
        result = parse_story_output_response(json.dumps(data))
        assert len(result["pages"]) == 1
        assert result["pages"][0]["text"] == "Valid"


# =============================================================================
# LENGTH_TO_PAGES
# =============================================================================


class TestLengthToPages:
    def test_known_lengths(self):
        assert LENGTH_TO_PAGES["short"] == (6, 8)
        assert LENGTH_TO_PAGES["medium"] == (10, 12)
        assert LENGTH_TO_PAGES["long"] == (14, 16)


# =============================================================================
# Story Validation
# =============================================================================


class TestStoryValidation:
    def test_build_validation_prompt_contains_story(self):
        prompt = build_story_validation_prompt(
            title="The Happy Bunny",
            story_text="A bunny hops in the garden.",
            age_min=2,
            age_max=4,
        )
        assert "The Happy Bunny" in prompt
        assert "A bunny hops in the garden." in prompt
        assert "2-4" in prompt

    def test_validation_response_format_structure(self):
        fmt = get_story_validation_response_format()
        assert fmt["type"] == "json_schema"
        assert "json_schema" in fmt
        schema = fmt["json_schema"]["schema"]
        assert "status" in schema["properties"]
        assert "reasoning" in schema["properties"]

    def test_parse_validation_pass(self):
        response = json.dumps({"status": "pass", "reasoning": ""})
        result = parse_story_validation_response(response)
        assert result["status"] == "pass"
        assert result["reasoning"] == ""

    def test_parse_validation_fail(self):
        response = json.dumps({
            "status": "fail",
            "reasoning": "The story contains violent content."
        })
        result = parse_story_validation_response(response)
        assert result["status"] == "fail"
        assert "violent" in result["reasoning"]

    def test_parse_validation_invalid_json(self):
        result = parse_story_validation_response("not json at all")
        assert result["status"] == "fail"
        assert result["reasoning"] != ""

    def test_parse_validation_missing_fields(self):
        response = json.dumps({"other": "data"})
        result = parse_story_validation_response(response)
        assert result["status"] == "fail"

    def test_parse_validation_invalid_status_value(self):
        response = json.dumps({"status": "maybe", "reasoning": ""})
        result = parse_story_validation_response(response)
        assert result["status"] == "fail"

    def test_parse_validation_json_in_markdown(self):
        response = '```json\n{"status": "pass", "reasoning": ""}\n```'
        result = parse_story_validation_response(response)
        assert result["status"] == "pass"

    def test_validation_schema_is_strict(self):
        assert STORY_VALIDATION_JSON_SCHEMA["strict"] is True
        assert STORY_VALIDATION_JSON_SCHEMA["schema"]["additionalProperties"] is False


# =============================================================================
# Story Re-Split
# =============================================================================


class TestStoryResplit:
    def test_build_resplit_prompt_contains_story(self):
        prompt = build_story_resplit_prompt(
            title="The Happy Bunny",
            story_text="A bunny hops in the garden. The bunny finds a flower.",
            age_min=2,
            age_max=4,
        )
        assert "The Happy Bunny" in prompt
        assert "A bunny hops in the garden." in prompt
        assert "2-4" in prompt
        assert "SPLITTING" in prompt  # Verify it's a split-only prompt

    def test_build_resplit_prompt_includes_age_range(self):
        prompt = build_story_resplit_prompt(
            title="Test",
            story_text="Some story text here.",
            age_min=3,
            age_max=6,
        )
        assert "3-6" in prompt

    def test_resplit_response_format_structure(self):
        fmt = get_story_resplit_response_format()
        assert fmt["type"] == "json_schema"
        assert "json_schema" in fmt
        schema = fmt["json_schema"]["schema"]
        assert "title" in schema["properties"]
        assert "pages" in schema["properties"]

    def test_parse_resplit_valid_response(self):
        response = json.dumps({
            "title": "The Happy Bunny",
            "pages": [
                {"text": "A bunny hops in the garden."},
                {"text": "The bunny finds a flower."},
            ]
        })
        result = parse_story_resplit_response(response)
        assert result["title"] == "The Happy Bunny"
        assert len(result["pages"]) == 2
        assert result["pages"][0]["text"] == "A bunny hops in the garden."

    def test_parse_resplit_empty_pages(self):
        response = json.dumps({"title": "Test", "pages": []})
        result = parse_story_resplit_response(response)
        assert result["pages"] == []
        assert result["title"] == ""  # empty result on no pages

    def test_parse_resplit_invalid_json(self):
        result = parse_story_resplit_response("not json at all")
        assert result["title"] == ""
        assert result["pages"] == []

    def test_parse_resplit_skips_empty_page_text(self):
        response = json.dumps({
            "title": "Test",
            "pages": [
                {"text": "Page one."},
                {"text": ""},
                {"text": "Page three."},
            ]
        })
        result = parse_story_resplit_response(response)
        assert len(result["pages"]) == 2  # Empty page skipped

    def test_parse_resplit_json_in_markdown(self):
        response = '```json\n{"title": "Test", "pages": [{"text": "Page one."}]}\n```'
        result = parse_story_resplit_response(response)
        assert len(result["pages"]) == 1

    def test_resplit_schema_is_strict(self):
        assert STORY_RESPLIT_JSON_SCHEMA["strict"] is True
        assert STORY_RESPLIT_JSON_SCHEMA["schema"]["additionalProperties"] is False

    def test_parse_resplit_not_a_dict(self):
        result = parse_story_resplit_response(json.dumps([1, 2, 3]))
        assert result["title"] == ""
        assert result["pages"] == []

    def test_parse_resplit_pages_not_a_list(self):
        result = parse_story_resplit_response(json.dumps({"title": "T", "pages": "bad"}))
        assert result["title"] == ""
        assert result["pages"] == []

    def test_parse_resplit_invalid_page_entries_skipped(self):
        data = {
            "title": "T",
            "pages": [
                {"text": "Valid page."},
                {"bad": "entry"},
                "not a dict",
            ],
        }
        result = parse_story_resplit_response(json.dumps(data))
        assert len(result["pages"]) == 1
        assert result["pages"][0]["text"] == "Valid page."

    def test_parse_resplit_strips_whitespace(self):
        response = json.dumps({
            "title": "  Test Title  ",
            "pages": [
                {"text": "  Page one.  "},
                {"text": "  Page two.  "},
            ]
        })
        result = parse_story_resplit_response(response)
        assert result["pages"][0]["text"] == "Page one."
        assert result["pages"][1]["text"] == "Page two."

    def test_resplit_schema_no_safety_fields(self):
        """Re-split schema should NOT include safety_status/safety_reasoning."""
        schema_props = STORY_RESPLIT_JSON_SCHEMA["schema"]["properties"]
        assert "safety_status" not in schema_props
        assert "safety_reasoning" not in schema_props
