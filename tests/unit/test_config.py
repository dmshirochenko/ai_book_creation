"""Unit tests for src/core/config.py."""

import pytest

from src.core.config import LLMConfig


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
