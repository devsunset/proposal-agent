"""
LLM 에이전트 패키지 (Claude / Gemini / Groq / Ollama).

- BaseAgent: LLM 호출·프롬프트 로드·JSON 추출(응답 형식·기대 필드 명시) 등 공통 로직
- RFPAnalyzer: RFP 문서 분석 → RFPAnalysis
- ContentGenerator: RFP 분석 + 회사 정보 → Impact-8 ProposalContent
"""

from .rfp_analyzer import RFPAnalyzer
from .content_generator import ContentGenerator

__all__ = ["RFPAnalyzer", "ContentGenerator"]
