"""
애플리케이션 설정 모듈

환경 변수(.env) 기반으로 LLM 프로바이더(Claude/Gemini/Groq), API 키, 로그 레벨,
PPTX 경로 등을 로드하고 검증합니다. Pydantic BaseModel을 사용해 타입·범위 검증을 수행합니다.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator


class Settings(BaseModel):
    """
    앱 전역 설정 (싱글톤으로 사용).

    환경 변수에서 읽으며, LLM_PROVIDER에 따라 사용할 API 키·모델이 결정됩니다.
    """

    # -------------------------------------------------------------------------
    # LLM 프로바이더: claude | gemini | groq | ollama (.env의 LLM_PROVIDER로 선택)
    # ollama: 로컬 Ollama 서버, API 키 불필요, 비용/할당량 제한 없음
    # -------------------------------------------------------------------------
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

    @field_validator("llm_provider")
    @classmethod
    def validate_llm_provider(cls, v: str) -> str:
        """LLM_PROVIDER는 claude, gemini, groq, ollama 중 하나여야 함."""
        if v not in ("claude", "gemini", "groq", "ollama"):
            raise ValueError(
                "LLM_PROVIDER must be one of: claude, gemini, groq, ollama. "
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
    # Ollama (로컬 LLM, LLM_PROVIDER=ollama 일 때)
    # API 키 불필요. 로컬에서 ollama serve 실행 필요.
    # -------------------------------------------------------------------------
    ollama_base_url: str = (os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1") or "http://localhost:11434/v1").strip().rstrip("/") + "/"
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:latest").strip()

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
    # LLM JSON 응답 추출 실패 시 재시도 횟수 (1~5). 기대 필드 명시 후 재요청
    llm_json_retry_count: int = int(os.getenv("LLM_JSON_RETRY_COUNT", "2") or "2")

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

    @field_validator("llm_json_retry_count")
    @classmethod
    def validate_json_retry_count(cls, v: int) -> int:
        """LLM_JSON_RETRY_COUNT는 1~5 (JSON 응답 추출 실패 시 재시도 횟수)."""
        if v < 1 or v > 5:
            raise ValueError("LLM_JSON_RETRY_COUNT must be between 1 and 5")
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
    company_data_dir: Path = base_dir / "company_data"
    output_dir: Path = base_dir / "output"
    input_dir: Path = base_dir / "input"

    @property
    def prompts_dir(self) -> Path:
        """PROMPT_VERSION 환경변수가 있으면 해당 이름의 프롬프트 디렉토리 사용 (예: config/prompts/)."""
        base = self.base_dir / "config" / "prompts"
        v = (self.prompt_version or "").strip()
        if v:
            versioned = base / v
            if versioned.exists():
                return versioned
        return base

    # -------------------------------------------------------------------------
    # PPTX 기본값 (템플릿 미사용 시)
    # -------------------------------------------------------------------------
    default_template: str = "base_template"
    slide_width_inches: float = 13.33
    slide_height_inches: float = 7.5

    # -------------------------------------------------------------------------
    # 고도화 기능 활성화 옵션 (advance.md Phase 1~2)
    # -------------------------------------------------------------------------
    # RFP 청킹: 의미 단위 분할로 25,000자 제한 해소
    enable_rfp_chunking: bool = os.getenv("ENABLE_RFP_CHUNKING", "true").lower() == "true"
    rfp_chunk_max_chars: int = int(os.getenv("RFP_CHUNK_MAX_CHARS", "40000") or "40000")

    # Draft → Critique → Refine 사이클 (토큰 비용 3배, 기본 off)
    enable_self_refinement: bool = os.getenv("ENABLE_SELF_REFINEMENT", "false").lower() == "true"

    # Phase별 체크포인트 저장 (API 실패 시 재시작 불필요)
    enable_checkpoint: bool = os.getenv("ENABLE_CHECKPOINT", "true").lower() == "true"

    # 슬라이드 품질 자동 스코어링 (규칙 기반, 경고 출력)
    enable_quality_scoring: bool = os.getenv("ENABLE_QUALITY_SCORING", "true").lower() == "true"
    min_quality_score: int = int(os.getenv("MIN_QUALITY_SCORE", "60") or "60")
    min_slide_quality_score: int = int(os.getenv("MIN_SLIDE_QUALITY_SCORE", "40") or "40")

    # Cross-Phase Context: 이전 Phase 결론을 다음 Phase에 전달
    enable_cross_phase_context: bool = os.getenv("ENABLE_CROSS_PHASE_CONTEXT", "true").lower() == "true"

    # 산업 통계 DB 주입 (프롬프트에 검증된 통계 삽입)
    enable_industry_stats: bool = os.getenv("ENABLE_INDUSTRY_STATS", "true").lower() == "true"

    # 프롬프트 버전 관리
    prompt_version: str = os.getenv("PROMPT_VERSION", "")

    # 품질 개선: Action Title 자동 수정 시도
    enable_auto_fix_titles: bool = os.getenv("ENABLE_AUTO_FIX_TITLES", "false").lower() == "true"

    model_config = ConfigDict(arbitrary_types_allowed=True)


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
