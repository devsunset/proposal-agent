"""BaseAgent._extract_json 동작 테스트 (정상 JSON, 마크다운, 꼬리 쉼표 등)"""

import pytest

from src.agents.base_agent import BaseAgent
from src.agents.content_generator import ContentGenerator


@pytest.fixture
def agent():
    """ContentGenerator 인스턴스 (conftest에서 get_settings 모킹됨)"""
    return ContentGenerator()


class TestExtractJson:
    def test_plain_json(self, agent):
        text = '{"project_name": "테스트", "score": 1}'
        out = agent._extract_json(text)
        assert out == {"project_name": "테스트", "score": 1}

    def test_markdown_fence(self, agent):
        text = '```json\n{"a": 1}\n```'
        out = agent._extract_json(text)
        assert out == {"a": 1}

    def test_trailing_comma(self, agent):
        text = '{"a": 1, "b": 2,}'
        out = agent._extract_json(text)
        assert out == {"a": 1, "b": 2}

    def test_empty_string(self, agent):
        assert agent._extract_json("") == {}
        assert agent._extract_json("   ") == {}

    def test_no_json_returns_empty(self, agent):
        out = agent._extract_json("Just plain text.")
        assert out == {}

    def test_nested_object(self, agent):
        text = '{"outer": {"inner": "value"}}'
        out = agent._extract_json(text)
        assert out == {"outer": {"inner": "value"}}
