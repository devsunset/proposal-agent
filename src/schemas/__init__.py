"""
데이터 스키마 패키지

- proposal_schema: ProposalContent, PhaseContent, SlideContent, WinTheme 등 (Impact-8 제안서 구조)
- rfp_schema: RFPAnalysis 및 하위 모델 (RFP 분석 결과)
"""

from .proposal_schema import (
    ProposalContent,
    PhaseContent,
    SlideContent,
    SlideType,
    BulletPoint,
    TableData,
    ChartData,
    WinTheme,
    KPIWithBasis,
)
from .rfp_schema import RFPAnalysis

__all__ = [
    "ProposalContent",
    "PhaseContent",
    "SlideContent",
    "SlideType",
    "BulletPoint",
    "TableData",
    "ChartData",
    "WinTheme",
    "KPIWithBasis",
    "RFPAnalysis",
]
