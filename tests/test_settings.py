"""설정 검증 테스트 (LLM_PROVIDER 등)"""

import os
import importlib

import pytest


def test_llm_provider_valid(monkeypatch):
    """유효한 LLM_PROVIDER는 통과"""
    from config.settings import Settings
    for provider in ("claude", "gemini", "groq"):
        monkeypatch.setattr(os, "getenv", lambda k, d="": {"LLM_PROVIDER": provider}.get(k, d))
        # Settings()는 필드 기본값으로 os.getenv를 사용하므로, 직접 값을 넘겨 검증만 테스트
        s = Settings(llm_provider=provider)
        assert s.llm_provider == provider


def test_llm_provider_invalid():
    """잘못된 LLM_PROVIDER는 ValueError"""
    from config.settings import Settings
    from pydantic import ValidationError
    with pytest.raises((ValueError, ValidationError)):
        Settings(llm_provider="invalid_provider")
