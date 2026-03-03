"""애플리케이션 설정"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, field_validator


class Settings(BaseModel):
    """앱 설정"""

    # LLM: claude | gemini | groq (.env의 LLM_PROVIDER로 선택)
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        if v not in ("claude", "gemini", "groq"):
            raise ValueError(
                "LLM_PROVIDER must be one of: claude, gemini, groq. "
                "Check your .env or environment."
            )
        return v

    # API (Claude / Anthropic)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # API (Gemini)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # API (Groq, 무료 티어 한도 넉넉함)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    # 413(Request too large) 방지: user 메시지 최대 문자 수. 초과 시 잘라서 전송 (0이면 제한 없음)
    groq_max_user_message_chars: int = int(os.getenv("GROQ_MAX_USER_MESSAGE_CHARS", "0") or "0")

    # 로그 레벨 (DEBUG | INFO | WARNING | ERROR)
    log_level: str = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()

    # LLM 공통: 재시도·토큰·호출 간 대기 (429/일시 오류 대응)
    # 응답 최대 토큰. 클 수수록 더 긴·상세한 응답 가능 (4096~16384 권장, 모델 한도 내)
    llm_max_tokens_default: int = int(os.getenv("LLM_MAX_TOKENS", "8192") or "8192")
    llm_retry_count: int = int(os.getenv("LLM_RETRY_COUNT", "3") or "3")
    llm_retry_base_delay_seconds: float = float(os.getenv("LLM_RETRY_BASE_DELAY", "5") or "5")
    # API 호출 간 대기(초). Gemini/Groq 공통. 429 방지용 (0=대기 없음, 무료 한도일 때 5~10 권장)
    llm_delay_seconds: float = float(os.getenv("LLM_DELAY_SECONDS", "8") or "8")

    @field_validator("llm_delay_seconds", "llm_retry_base_delay_seconds")
    @classmethod
    def validate_delay_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("Delay/retry base must be >= 0")
        return v

    @field_validator("llm_max_tokens_default")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        if v < 1 or v > 128000:
            raise ValueError("LLM_MAX_TOKENS must be between 1 and 128000")
        return v

    @field_validator("llm_retry_count")
    @classmethod
    def validate_retry_count(cls, v: int) -> int:
        if v < 1 or v > 10:
            raise ValueError("LLM_RETRY_COUNT must be between 1 and 10")
        return v

    # Paths
    base_dir: Path = Path(__file__).parent.parent
    templates_dir: Path = base_dir / "templates"
    prompts_dir: Path = base_dir / "config" / "prompts"
    company_data_dir: Path = base_dir / "company_data"
    output_dir: Path = base_dir / "output"
    input_dir: Path = base_dir / "input"

    # PPTX Settings
    default_template: str = "base_template"
    slide_width_inches: float = 13.33
    slide_height_inches: float = 7.5

    class Config:
        arbitrary_types_allowed = True


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """싱글톤 설정 반환"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
