"""
LLM 에이전트 패키지 (Claude / Gemini / Groq)

- BaseAgent: LLM 호출·프롬프트 로드·JSON 추출 등 공통 로직 (추상 클래스)
- RFPAnalyzer: RFP 문서 분석 → RFPAnalysis
- ContentGenerator: RFP 분석 결과 + 회사 정보 → Impact-8 구조 ProposalContent
"""

from .rfp_analyzer import RFPAnalyzer
from .content_generator import ContentGenerator

__all__ = ["RFPAnalyzer", "ContentGenerator"]
