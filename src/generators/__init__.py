"""
PPTX 생성 패키지 ([회사명] 레이어)

- TemplateManager: 템플릿 PPTX 로드, 테마(색상·폰트)·레이아웃 추출, 디자인 시스템 제공
- PPTXGenerator: 슬라이드 추가(타이틀, 콘텐츠, 테이블, 2/3단, 티저, 섹션 구분 등)
- ChartGenerator: 차트, 타임라인, 조직도, KPI 카드, 경쟁사 비교, ROI 시각화
- DiagramGenerator: 프로세스 플로우, 피처 박스, Before/After, 컨셉 다이어그램
"""

from .template_manager import TemplateManager
from .pptx_generator import PPTXGenerator
from .chart_generator import ChartGenerator

__all__ = ["TemplateManager", "PPTXGenerator", "ChartGenerator"]
