"""
산업 통계 데이터베이스 (Industry Statistics DB)

LLM 프롬프트에 검증된 통계 수치를 주입해 할루시네이션을 줄이고
제안서의 구체성을 높입니다.

사용 방법:
    from src.data.industry_stats import get_relevant_stats
    stats_text = get_relevant_stats("marketing_pr", phase_num=2)
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 내장 통계 데이터베이스
# ---------------------------------------------------------------------------

INDUSTRY_STATS: Dict[str, Dict[str, List[Dict]]] = {
    "marketing_pr": {
        "sns_general": [
            {
                "stat": "인스타그램 릴스 도달률이 일반 피드 대비 1.8배 높음",
                "source": "Social Insider, 2025",
                "value": 1.8,
                "unit": "배",
            },
            {
                "stat": "국내 인스타그램 월간 활성 사용자(MAU) 2,644만명",
                "source": "와이즈앱, 2025 Q1",
                "value": 2644,
                "unit": "만명",
            },
            {
                "stat": "Z세대(18~24세) SNS 일평균 사용시간 55분",
                "source": "닐슨 코리아, 2025",
                "value": 55,
                "unit": "분/일",
            },
            {
                "stat": "브랜드 콘텐츠 중 숏폼 참여율이 롱폼 대비 2.3배",
                "source": "HubSpot State of Marketing 2025",
                "value": 2.3,
                "unit": "배",
            },
            {
                "stat": "유튜브 쇼츠 일일 조회수 700억 회 돌파",
                "source": "YouTube Blog, 2025",
                "value": 700,
                "unit": "억 회/일",
            },
            {
                "stat": "국내 유튜브 MAU 4,560만명, 전체 SNS 중 1위",
                "source": "와이즈앱, 2025 Q1",
                "value": 4560,
                "unit": "만명",
            },
        ],
        "influencer": [
            {
                "stat": "마이크로 인플루언서(팔로워 1만~10만) 평균 참여율 3.8%",
                "source": "Influencer Marketing Hub, 2025",
                "value": 3.8,
                "unit": "%",
            },
            {
                "stat": "인플루언서 마케팅 평균 ROI: 투자 1원당 6.5원 수익",
                "source": "Influencer Marketing Hub Annual Report 2025",
                "value": 6.5,
                "unit": "배 ROI",
            },
            {
                "stat": "브랜드 협업 콘텐츠 클릭률(CTR) 일반 광고 대비 4.5배",
                "source": "Meta Business Insights 2025",
                "value": 4.5,
                "unit": "배",
            },
        ],
        "content": [
            {
                "stat": "소비자 84%가 브랜드 콘텐츠보다 지인·인플루언서 추천을 신뢰",
                "source": "Edelman Trust Barometer 2025",
                "value": 84,
                "unit": "%",
            },
            {
                "stat": "SNS 광고 CTR 평균 0.9%, 브랜드 콘텐츠는 3.2%",
                "source": "Statista Digital Advertising Report 2025",
                "value": 3.2,
                "unit": "% CTR",
            },
            {
                "stat": "UGC(사용자 제작 콘텐츠) 포함 캠페인 전환율 4.5배 향상",
                "source": "Bazaarvoice 2025",
                "value": 4.5,
                "unit": "배",
            },
        ],
        "roi": [
            {
                "stat": "SNS 마케팅 예산 집행 시 오가닉 도달 대비 유료 도달 5~8배",
                "source": "Facebook Business 2025",
                "value": 6.5,
                "unit": "배",
            },
        ],
    },
    "it_system": {
        "digital_transformation": [
            {
                "stat": "국내 기업 디지털 전환 투자 전년 대비 23% 증가",
                "source": "IDC Korea, 2025",
                "value": 23,
                "unit": "% 증가",
            },
            {
                "stat": "클라우드 전환 기업 IT 운영 비용 평균 32% 절감",
                "source": "가트너, 2025",
                "value": 32,
                "unit": "% 절감",
            },
            {
                "stat": "AI/ML 적용 시스템 운영 자동화율 평균 45% 향상",
                "source": "McKinsey Digital 2025",
                "value": 45,
                "unit": "% 향상",
            },
            {
                "stat": "레거시 시스템 유지보수 비용 IT 예산의 평균 68% 차지",
                "source": "가트너 IT Spending Report 2025",
                "value": 68,
                "unit": "% 비중",
            },
        ],
        "security": [
            {
                "stat": "국내 기업 사이버 침해사고 전년 대비 38% 증가",
                "source": "KISA 사이버보안 동향 2025",
                "value": 38,
                "unit": "% 증가",
            },
        ],
        "agile": [
            {
                "stat": "애자일 방법론 도입 프로젝트 성공률 비애자일 대비 28% 높음",
                "source": "Standish Group CHAOS Report 2025",
                "value": 28,
                "unit": "% 높음",
            },
        ],
    },
    "event": {
        "participation": [
            {
                "stat": "오프라인 행사 참가자 중 67%가 SNS 콘텐츠 자발적 공유",
                "source": "Eventbrite Annual Report 2025",
                "value": 67,
                "unit": "%",
            },
            {
                "stat": "하이브리드 행사(온·오프라인 병행) 참여자 수 오프라인 단독 대비 3.2배",
                "source": "Cvent Event Trend Report 2025",
                "value": 3.2,
                "unit": "배",
            },
            {
                "stat": "행사 후 브랜드 인지도 평균 34% 향상",
                "source": "Freeman Event Research 2025",
                "value": 34,
                "unit": "% 향상",
            },
        ],
    },
    "public": {
        "policy": [
            {
                "stat": "공공 디지털 서비스 시민 만족도 평균 78점(100점 기준)",
                "source": "한국지능정보사회진흥원(NIA), 2025",
                "value": 78,
                "unit": "점",
            },
            {
                "stat": "공공사업 데이터 기반 의사결정 도입 시 예산 낭비 20% 감소",
                "source": "행정안전부 디지털정부 백서 2025",
                "value": 20,
                "unit": "% 감소",
            },
        ],
    },
    "consulting": {
        "management": [
            {
                "stat": "전략 컨설팅 권고사항 실행률 평균 38% (비전적 지원 없을 때)",
                "source": "Harvard Business Review, 2025",
                "value": 38,
                "unit": "% 실행률",
            },
            {
                "stat": "변화 관리(Change Management) 동반 시 전략 실행 성공률 3.5배",
                "source": "McKinsey & Company 2025",
                "value": 3.5,
                "unit": "배",
            },
        ],
    },
    "general": {},
}

# Phase별 적합 카테고리 매핑 (어떤 Phase에서 어떤 통계를 보여줄지)
_PHASE_STAT_CATEGORIES: Dict[str, List[str]] = {
    "marketing_pr": {
        2: ["sns_general", "content"],       # INSIGHT: 시장 환경 분석
        3: ["sns_general", "influencer"],    # CONCEPT: 전략
        4: ["content", "influencer", "roi"], # ACTION PLAN
        7: ["roi"],                          # INVESTMENT & ROI
    }.get,
    "it_system": {
        2: ["digital_transformation", "security"],
        3: ["digital_transformation", "agile"],
        4: ["agile"],
        7: ["digital_transformation"],
    }.get,
    "event": {
        2: ["participation"],
        4: ["participation"],
        7: ["participation"],
    }.get,
    "public": {
        2: ["policy"],
        4: ["policy"],
    }.get,
    "consulting": {
        2: ["management"],
        3: ["management"],
        7: ["management"],
    }.get,
}


def get_relevant_stats(
    proposal_type: str,
    phase_num: int,
    max_items: int = 5,
    custom_stats_path: Optional[str] = None,
) -> str:
    """
    유형과 Phase에 맞는 통계 데이터 텍스트 반환 (프롬프트 주입용).

    Args:
        proposal_type: 제안서 유형 (marketing_pr, it_system, event, public, consulting, general)
        phase_num: Phase 번호 (0~7)
        max_items: 최대 통계 항목 수
        custom_stats_path: 커스텀 통계 JSON 경로 (INDUSTRY_STATS_PATH 환경변수 우선)

    Returns:
        프롬프트에 삽입할 통계 텍스트 (없으면 빈 문자열)
    """
    # 커스텀 통계 우선 (INDUSTRY_STATS_PATH env)
    env_path = custom_stats_path or os.getenv("INDUSTRY_STATS_PATH", "")
    if env_path:
        try:
            custom = json.loads(Path(env_path).read_text(encoding="utf-8"))
            # 커스텀 데이터를 내장 데이터에 병합
            for ptype, categories in custom.items():
                if ptype not in INDUSTRY_STATS:
                    INDUSTRY_STATS[ptype] = {}
                for cat, items in categories.items():
                    INDUSTRY_STATS[ptype].setdefault(cat, []).extend(items)
        except Exception:
            pass

    stats_by_type = INDUSTRY_STATS.get(proposal_type, {})
    if not stats_by_type:
        # general은 빈 dict이므로 다른 유형에서 폴백하지 않음
        return ""

    # Phase별 적합 카테고리 선택
    phase_getter = _PHASE_STAT_CATEGORIES.get(proposal_type)
    if phase_getter:
        categories = phase_getter(phase_num) or list(stats_by_type.keys())
    else:
        categories = list(stats_by_type.keys())

    # 선택된 카테고리에서 통계 수집
    all_items: List[Dict] = []
    for cat in categories:
        all_items.extend(stats_by_type.get(cat, []))

    # 중복 제거 후 상위 max_items개
    seen: set = set()
    selected: List[Dict] = []
    for item in all_items:
        key = item["stat"]
        if key not in seen:
            seen.add(key)
            selected.append(item)
        if len(selected) >= max_items:
            break

    if not selected:
        return ""

    lines = [
        "## 참고 통계 데이터 (이 수치를 인용하거나 유사 수준의 데이터로 활용하세요)",
    ]
    for item in selected:
        lines.append(f"  - {item['stat']} (출처: {item['source']})")
    return "\n".join(lines)
