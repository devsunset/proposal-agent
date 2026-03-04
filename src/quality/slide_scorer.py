"""
슬라이드 품질 스코어링 엔진 (규칙 기반)

LLM 호출 없이 규칙 기반으로 생성된 슬라이드의 품질을 빠르게 채점합니다.
content_generator.py에서 각 Phase 생성 후 자동으로 호출됩니다.

평가 항목:
  1. Action Title 준수 (인사이트 기반 제목 여부)
  2. 내용 풍부성 (불릿 수, 텍스트 길이)
  3. 구체성 (수치/데이터/기간 포함 여부)
  4. 플레이스홀더 남용 (빈 자리 표시 과다)
  5. 슬라이드 유형 적합성
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..schemas.proposal_schema import PhaseContent, SlideContent, SlideType


# Action Title 금지 패턴 (topic title 패턴)
_BAD_TITLE_PATTERNS = [
    re.compile(r".*에\s*대하여\s*$"),
    re.compile(r".*의\s*현황\s*$"),
    re.compile(r".*의\s*방안\s*$"),
    re.compile(r".*의\s*필요성\s*$"),
    re.compile(r".*의\s*개요\s*$"),
    re.compile(r".*의\s*배경\s*$"),
    re.compile(r"^관련\s*현황"),
    re.compile(r"^추진\s*계획\s*$"),
    re.compile(r"^세부\s*내용\s*$"),
    re.compile(r"^사업\s*개요\s*$"),
    re.compile(r"^환경\s*분석\s*$"),
    re.compile(r"^전략\s*방향\s*$"),
]

# 필수 플레이스홀더 (경고 없이 허용)
_ALLOWED_PLACEHOLDERS = {
    "회사명", "대표이사명", "PM 성명", "담당자명",
    "설립연도", "직원수", "대표전화", "이메일",
}


@dataclass
class SlideScore:
    """단일 슬라이드 품질 점수"""
    slide_index: int
    title: str
    total: float                          # 0~100 종합 점수
    scores: Dict[str, float] = field(default_factory=dict)  # 항목별 0~1
    issues: List[str] = field(default_factory=list)         # 발견된 문제점


@dataclass
class PhaseQualityReport:
    """Phase 전체 품질 리포트"""
    phase_number: int
    phase_title: str
    total_slides: int
    avg_score: float
    min_score: float
    low_quality_slides: List[Dict]        # score < threshold인 슬라이드
    action_title_violations: int          # Action Title 미준수 수
    placeholder_abuse_count: int          # 플레이스홀더 남용 슬라이드 수
    summary: str = ""                     # 한줄 요약

    def is_acceptable(self, min_avg: int = 60) -> bool:
        return self.avg_score >= min_avg


class SlideQualityScorer:
    """
    슬라이드 콘텐츠 품질을 규칙 기반으로 채점.
    LLM 호출 없이 빠르게 동작합니다.
    """

    def score_slide(self, slide: SlideContent, slide_index: int = 0) -> SlideScore:
        """슬라이드 1개 품질 채점 (0~100점)."""
        scores: Dict[str, float] = {}
        issues: List[str] = []

        # 1. Action Title 검사
        at_score = self._check_action_title(slide.title)
        scores["action_title"] = at_score
        if at_score < 0.5:
            issues.append(f"Topic Title 패턴 감지: '{slide.title}' → Action Title로 개선 필요")

        # 2. 내용 풍부성 검사
        cr_score = self._check_content_richness(slide)
        scores["content_richness"] = cr_score
        if cr_score < 0.5:
            issues.append("콘텐츠 빈약: 불릿 4개 이상 또는 충분한 텍스트 추가 필요")

        # 3. 구체성 검사
        sp_score = self._check_specificity(slide)
        scores["specificity"] = sp_score
        if sp_score < 0.3:
            issues.append("구체성 부족: 수치(%/명/원/건), 기간(년/월), 출처 추가 권장")

        # 4. 플레이스홀더 남용 검사
        ph_score = self._check_placeholder_abuse(slide)
        scores["placeholder_abuse"] = ph_score
        if ph_score < 0.5:
            issues.append("플레이스홀더 과다: [대괄호] 표시를 실제 내용으로 채우거나 제거 권장")

        # 5. 슬라이드 유형 적합성
        tf_score = self._check_type_fitness(slide)
        scores["type_fitness"] = tf_score
        if tf_score < 0.5:
            issues.append(f"슬라이드 유형({slide.slide_type.value}) 대비 데이터 부족")

        # 가중 평균 (action_title 25%, content_richness 30%, specificity 25%, placeholder 15%, type 5%)
        weights = {
            "action_title": 0.25,
            "content_richness": 0.30,
            "specificity": 0.25,
            "placeholder_abuse": 0.15,
            "type_fitness": 0.05,
        }
        total = sum(scores.get(k, 0) * w for k, w in weights.items()) * 100

        return SlideScore(
            slide_index=slide_index,
            title=slide.title,
            total=round(total, 1),
            scores=scores,
            issues=issues,
        )

    def score_phase(
        self,
        phase: PhaseContent,
        min_slide_score: int = 40,
    ) -> PhaseQualityReport:
        """Phase 전체 품질 리포트 생성."""
        if not phase.slides:
            return PhaseQualityReport(
                phase_number=phase.phase_number,
                phase_title=phase.phase_title,
                total_slides=0,
                avg_score=0.0,
                min_score=0.0,
                low_quality_slides=[],
                action_title_violations=0,
                placeholder_abuse_count=0,
                summary="슬라이드 없음",
            )

        slide_scores = [
            self.score_slide(slide, i) for i, slide in enumerate(phase.slides)
        ]
        avg = sum(s.total for s in slide_scores) / len(slide_scores)
        min_s = min(s.total for s in slide_scores)

        low_quality = [
            {
                "index": s.slide_index,
                "title": s.title,
                "score": s.total,
                "issues": s.issues,
            }
            for s in slide_scores
            if s.total < min_slide_score
        ]

        action_violations = sum(
            1 for s in slide_scores if s.scores.get("action_title", 1) < 0.5
        )
        placeholder_abuse = sum(
            1 for s in slide_scores if s.scores.get("placeholder_abuse", 1) < 0.5
        )

        summary_parts = []
        if action_violations:
            summary_parts.append(f"Action Title 미준수 {action_violations}건")
        if placeholder_abuse:
            summary_parts.append(f"플레이스홀더 남용 {placeholder_abuse}건")
        if low_quality:
            summary_parts.append(f"저품질 슬라이드 {len(low_quality)}건")

        return PhaseQualityReport(
            phase_number=phase.phase_number,
            phase_title=phase.phase_title,
            total_slides=len(phase.slides),
            avg_score=round(avg, 1),
            min_score=round(min_s, 1),
            low_quality_slides=low_quality,
            action_title_violations=action_violations,
            placeholder_abuse_count=placeholder_abuse,
            summary="; ".join(summary_parts) if summary_parts else "품질 양호",
        )

    # -----------------------------------------------------------------------
    # Private: 각 항목별 채점
    # -----------------------------------------------------------------------

    def _check_action_title(self, title: str) -> float:
        """Action Title 준수 여부 (0~1)."""
        if not title:
            return 0.0

        # 금지 패턴 확인
        for pattern in _BAD_TITLE_PATTERNS:
            if pattern.search(title):
                return 0.0

        # 숫자 포함 여부 (Action Title의 특징)
        has_number = bool(re.search(r"\d", title))
        # 적절한 길이 (12~50자)
        good_length = 12 <= len(title) <= 50
        # 동사/결론형 표현 (긍정 신호)
        has_verb_conclusion = bool(re.search(
            r"달성|향상|개선|확보|구축|실현|돌파|선점|주도|집중|강화|절감|증가|성장|혁신", title
        ))

        score = 0.4 + 0.2 * has_number + 0.2 * good_length + 0.2 * has_verb_conclusion
        return min(score, 1.0)

    def _check_content_richness(self, slide: SlideContent) -> float:
        """내용 풍부성 (불릿 수, 텍스트 길이)."""
        score = 0.0

        if slide.bullets:
            bullet_count = len(slide.bullets)
            score += min(bullet_count / 4, 1.0) * 0.5  # 4개 이상이면 만점

            avg_len = sum(len(b.text) for b in slide.bullets) / max(bullet_count, 1)
            score += min(avg_len / 25, 1.0) * 0.3  # 평균 25자 이상이면 만점

        elif slide.left_content or slide.right_content:
            lc = slide.left_content or []
            rc = slide.right_content or []
            total = len(lc) + len(rc)
            score += min(total / 6, 1.0) * 0.8

        if slide.table and slide.table.rows:
            score += min(len(slide.table.rows) / 3, 1.0) * 0.2  # 3행 이상이면 만점

        if slide.timeline:
            score += min(len(slide.timeline) / 3, 1.0) * 0.5

        return min(score, 1.0)

    def _check_specificity(self, slide: SlideContent) -> float:
        """구체성 (수치/데이터/출처 포함 여부)."""
        all_text = self._extract_all_text(slide)
        if not all_text:
            return 0.0

        # 수치 패턴: 숫자 + 단위
        has_numbers = bool(re.search(r"\d+\s*[%명만억원건회배배+\-]", all_text))
        # 연도/기간 패턴
        has_period = bool(re.search(r"\d{4}년|\d+개월|\d+주|\d+일", all_text))
        # 출처/데이터 패턴
        has_source = bool(re.search(
            r"출처|Source|기준|조사|리포트|통계|보고서|데이터|\d{4}\s*Q\d",
            all_text, re.IGNORECASE,
        ))
        # KPI/목표 수치 패턴
        has_kpi = bool(re.search(r"\+\d+|\d+\+|→\d+|\d+%|목표|달성|기준", all_text))

        return (
            0.35 * has_numbers
            + 0.25 * has_period
            + 0.20 * has_source
            + 0.20 * has_kpi
        )

    def _check_placeholder_abuse(self, slide: SlideContent) -> float:
        """플레이스홀더 남용 검사 (높을수록 좋음)."""
        all_text = self._extract_all_text(slide)
        if not all_text:
            return 1.0

        # [대괄호] 형태 플레이스홀더 찾기
        placeholders = re.findall(r"\[([^\]]+)\]", all_text)

        # 허용 플레이스홀더 제외
        excess = sum(1 for p in placeholders if p.strip() not in _ALLOWED_PLACEHOLDERS)

        # 초과 0개 → 1.0, 1개 → 0.67, 2개 → 0.33, 3개 이상 → 0.0
        return max(0.0, 1.0 - excess * 0.33)

    def _check_type_fitness(self, slide: SlideContent) -> float:
        """슬라이드 유형 대비 데이터 적합성."""
        st = slide.slide_type

        if st == SlideType.TABLE:
            return 1.0 if (slide.table and slide.table.rows) else 0.0

        if st == SlideType.CHART:
            return 1.0 if slide.chart else 0.3

        if st in (SlideType.TWO_COLUMN, SlideType.THREE_COLUMN):
            has_data = bool(slide.left_content or slide.right_content or slide.bullets)
            return 1.0 if has_data else 0.0

        if st == SlideType.TIMELINE:
            return 1.0 if slide.timeline else 0.0

        if st == SlideType.CHANNEL_STRATEGY:
            return 1.0 if slide.channel_strategy else 0.3

        if st == SlideType.CONTENT_EXAMPLE:
            return 1.0 if slide.content_examples else 0.3

        if st in (SlideType.CONTENT, SlideType.KEY_MESSAGE):
            return 1.0 if (slide.bullets and len(slide.bullets) >= 2) else 0.3

        return 0.8  # 나머지 유형은 기본 점수

    def _extract_all_text(self, slide: SlideContent) -> str:
        """슬라이드에서 모든 텍스트 추출."""
        parts: List[str] = [slide.title or "", slide.subtitle or ""]

        if slide.bullets:
            parts.extend(b.text for b in slide.bullets)
        if slide.left_content:
            parts.extend(b.text for b in slide.left_content)
        if slide.right_content:
            parts.extend(b.text for b in slide.right_content)
        if slide.center_content:
            parts.extend(b.text for b in slide.center_content)
        if slide.key_message:
            parts.append(slide.key_message)
        if slide.table:
            parts.extend(slide.table.headers or [])
            for row in (slide.table.rows or []):
                parts.extend(row)
        if slide.timeline:
            for t in slide.timeline:
                parts.extend([t.title, t.phase, t.description or ""])
        if slide.channel_strategy:
            cs = slide.channel_strategy
            parts.extend([cs.channel_name, cs.role, cs.target_audience])
            parts.extend(cs.content_pillars or [])
        if slide.notes:
            parts.append(slide.notes)

        return " ".join(p for p in parts if p)
