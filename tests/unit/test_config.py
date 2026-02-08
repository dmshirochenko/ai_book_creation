"""Unit tests for src/core/config.py."""

import pytest

from src.core.config import BookConfig, LLMConfig, GeneratorConfig


class TestBookConfig:
    def test_defaults(self):
        config = BookConfig()
        assert config.target_age_min == 2
        assert config.target_age_max == 4
        assert config.language == "English"
        assert config.font_size == 24
        assert config.title_font_size == 36
        assert config.paper_size == "A4"
        assert config.text_on_image is False
        assert config.background_color is None

    def test_custom_values(self):
        config = BookConfig(
            target_age_min=3,
            target_age_max=6,
            language="Spanish",
            font_size=28,
            background_color="#FFF8E7",
        )
        assert config.target_age_min == 3
        assert config.target_age_max == 6
        assert config.language == "Spanish"
        assert config.font_size == 28
        assert config.background_color == "#FFF8E7"


class TestLLMConfig:
    def test_defaults(self):
        config = LLMConfig()
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.max_tokens == 2000
        assert config.temperature == 0.7

    def test_validate_with_key(self):
        config = LLMConfig(api_key="test-key")
        assert config.validate() is True

    def test_validate_without_key(self):
        config = LLMConfig(api_key="")
        assert config.validate() is False


class TestGeneratorConfig:
    def test_default_sub_configs(self):
        config = GeneratorConfig()
        assert isinstance(config.book, BookConfig)
        assert isinstance(config.llm, LLMConfig)
        assert config.debug_mode is False
