"""애플리케이션 설정"""

import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseModel):
    """앱 설정"""

    # LLM: claude | gemini | groq (.env의 LLM_PROVIDER로 선택)
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower().strip()

    # API (Claude / Anthropic)
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

    # API (Gemini)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    # 429 방지: 호출 간 대기(초) + 429 시 재시도 대기 기준값 (Claude/Gemini/Groq 공통). 5~10 권장
    gemini_delay_seconds: float = float(os.getenv("GEMINI_DELAY_SECONDS", "8"))

    # API (Groq, 무료 티어 한도 넉넉함)
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

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
