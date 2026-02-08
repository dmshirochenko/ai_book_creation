"""Root-level test fixtures."""

import os
import pytest

from src.core.config import BookConfig, LLMConfig
from src.core.text_processor import (
    TextProcessor,
    BookContent,
    BookPage,
    PageType,
)
from src.core.prompts import Character, StoryVisualContext


# Ensure no real API keys leak into tests
@pytest.fixture(autouse=True)
def _clear_env_keys(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture
def book_config():
    return BookConfig()


@pytest.fixture
def llm_config():
    return LLMConfig(api_key="test-key-123")


@pytest.fixture
def text_processor():
    return TextProcessor()


@pytest.fixture
def sample_story_text():
    return (
        "The Friendly Fox\n"
        "A little fox named Ruby wakes up.\n"
        "Ruby sees a blue butterfly.\n"
        "She follows the butterfly into the meadow.\n"
        "The butterfly lands on a flower.\n"
        "Ruby smiles and sits beside the flower."
    )


@pytest.fixture
def sample_structured_story():
    return {
        "title": "The Friendly Fox",
        "pages": [
            {"text": "A little fox named Ruby wakes up."},
            {"text": "Ruby sees a blue butterfly."},
            {"text": "She follows the butterfly into the meadow."},
            {"text": "The butterfly lands on a flower."},
            {"text": "Ruby smiles and sits beside the flower."},
        ],
    }


@pytest.fixture
def sample_visual_context():
    return StoryVisualContext(
        characters=[
            Character(name="Ruby", description="A small red fox with bright green eyes"),
            Character(name="Butterfly", description="A blue butterfly with shimmering wings"),
        ],
        setting="A sunny meadow with wildflowers",
        atmosphere="Warm sunny morning, calm and peaceful",
        color_palette="Warm oranges, greens, blues, and yellows",
        background_color="#FFF8E7",
    )


@pytest.fixture
def sample_book_content():
    pages = [
        BookPage(page_type=PageType.COVER, content="The Friendly Fox", page_number=1),
        BookPage(page_type=PageType.CONTENT, content="A little fox named Ruby wakes up.", page_number=2),
        BookPage(page_type=PageType.CONTENT, content="Ruby sees a blue butterfly.", page_number=3),
        BookPage(page_type=PageType.CONTENT, content="She follows the butterfly.", page_number=4),
        BookPage(page_type=PageType.CONTENT, content="The butterfly lands on a flower.", page_number=5),
        BookPage(page_type=PageType.CONTENT, content="Ruby smiles.", page_number=6),
        BookPage(page_type=PageType.END, content="The End", page_number=7),
        BookPage(page_type=PageType.BLANK, content="", page_number=8),
    ]
    return BookContent(title="The Friendly Fox", pages=pages)
