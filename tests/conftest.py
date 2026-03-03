"""pytest 공통 픽스처 — 설정·Gemini 클라이언트 모킹으로 테스트 시 .env/API 키 불필요"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """테스트 시 get_settings가 최소 설정만 반환하도록 모킹"""
    mock = MagicMock()
    mock.llm_provider = "gemini"
    mock.prompts_dir = Path(__file__).parent.parent / "config" / "prompts"
    mock.gemini_api_key = "test-key-for-unit-tests"
    mock.llm_delay_seconds = 0
    mock.anthropic_api_key = ""
    mock.groq_api_key = ""
    mock.llm_retry_count = 1
    mock.llm_retry_base_delay_seconds = 0.1
    mock.groq_max_user_message_chars = 0
    mock.llm_max_tokens_default = 4096
    monkeypatch.setattr("config.settings.get_settings", lambda: mock)
    return mock


@pytest.fixture(autouse=True)
def mock_genai_client(monkeypatch):
    """Gemini Client 생성 시 실제 API 호출 없이 Mock 반환 (BaseAgent/ContentGenerator 테스트용)"""
    # base_agent: from google import genai; genai.Client(api_key=...)
    monkeypatch.setattr("google.genai.Client", MagicMock(return_value=MagicMock()))
