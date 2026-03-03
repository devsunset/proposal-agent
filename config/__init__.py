"""
설정 패키지

- Settings: Pydantic 기반 앱 설정 (LLM, API 키, 경로, PPTX 옵션 등)
- get_settings(): 싱글톤 Settings 인스턴스 반환
"""

from .settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
