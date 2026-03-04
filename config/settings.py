"""
애플리케이션 설정 모듈

환경 변수(.env) 기반으로 LLM 프로바이더(Claude/Gemini/Groq), API 키, 로그 레벨,
PPTX 경로 등을 로드하고 검증합니다. Pydantic BaseModel을 사용해 타입·범위 검증을 수행합니다.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, field_validator


class Settings(BaseModel):
    """
    앱 전역 설정 (싱글톤으로 사용).

    환경 변수에서 읽으며, LLM_PROVIDER에 따라 사용할 API 키·모델이 결정됩니다.
    """

    # -------------------------------------------------------------------------
    # LLM 프로바이더: claude | gemini | groq (.env의 LLM_PROVIDER로 선택)
    # -------------------------------------------------------------------------
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """LLM_PROVIDER는 claude, gemini, groq 중 하나여야 함."""
        if v not in ("claude", "gemini", "groq"):
            raise ValueError(
                "LLM_PROVIDER must be one of: claude, gemini, groq. "
                "Check your .env or environment."
            )
        return v

    # -------------------------------------------------------------------------
    # API (Claude / Anthropic)
    # -------------------------------------------------------------------------
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # -------------------------------------------------------------------------
    # API (Gemini)
    # -------------------------------------------------------------------------
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

    # -------------------------------------------------------------------------
    # API (Groq, 무료 티어 한도 넉넉함)
    # 413(Request too large) 방지: user 메시지 최대 문자 수. 초과 시 잘라서 전송 (0=제한 없음)
    # groq_max_request_tokens: 요청 전체(입력+출력) 상한. on_demand 한도 6000 이하로 설정 (기본 5500).
    # -------------------------------------------------------------------------
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    groq_max_user_message_chars: int = int(os.getenv("GROQ_MAX_USER_MESSAGE_CHARS", "0") or "0")
    groq_max_request_tokens: int = int(os.getenv("GROQ_MAX_REQUEST_TOKENS", "5000") or "5000")

    # -------------------------------------------------------------------------
    # 로그: DEBUG | INFO | WARNING | ERROR
    # -------------------------------------------------------------------------
    log_level: str = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()

    # -------------------------------------------------------------------------
    # LLM 공통: 재시도·토큰·호출 간 대기 (429/일시 오류 대응)
    # -------------------------------------------------------------------------
    llm_max_tokens_default: int = int(os.getenv("LLM_MAX_TOKENS", "8192") or "8192")
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.4") or "0.4")
    llm_retry_count: int = int(os.getenv("LLM_RETRY_COUNT", "3") or "3")
    llm_retry_base_delay_seconds: float = float(os.getenv("LLM_RETRY_BASE_DELAY", "5") or "5")
    llm_delay_seconds: float = float(os.getenv("LLM_DELAY_SECONDS", "8") or "8")

    @field_validator("llm_delay_seconds", "llm_retry_base_delay_seconds")
    @classmethod
    def validate_delay_non_negative(cls, v: float) -> float:
        """지연/재시도 기본값은 0 이상이어야 함."""
        if v < 0:
            raise ValueError("Delay/retry base must be >= 0")
        return v

    @field_validator("llm_max_tokens_default")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """LLM_MAX_TOKENS는 1~128000 범위."""
        if v < 1 or v > 128000:
            raise ValueError("LLM_MAX_TOKENS must be between 1 and 128000")
        return v

    @field_validator("llm_retry_count")
    @classmethod
    def validate_retry_count(cls, v: int) -> int:
        """LLM_RETRY_COUNT는 1~10 범위."""
        if v < 1 or v > 10:
            raise ValueError("LLM_RETRY_COUNT must be between 1 and 10")
        return v

    @field_validator("llm_temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """LLM_TEMPERATURE는 0~2 범위 (낮을수록 JSON 형식 준수에 유리)."""
        if v < 0 or v > 2:
            raise ValueError("LLM_TEMPERATURE must be between 0 and 2")
        return v

    # -------------------------------------------------------------------------
    # 경로: 프로젝트 루트 기준
    # -------------------------------------------------------------------------
    base_dir: Path = Path(__file__).parent.parent
    templates_dir: Path = base_dir / "templates"
    prompts_dir: Path = base_dir / "config" / "prompts"
    company_data_dir: Path = base_dir / "company_data"
    output_dir: Path = base_dir / "output"
    input_dir: Path = base_dir / "input"

    # -------------------------------------------------------------------------
    # PPTX 기본값 (템플릿 미사용 시)
    # -------------------------------------------------------------------------
    default_template: str = "base_template"
    slide_width_inches: float = 13.33
    slide_height_inches: float = 7.5

    class Config:
        arbitrary_types_allowed = True


_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    싱글톤 설정 인스턴스 반환.

    Returns:
        Settings: 전역 설정 객체 (최초 1회만 생성).
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
