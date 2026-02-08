"""Integration tests for src/core/llm_connector.py (mocked HTTP)."""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import httpx

from src.core.config import LLMConfig
from src.core.llm_connector import OpenRouterClient, LLMResponse, analyze_story_for_visuals
from src.core.prompts import StoryVisualContext


@pytest.fixture
def client(llm_config):
    return OpenRouterClient(llm_config)


def _mock_httpx_response(data: dict, status_code: int = 200):
    """Create a mock httpx.Response."""
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.json.return_value = data
    response.text = json.dumps(data)
    response.raise_for_status = MagicMock()
    if status_code >= 400:
        http_error = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=response
        )
        response.raise_for_status.side_effect = http_error
    return response


class TestOpenRouterClientCallLLM:
    async def test_successful_call(self, client):
        response_data = {
            "choices": [{"message": {"content": "Hello world"}}],
            "usage": {"total_tokens": 42},
        }

        mock_response = _mock_httpx_response(response_data)
        with patch("src.core.llm_connector.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            result = await client._call_llm("test prompt")
            assert result.success is True
            assert result.content == "Hello world"
            assert result.tokens_used == 42

    async def test_no_api_key(self):
        config = LLMConfig(api_key="")
        client = OpenRouterClient(config)
        result = await client._call_llm("test")
        assert result.success is False
        assert "not configured" in result.error.lower()

    async def test_http_error(self, client):
        mock_response = _mock_httpx_response({"error": "bad"}, status_code=500)
        with patch("src.core.llm_connector.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            result = await client._call_llm("test")
            assert result.success is False
            assert "API error" in result.error

    async def test_request_error(self, client):
        with patch("src.core.llm_connector.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = httpx.RequestError("connection failed")
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            result = await client._call_llm("test")
            assert result.success is False
            assert "Request failed" in result.error

    async def test_response_format_passed(self, client):
        response_data = {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"total_tokens": 10},
        }
        mock_response = _mock_httpx_response(response_data)
        with patch("src.core.llm_connector.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            fmt = {"type": "json_schema", "json_schema": {"name": "test"}}
            await client._call_llm("test", response_format=fmt)
            call_kwargs = mock_instance.post.call_args
            payload = call_kwargs.kwargs["json"]
            assert payload["response_format"] == fmt


class TestOpenRouterClientAnalyzeStory:
    async def test_successful_analysis(self, client):
        analysis_json = json.dumps({
            "characters": [{"name": "Fox", "description": "A red fox"}],
            "setting": "Forest",
            "atmosphere": "Sunny",
            "color_palette": "Greens",
            "background_color": "#FFF8E7",
        })
        response_data = {
            "choices": [{"message": {"content": analysis_json}}],
            "usage": {"total_tokens": 100},
        }
        mock_response = _mock_httpx_response(response_data)
        with patch("src.core.llm_connector.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            ctx, resp = await client.analyze_story("A fox in the forest")
            assert resp.success is True
            assert len(ctx.characters) == 1
            assert ctx.setting == "Forest"

    async def test_failed_analysis_returns_empty_context(self, client):
        with patch("src.core.llm_connector.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post.side_effect = httpx.RequestError("fail")
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            ctx, resp = await client.analyze_story("test")
            assert resp.success is False
            assert ctx.is_empty()


class TestAnalyzeStoryForVisuals:
    async def test_convenience_function(self):
        config = LLMConfig(api_key="test-key")
        analysis_json = json.dumps({
            "characters": [],
            "setting": "Beach",
            "atmosphere": "Calm",
            "color_palette": "Blues",
            "background_color": "#F0F8FF",
        })
        response_data = {
            "choices": [{"message": {"content": analysis_json}}],
            "usage": {"total_tokens": 50},
        }
        mock_response = _mock_httpx_response(response_data)
        with patch("src.core.llm_connector.httpx.AsyncClient") as mock_client_cls:
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_instance

            ctx, resp = await analyze_story_for_visuals("test story", config)
            assert resp.success is True
            assert ctx.setting == "Beach"
