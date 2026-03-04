"""
제안서 콘텐츠 생성 에이전트 (v3.6 - Impact-8 Framework + 설득 구조 강화)

실제 수주 성공 제안서 분석을 기반으로 개선된 8-Phase 구조
v3.6: Win Theme 전달 체인, Action Title 강제, C-E-I 설득 로직, KPIWithBasis
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional

from config.settings import get_settings
from .base_agent import BaseAgent
from ..schemas.proposal_schema import (
    BulletPoint,
    ChartData,
    KPIItem,
    KPIWithBasis,
    WinTheme,
    CompetitorComparison,
    OrgChartNode,
    PhaseContent,
    ProposalContent,
    ProposalType,
    SlideContent,
    SlideType,
    TeaserContent,
    TimelineItem,
    ContentExample,
    ChannelStrategy,
    CampaignPlan,
    PHASE_DEFINITIONS,
    PHASE_TITLES,
    get_phase_weights,
)
from ..schemas.rfp_schema import RFPAnalysis
from ..utils.logger import get_logger
from config.proposal_types import get_config, get_phase_config, ProposalType as ConfigProposalType

logger = get_logger("content_generator")

# 모델별 응답 키 통일: camelCase 등 → snake_case (공통 처리)
TEASER_KEY_ALIASES = {
    "mainSlogan": "main_slogan",
    "subMessage": "sub_message",
    "visualConcept": "visual_concept",
    "keyVisuals": "key_visuals",
}
PHASE_KEY_ALIASES = {"winThemeKey": "win_theme_key"}
SLIDE_KEY_ALIASES = {
    "slideType": "slide_type",
    "contentExamples": "content_examples",
    "competitorComparison": "competitor_comparison",
}


class ContentGenerator(BaseAgent):
    """제안서 콘텐츠 생성 에이전트 (v3.6 - Impact-8 Framework + 설득 구조 강화)"""

    # Impact-8 Phase 프롬프트 매핑
    PHASE_PROMPTS = {
        0: "phase0_hook",
        1: "phase1_summary",
        2: "phase2_insight",
        3: "phase3_concept",
        4: "phase4_action",
        5: "phase5_management",
        6: "phase6_whyus",
        7: "phase7_investment",
    }

    PHASE_SUBTITLES = {
        0: "임팩트 있는 오프닝",
        1: "Executive Summary",
        2: "시장 환경 & 문제 정의",
        3: "핵심 컨셉 & 차별화 전략",
        4: "상세 실행 계획",
        5: "운영 & 품질 관리",
        6: "수행 역량 & 실적",
        7: "투자 비용 & 기대효과",
    }

    async def execute(
        self,
        input_data: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
        diagnostics_out: Optional[List[Dict[str, Any]]] = None,
    ) -> ProposalContent:
        """
        RFP 분석 결과를 바탕으로 제안서 콘텐츠 생성 (Impact-8 Framework)

        Args:
            input_data: {
                "rfp_analysis": RFPAnalysis,
                "company_data": Dict,
                "project_name": str,
                "client_name": str,
                "submission_date": str,
                "proposal_type": str (optional)
            }
            progress_callback: 진행 상황 콜백
            diagnostics_out: Phase별 소요시간·슬라이드 수·JSON 성공 여부를 담을 리스트 (고도화: 로깅·진단)

        Returns:
            ProposalContent: 생성된 제안서 콘텐츠
        """
        phases: List[PhaseContent] = []
        teaser: Optional[TeaserContent] = None
        win_themes: List[Dict[str, Any]] = []  # v3.6: Win Theme 전달 체인
        diagnostics: List[Dict[str, Any]] = []

        rfp_analysis: RFPAnalysis = input_data["rfp_analysis"]

        # 제안서 유형 판단 (v3.6: RFP에서 추출한 project_type 우선 사용)
        proposal_type = self._determine_proposal_type(
            input_data.get("proposal_type") or getattr(rfp_analysis, 'project_type', None),
            rfp_analysis
        )

        # 유형별 가중치 가져오기
        weights = get_phase_weights(proposal_type)

        # Phase 0: HOOK (티저) 생성
        if progress_callback:
            progress_callback({
                "step": 0,
                "total": 8,
                "message": f"Phase 0: {PHASE_TITLES[0]} 생성 중...",
            })
        t0 = time.perf_counter()
        teaser = await self._generate_teaser(
            rfp_analysis=rfp_analysis,
            company_data=input_data.get("company_data", {}),
            project_name=input_data["project_name"],
            client_name=input_data["client_name"],
            proposal_type=proposal_type,
        )
        logger.info("Phase 0: HOOK 생성 완료")
        diagnostics.append({
            "phase": 0,
            "phase_title": PHASE_TITLES.get(0, "HOOK"),
            "slides_count": len(teaser.slides) if teaser and teaser.slides else 0,
            "elapsed_sec": round(time.perf_counter() - t0, 2),
            "json_ok": True,
        })

        # Phase 1: SUMMARY 생성 → Win Theme 3개 확정
        if progress_callback:
            progress_callback({
                "step": 1,
                "total": 8,
                "message": f"Phase 1: {PHASE_TITLES[1]} 생성 중...",
            })
        t0 = time.perf_counter()
        phase1_content, phase1_raw = await self._generate_phase_with_raw(
            phase_num=1,
            rfp_analysis=rfp_analysis,
            company_data=input_data.get("company_data", {}),
            project_name=input_data["project_name"],
            client_name=input_data["client_name"],
            proposal_type=proposal_type,
            weight=weights.get(1, 0.05),
        )
        phases.append(phase1_content)
        logger.info("Phase 1: SUMMARY 생성 완료")
        diagnostics.append({
            "phase": 1,
            "phase_title": PHASE_TITLES.get(1, "SUMMARY"),
            "slides_count": len(phase1_content.slides),
            "elapsed_sec": round(time.perf_counter() - t0, 2),
            "json_ok": bool(phase1_raw and phase1_raw.get("slides")),
        })

        # v3.6: Phase 1 응답에서 Win Theme 추출
        win_themes = self._extract_win_themes(phase1_raw)
        if win_themes:
            logger.info(f"Win Theme {len(win_themes)}개 확정: {[wt.get('name', '') for wt in win_themes]}")
        else:
            # RFP 분석에서 Win Theme 후보 사용 (폴백)
            win_theme_candidates = getattr(rfp_analysis, 'win_theme_candidates', [])
            if win_theme_candidates:
                win_themes = win_theme_candidates
                logger.info(f"RFP Win Theme 후보 {len(win_themes)}개 사용 (폴백)")

        # Phase 2~7 순차 생성 (단계별 로그, Win Theme 전달)
        for phase_num in range(2, 8):
            if progress_callback:
                progress_callback({
                    "step": 1 + phase_num,
                    "total": 8,
                    "message": f"Phase {phase_num}: {PHASE_TITLES[phase_num]} 생성 중...",
                })
            logger.info("Phase {}: {} 생성 중...", phase_num, PHASE_TITLES[phase_num])
            t0 = time.perf_counter()
            phase_content = await self._generate_phase(
                phase_num=phase_num,
                rfp_analysis=rfp_analysis,
                company_data=input_data.get("company_data", {}),
                project_name=input_data["project_name"],
                client_name=input_data["client_name"],
                proposal_type=proposal_type,
                weight=weights.get(phase_num, 0.1),
                win_themes=win_themes,
            )
            phases.append(phase_content)
            logger.info("Phase {}: {} 생성 완료", phase_num, PHASE_TITLES[phase_num])
            diagnostics.append({
                "phase": phase_num,
                "phase_title": PHASE_TITLES.get(phase_num, ""),
                "slides_count": len(phase_content.slides),
                "elapsed_sec": round(time.perf_counter() - t0, 2),
                "json_ok": len(phase_content.slides) > 0,
            })

        # 핵심 메시지 추출 (Executive Summary/Teaser에서)
        one_sentence_pitch, key_differentiators, slogan = self._extract_key_messages(
            teaser, phases[0] if phases else None
        )

        # v3.6: Win Theme을 WinTheme 모델로 변환
        win_theme_models = self._build_win_theme_models(win_themes)

        if diagnostics_out is not None:
            diagnostics_out.clear()
            diagnostics_out.extend(diagnostics)

        return ProposalContent(
            project_name=input_data["project_name"],
            client_name=input_data["client_name"],
            submission_date=input_data.get("submission_date", ""),
            company_name=input_data.get("company_name", "[회사명]"),
            proposal_type=proposal_type,
            one_sentence_pitch=one_sentence_pitch,
            key_differentiators=key_differentiators,
            slogan=slogan,
            win_themes=win_theme_models if win_theme_models else None,
            rfp_summary=rfp_analysis.model_dump(),
            teaser=teaser,
            phases=phases,
            design_style="guide_template",
        )

    async def _generate_teaser(
        self,
        rfp_analysis: RFPAnalysis,
        company_data: Dict,
        project_name: str,
        client_name: str,
        proposal_type: ProposalType,
    ) -> TeaserContent:
        """Phase 0: HOOK (티저) 콘텐츠 생성"""

        system_prompt = self._load_prompt(self.PHASE_PROMPTS[0])
        if not system_prompt:
            system_prompt = self._get_phase_system_prompt(0)

        # 프로젝트 유형에 따른 티저 슬라이드 수 결정
        type_config = get_config(ConfigProposalType(proposal_type.value))
        phase_config = type_config.phases.get(0)
        min_slides = phase_config.min_slides if phase_config else 3
        max_slides = phase_config.max_slides if phase_config else 10

        user_message = f"""
프로젝트명: {project_name}
발주처: {client_name}
제안서 유형: {proposal_type.value}

## RFP 분석 결과
{json.dumps(rfp_analysis.model_dump(), ensure_ascii=False, indent=2)[:8000]}

## 요청사항
Phase 0: HOOK (티저) 슬라이드를 생성해주세요.
- 슬라이드 수: {min_slides}~{max_slides}장
- 목적: 본문 시작 전 강력한 첫인상으로 몰입감 형성
- main_slogan, sub_message, 각 slide의 title/key_message는 한두 단어가 아닌 **문장 단위**로 작성하세요.

다음 JSON 형식으로 응답해주세요:

```json
{{
    "main_slogan": "핵심 슬로건/한 줄 메시지",
    "sub_message": "부제목 메시지",
    "visual_concept": "비주얼 컨셉 설명",
    "key_visuals": ["비주얼1 설명", "비주얼2 설명"],
    "slides": [
        {{
            "slide_type": "teaser",
            "title": "슬라이드 제목",
            "subtitle": "부제목",
            "key_message": "핵심 메시지",
            "visual_style": "dark|gradient_dark|light",
            "layout_hint": "full_bleed|centered"
        }}
    ]
}}
```

## 중요 원칙
1. 텍스트 최소화, 비주얼 중심
2. 시대/시장 변화를 선언하는 메시지
3. 다크 배경으로 몰입감 조성
4. 마지막에 표지 슬라이드 포함
"""

        max_tokens = get_settings().llm_max_tokens_default
        teaser_data = self._call_llm_and_extract_json(
            system_prompt, user_message, max_tokens=max_tokens
        )
        teaser_data = self._normalize_json_keys(teaser_data, TEASER_KEY_ALIASES)

        slides = self._parse_slides(teaser_data.get("slides", []))
        if not slides and teaser_data.get("main_slogan"):
            main_slogan = teaser_data.get("main_slogan", project_name)
            slides = [SlideContent(slide_type=SlideType.TEASER, title=main_slogan)]

        return TeaserContent(
            main_slogan=teaser_data.get("main_slogan", project_name),
            sub_message=teaser_data.get("sub_message"),
            visual_concept=teaser_data.get("visual_concept", "모던하고 임팩트 있는 디자인"),
            key_visuals=teaser_data.get("key_visuals"),
            slides=slides,
        )

    async def _generate_phase_with_raw(
        self,
        phase_num: int,
        rfp_analysis: RFPAnalysis,
        company_data: Dict,
        project_name: str,
        client_name: str,
        proposal_type: ProposalType,
        weight: float,
        win_themes: Optional[List[Dict[str, Any]]] = None,
    ) -> tuple:
        """Phase 콘텐츠 생성 + 원본 JSON 반환 (Win Theme 추출용). JSON 실패 시 1회 재생성."""
        # content_guidelines를 Phase system 앞에 붙여 품질·형식 준수 유도
        guidelines = self._load_prompt("content_guidelines")
        system_prompt = self._load_prompt(self.PHASE_PROMPTS[phase_num])
        if not system_prompt:
            system_prompt = self._get_phase_system_prompt(phase_num)
        if (guidelines or "").strip():
            system_prompt = (guidelines or "").strip() + "\n\n---\n\n" + system_prompt

        user_message = self._build_phase_user_message(
            phase_num, rfp_analysis, company_data,
            project_name, client_name, proposal_type, weight, win_themes
        )

        type_config = get_config(ConfigProposalType(proposal_type.value))
        phase_config = type_config.phases.get(phase_num)
        min_slides = phase_config.min_slides if phase_config else 3

        # Phase별 토큰 상한: Phase 4는 16384, Phase 2·3·5·6·7은 12288 이상으로 상세 응답 유도
        default_tokens = get_settings().llm_max_tokens_default
        if phase_num == 4:
            max_tokens = max(default_tokens, 16384)
        elif phase_num in (2, 3, 5, 6, 7):
            max_tokens = max(default_tokens, 12288)
        else:
            max_tokens = default_tokens

        # LLM 호출 + JSON 추출 (실패 시 .env LLM_JSON_RETRY_COUNT 만큼 재시도)
        slides_data = self._call_llm_and_extract_json(
            system_prompt, user_message, max_tokens=max_tokens
        )
        slides_data = self._normalize_json_keys(slides_data, PHASE_KEY_ALIASES)
        slides = self._parse_slides(slides_data.get("slides", []))

        # JSON 성공했지만 slides 없음 시 1회 재생성
        retry_count = 0
        if not slides_data or not slides_data.get("slides") or len(slides) == 0:
            logger.warning("Phase {}: slides 없음, 1회 재생성 시도", phase_num)
            slides_data = self._call_llm_and_extract_json(
                system_prompt, user_message, max_tokens=max_tokens
            )
            slides_data = self._normalize_json_keys(slides_data or {}, PHASE_KEY_ALIASES)
            slides = self._parse_slides(slides_data.get("slides", []))
            retry_count = 1

        # Self-Refinement: min_slides 미달이면 2차 재생성 1회 (고도화 방안)
        if 0 < len(slides) < min_slides and retry_count < 2:
            logger.warning(
                "Phase {}: 슬라이드 {}장 < min_slides {}, 2차 재생성 시도",
                phase_num, len(slides), min_slides,
            )
            slides_data = self._call_llm_and_extract_json(
                system_prompt, user_message, max_tokens=max_tokens
            )
            slides_data = self._normalize_json_keys(slides_data or {}, PHASE_KEY_ALIASES)
            new_slides = self._parse_slides(slides_data.get("slides", []))
            if len(new_slides) >= len(slides):
                slides = new_slides
            retry_count = 2

        if not slides:
            slides = [SlideContent(slide_type=SlideType.CONTENT, title=PHASE_TITLES[phase_num])]

        if len(slides) < min_slides:
            logger.warning(
                "Phase {} ({}): min_slides={} but generated {} slides. Consider increasing LLM_MAX_TOKENS or checking prompt.",
                phase_num, PHASE_TITLES.get(phase_num, ""), min_slides, len(slides),
            )

        phase_content = PhaseContent(
            phase_number=phase_num,
            phase_title=PHASE_TITLES[phase_num],
            phase_subtitle=self.PHASE_SUBTITLES[phase_num],
            win_theme=slides_data.get("win_theme_key"),
            slides=slides,
        )
        return phase_content, slides_data

    async def _generate_phase(
        self,
        phase_num: int,
        rfp_analysis: RFPAnalysis,
        company_data: Dict,
        project_name: str,
        client_name: str,
        proposal_type: ProposalType,
        weight: float,
        win_themes: Optional[List[Dict[str, Any]]] = None,
    ) -> PhaseContent:
        """개별 Phase 콘텐츠 생성"""
        phase_content, _ = await self._generate_phase_with_raw(
            phase_num, rfp_analysis, company_data,
            project_name, client_name, proposal_type, weight, win_themes
        )
        return phase_content

    def _build_phase_user_message(
        self,
        phase_num: int,
        rfp_analysis: RFPAnalysis,
        company_data: Dict,
        project_name: str,
        client_name: str,
        proposal_type: ProposalType,
        weight: float,
        win_themes: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Phase별 user_message 구성 (v3.6 통합)"""

        # 프로젝트 유형별 슬라이드 수 결정
        type_config = get_config(ConfigProposalType(proposal_type.value))
        phase_config = type_config.phases.get(phase_num)
        min_slides = phase_config.min_slides if phase_config else 3
        max_slides = phase_config.max_slides if phase_config else 10
        special_focus = phase_config.special_focus if phase_config else []

        # v3.6: 평가 기준 전략 섹션
        eval_strategy_section = ""
        eval_strategy = getattr(rfp_analysis, 'evaluation_strategy', None)
        if eval_strategy and isinstance(eval_strategy, dict):
            high_items = eval_strategy.get('high_weight_items', [])
            if high_items:
                items_text = "\n".join([
                    f"  - 배점 {item.get('weight', '?')}%: \"{item.get('item', '?')}\" → {item.get('proposal_emphasis', '')}"
                    for item in high_items[:5]
                ])
                eval_strategy_section = f"""
## 평가 기준 정렬 (배점 높은 항목 우선 대응)
{items_text}
→ 배점이 높은 항목에 특히 강조하여 작성하세요.
"""

        # v3.6: Pain Point 섹션
        pain_point_section = ""
        pain_points = getattr(rfp_analysis, 'pain_points', [])
        if pain_points:
            points_text = "\n".join([f"  - {pp}" for pp in pain_points[:5]])
            pain_point_section = f"""
## 발주처 핵심 Pain Point (이 고민을 해결하는 방향으로 작성)
{points_text}
"""

        # v3.6: Win Theme 컨텍스트 섹션
        win_theme_section = ""
        if win_themes and phase_num >= 2:
            wt_lines = []
            for i, wt in enumerate(win_themes[:3], 1):
                name = wt.get('name', f'Win Theme {i}')
                desc = wt.get('description', '')
                wt_lines.append(f"  {i}. {name}: {desc}")
            win_theme_section = f"""
## Win Theme (제안서 전체 일관성 유지 — 반드시 반영)
{chr(10).join(wt_lines)}
→ 이 Phase의 콘텐츠가 위 Win Theme과 연결되도록 작성하세요.
"""

        # RFP 요약 블록 (품질 개선: LLM이 핵심을 놓치지 않도록 상단에 요약 제공)
        reqs = getattr(rfp_analysis, "key_requirements", []) or getattr(rfp_analysis, "functional_requirements", [])
        req_lines = []
        for r in (reqs[:5] if isinstance(reqs, list) else []):
            text = r.get("requirement", str(r)) if isinstance(r, dict) else getattr(r, "requirement", str(r))
            req_lines.append(f"  - {text}")
        eval_items = []
        eval_strategy = getattr(rfp_analysis, "evaluation_strategy", None) or {}
        if isinstance(eval_strategy, dict) and eval_strategy.get("high_weight_items"):
            for item in eval_strategy["high_weight_items"][:5]:
                eval_items.append(f"  - 배점 {item.get('weight', '?')}%: {item.get('item', item)}")
        if not eval_items and getattr(rfp_analysis, "evaluation_criteria", None):
            for c in (rfp_analysis.evaluation_criteria or [])[:5]:
                w = c.get("weight", "") if isinstance(c, dict) else getattr(c, "weight", "")
                it = c.get("item", c) if isinstance(c, dict) else getattr(c, "item", c)
                eval_items.append(f"  - {w}%: {it}")
        rfp_summary = f"""
## RFP 요약 (작성 시 반드시 반영)
- 프로젝트 개요: {getattr(rfp_analysis, 'project_overview', '') or ''}
- 핵심 요구사항 (상위 5개):
{chr(10).join(req_lines) if req_lines else '  (없음)'}
- 고배점 평가 항목:
{chr(10).join(eval_items) if eval_items else '  (없음)'}
"""

        # KPI 스키마 (v3.6: calculation_basis 추가)
        kpi_schema = '''"kpis": [
                {{"metric": "지표명", "target": "목표값", "baseline": "현재값", "improvement": "개선폭", "calculation_basis": "산출 근거 (어떻게 이 목표를 도출했는지)", "data_source": "데이터 출처"}}
            ],'''

        user_message = f"""
프로젝트명: {project_name}
발주처: {client_name}
제안서 유형: {proposal_type.value}
Phase 비중: {weight * 100:.0f}%
{rfp_summary}

## RFP 분석 결과 (상세)
{json.dumps(rfp_analysis.model_dump(), ensure_ascii=False, indent=2)[:10000]}

## 회사 정보
{json.dumps(company_data, ensure_ascii=False, indent=2)[:4000]}
{pain_point_section}{eval_strategy_section}{win_theme_section}
## 요청사항
Phase {phase_num}: {PHASE_TITLES[phase_num]}의 슬라이드 콘텐츠를 생성해주세요.
- **최소 {min_slides}장 이상** 슬라이드를 생성해야 하며, 1~2장만 내는 응답은 사용하지 않습니다.
- 슬라이드 수: {min_slides}~{max_slides}장
- 목적: {self.PHASE_SUBTITLES[phase_num]}
{f'- 특별 강조 요소: {", ".join(special_focus)}' if special_focus else ''}

## ★ 분량·상세도 (필수 — 한두 줄만 쓰지 마세요)
- 제안서로 실제 사용할 수 있도록 **각 슬라이드마다 충분한 분량**으로 작성하세요.
- content/두괴 슬라이드: bullets는 **최소 3~5개 이상**, 각 항목은 한 문장 이상의 구체적 설명으로 채우세요.
- 테이블: rows를 3행 이상, 의미 있는 데이터로 채우세요. 헤더만 있는 빈 테이블 금지.
- key_message, subtitle, description 등은 한두 단어가 아닌 **문장 단위**로 작성하세요.
- 모델에 관계없이 위 기준을 지키면 제안서 품질이 보장됩니다.

다음 JSON 형식으로 응답해주세요:

```json
{{
    "slides": [
        {{
            "slide_type": "section_divider|content|two_column|three_column|table|chart|timeline|org_chart|comparison|key_message|content_example|channel_strategy|campaign|budget",
            "title": "슬라이드 제목 (★ Action Title: 인사이트/결론을 담은 제목)",
            "subtitle": "부제목 (선택)",
            "bullets": [
                {{"text": "내용", "level": 0, "emphasis": false, "icon": "check"}}
            ],
            "table": {{
                "headers": ["헤더1", "헤더2"],
                "rows": [["데이터1", "데이터2"]],
                "style": "default|dark|accent"
            }},
            "timeline": [
                {{"phase": "Phase 1", "title": "착수", "duration": "4주", "milestones": ["요구분석"]}}
            ],
            {kpi_schema}
            "competitor_comparison": [
                {{"criteria": "기준", "our_strength": "우리", "competitor": "경쟁사"}}
            ],
            "content_examples": [
                {{
                    "platform": "instagram",
                    "content_type": "feed",
                    "title": "콘텐츠 제목",
                    "description": "설명",
                    "visual_description": "비주얼 설명",
                    "copy_example": "카피 예시",
                    "hashtags": ["해시태그1", "해시태그2"]
                }}
            ],
            "campaign": {{
                "campaign_name": "캠페인명",
                "concept": "컨셉",
                "period": "기간",
                "objectives": ["목표1"],
                "target": "타겟",
                "channels": ["채널1"],
                "key_activities": ["활동1"],
                "expected_results": ["예상결과1"]
            }},
            "key_message": "핵심 메시지",
            "layout_hint": "full_bleed|centered|left_heavy|grid",
            "visual_style": "dark|light|gradient|accent"
        }}
    ]
}}
```

{self._get_phase_specific_guide(phase_num, proposal_type)}

## 중요 원칙
1. **분량**: 한두 줄만 쓰지 말고, 슬라이드당 불릿 3~5개 이상·구체적 문장으로 채우세요.
2. 모든 약속은 숫자로 표현 (정량화)
3. key_message를 적극 활용하여 핵심 전달
4. 경쟁사 대비 차별점 명시
5. 테이블과 차트를 활용한 시각화 (테이블은 3행 이상)
6. 마케팅/PR의 경우 실제 콘텐츠 예시 포함

## ★ 필수: Action Title (인사이트 기반 제목)
모든 슬라이드 title 필드에 Action Title을 사용하세요.
❌ "시장 환경 분석", "타겟 분석", "채널 전략" (Topic Title — 사용 금지)
✅ "숏폼 트렌드가 만드는 새로운 기회", "MZ세대, 하루 55분 SNS 사용" (Action Title)
규칙: 결론/인사이트를 제목에 담고, 가능하면 숫자를 포함하세요.
피해야 할 표현: "~~에 대하여", "~~의 현황", "~~의 방안", "~~의 필요성", "~~의 개요"

## ★ 설득 구조: C-E-I (Claim → Evidence → Impact)
각 슬라이드는 다음 구조를 따르세요:
- Claim (주장): Action Title에 핵심 주장 반영
- Evidence (근거): 데이터, 실적, 사례로 뒷받침
- Impact (영향): 발주처에 미치는 가치/효과
"""
        return user_message

    def _normalize_chart(self, raw: Optional[Dict]) -> Optional[ChartData]:
        """LLM이 type/labels/datasets 등으로 반환해도 ChartData로 변환"""
        if not raw or not isinstance(raw, dict):
            return None
        try:
            chart_type = raw.get("chart_type") or raw.get("type") or "bar"
            title = raw.get("title") or ""
            data = raw.get("data")
            if data is None:
                data = {k: v for k, v in raw.items() if k not in ("chart_type", "type", "title", "colors", "show_values", "show_legend")}
            if not isinstance(data, dict):
                data = {}
            return ChartData(
                chart_type=str(chart_type),
                title=str(title),
                data=data,
                colors=raw.get("colors"),
                show_values=raw.get("show_values", True),
                show_legend=raw.get("show_legend", True),
            )
        except Exception as e:
            logger.debug("chart 정규화 실패: {}", e)
            return None

    def _normalize_timeline(self, raw: Optional[List]) -> Optional[List[TimelineItem]]:
        """타임라인 항목에 title 등 필수 필드 보완"""
        if not raw or not isinstance(raw, list):
            return None
        out = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            try:
                out.append(TimelineItem(
                    phase=item.get("phase", ""),
                    title=item.get("title") or item.get("phase") or "",
                    duration=item.get("duration", ""),
                    description=item.get("description"),
                    milestones=item.get("milestones"),
                    deliverables=item.get("deliverables"),
                    color=item.get("color"),
                ))
            except Exception as e:
                logger.debug("timeline 항목 스킵: {}", e)
        return out if out else None

    def _normalize_table(self, raw: Optional[Dict]) -> Optional[Dict]:
        """LLM이 반환한 테이블(셀에 숫자 등)을 headers/rows 모두 str로 정규화"""
        if not raw or not isinstance(raw, dict):
            return None
        headers = raw.get("headers")
        rows = raw.get("rows")
        if headers is None and rows is None:
            return None
        try:
            out_headers = [str(h) for h in (headers or [])]
            out_rows = []
            for row in (rows or []):
                if isinstance(row, (list, tuple)):
                    out_rows.append([str(c) for c in row])
                else:
                    out_rows.append([])
            return {
                "headers": out_headers,
                "rows": out_rows,
                "highlight_rows": raw.get("highlight_rows"),
                "highlight_cols": raw.get("highlight_cols"),
                "column_widths": raw.get("column_widths"),
                "caption": raw.get("caption"),
                "style": raw.get("style", "default"),
            }
        except Exception as e:
            logger.debug("table 정규화 실패: {}", e)
            return None

    def _normalize_org_chart(self, raw: Optional[Dict]) -> Optional[OrgChartNode]:
        """LLM이 { root: { name, role, children } } 형태로 반환해도 OrgChartNode로 변환"""
        if not raw or not isinstance(raw, dict):
            return None
        node = raw.get("root") if "root" in raw else raw
        if not isinstance(node, dict):
            return None
        try:
            def to_node(n: Dict) -> OrgChartNode:
                children = None
                if n.get("children"):
                    children = [to_node(c) for c in n["children"] if isinstance(c, dict)]
                return OrgChartNode(
                    name=n.get("name", ""),
                    role=n.get("role", ""),
                    expertise=n.get("expertise"),
                    children=children,
                )
            return to_node(node)
        except Exception as e:
            logger.debug("org_chart 정규화 실패: {}", e)
            return None

    def _parse_slides(self, slides_data: List[Dict]) -> List[SlideContent]:
        """슬라이드 데이터 파싱 (모델별 키 차이 정규화 포함)"""
        slides = []

        for slide_data in slides_data:
            try:
                slide_data = dict(slide_data)
                self._normalize_json_keys(slide_data, SLIDE_KEY_ALIASES)
                slide_type_str = slide_data.get("slide_type", "content")
                try:
                    slide_type = SlideType(slide_type_str)
                except ValueError:
                    slide_type = SlideType.CONTENT

                # bullets 파싱
                bullets = self._parse_bullets(slide_data.get("bullets"))

                # KPIs 파싱 (SlideContent.kpis는 List[KPIItem]만 허용 → 항상 str로 정규화 후 KPIItem 생성)
                kpis = None
                if slide_data.get("kpis"):
                    kpis = []
                    for k in slide_data["kpis"]:
                        try:
                            if isinstance(k, dict):
                                kpis.append(KPIItem(
                                    metric=str(k.get("metric", "") or ""),
                                    target=str(k.get("target", "") or ""),
                                    baseline=str(k["baseline"]) if k.get("baseline") is not None else None,
                                    improvement=str(k["improvement"]) if k.get("improvement") is not None else None,
                                ))
                            else:
                                # KPIWithBasis 등 모델 인스턴스 → KPIItem으로 변환 (숫자 → str)
                                bl = getattr(k, "baseline", None)
                                im = getattr(k, "improvement", None)
                                kpis.append(KPIItem(
                                    metric=str(getattr(k, "metric", "") or ""),
                                    target=str(getattr(k, "target", "") or ""),
                                    baseline=str(bl) if bl is not None else None,
                                    improvement=str(im) if im is not None else None,
                                ))
                        except Exception as e:
                            logger.debug("KPI 항목 스킵: {}", e)
                            continue

                # Competitor Comparisons 파싱
                competitor_comparison = None
                if slide_data.get("competitor_comparison") or slide_data.get("comparisons"):
                    comparisons = slide_data.get("competitor_comparison") or slide_data.get("comparisons")
                    competitor_comparison = [
                        CompetitorComparison(
                            criteria=c.get("criteria", ""),
                            our_strength=c.get("our_strength", ""),
                            competitor=c.get("competitor", ""),
                        )
                        for c in comparisons
                    ]

                # Content Examples 파싱 (마케팅/PR용)
                content_examples = None
                if slide_data.get("content_examples"):
                    content_examples = [
                        ContentExample(
                            platform=ce.get("platform", ""),
                            content_type=ce.get("content_type", ""),
                            title=ce.get("title", ""),
                            description=ce.get("description", ""),
                            visual_description=ce.get("visual_description"),
                            copy_example=ce.get("copy_example"),
                            hashtags=ce.get("hashtags"),
                            kpi_target=ce.get("kpi_target"),
                        )
                        for ce in slide_data["content_examples"]
                    ]

                # Campaign 파싱
                campaign = None
                if slide_data.get("campaign"):
                    cp = slide_data["campaign"]
                    campaign = CampaignPlan(
                        campaign_name=cp.get("campaign_name", ""),
                        concept=cp.get("concept", ""),
                        period=cp.get("period", ""),
                        objectives=cp.get("objectives", []),
                        target=cp.get("target", ""),
                        channels=cp.get("channels", []),
                        key_activities=cp.get("key_activities", []),
                        expected_results=cp.get("expected_results", []),
                    )

                # 차트/타임라인/조직도/테이블 정규화 (LLM이 다른 형식으로 반환하는 경우 대응)
                chart = self._normalize_chart(slide_data.get("chart"))
                timeline = self._normalize_timeline(slide_data.get("timeline"))
                org_chart = self._normalize_org_chart(slide_data.get("org_chart"))
                table = self._normalize_table(slide_data.get("table"))

                slide = SlideContent(
                    slide_type=slide_type,
                    title=slide_data.get("title", ""),
                    subtitle=slide_data.get("subtitle"),
                    bullets=bullets,
                    table=table,
                    chart=chart,
                    timeline=timeline,
                    org_chart=org_chart,
                    left_content=self._parse_bullets(slide_data.get("left_content")),
                    right_content=self._parse_bullets(slide_data.get("right_content")),
                    center_content=self._parse_bullets(slide_data.get("center_content")),
                    left_title=slide_data.get("left_title"),
                    right_title=slide_data.get("right_title"),
                    center_title=slide_data.get("center_title"),
                    key_message=slide_data.get("key_message"),
                    notes=slide_data.get("notes"),
                    kpis=kpis,
                    competitor_comparison=competitor_comparison,
                    content_examples=content_examples,
                    campaign=campaign,
                    layout_hint=slide_data.get("layout_hint"),
                    visual_style=slide_data.get("visual_style"),
                    accent_color=slide_data.get("accent_color"),
                )
                slides.append(slide)

            except Exception as e:
                logger.warning(f"슬라이드 파싱 실패: {e}")
                continue

        return slides

    def _parse_bullets(self, bullets_data: Optional[List]) -> Optional[List[BulletPoint]]:
        """불릿 데이터 파싱"""
        if not bullets_data:
            return None
        return [
            BulletPoint(
                text=b.get("text", ""),
                level=b.get("level", 0),
                emphasis=b.get("emphasis", False),
                icon=b.get("icon"),
            )
            for b in bullets_data
        ]

    def _extract_win_themes(self, phase1_raw: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Phase 1 응답에서 Win Theme 추출 (v3.6). 여러 키/형식 폴백."""
        # 1) 최상위 win_themes
        win_themes = phase1_raw.get("win_themes") or phase1_raw.get("winThemes")
        if win_themes and isinstance(win_themes, list) and len(win_themes) > 0:
            return win_themes

        # 2) slides 내 첫 슬라이드나 summary 슬라이드에서 themes 추출
        slides = phase1_raw.get("slides", [])
        if isinstance(slides, list):
            for slide in slides[:3]:
                if not isinstance(slide, dict):
                    continue
                for key in ("win_themes", "winThemes", "themes", "key_themes"):
                    val = slide.get(key)
                    if val and isinstance(val, list) and len(val) > 0:
                        return val
                # 슬라이드 제목이 Win Theme 관련이면 bullets를 theme 후보로
                title = (slide.get("title") or "").lower()
                if "win" in title or "theme" in title or "핵심" in title:
                    bullets = slide.get("bullets", [])
                    if bullets and isinstance(bullets, list):
                        themes = []
                        for b in bullets[:3]:
                            if isinstance(b, dict) and b.get("text"):
                                themes.append({"name": b["text"][:50], "description": b.get("text", "")})
                            elif isinstance(b, str):
                                themes.append({"name": b[:50], "description": b})
                        if themes:
                            return themes

        # 3) summary_win_themes 등 변형 키
        for key in ("summary_win_themes", "key_win_themes", "themes"):
            val = phase1_raw.get(key)
            if val and isinstance(val, list) and len(val) > 0:
                return val

        logger.debug("Phase 1 응답에서 win_themes 배열을 찾지 못함. RFP 후보 또는 기본값 사용.")
        return []

    def _build_win_theme_models(self, win_themes: List[Dict[str, Any]]) -> Optional[List[WinTheme]]:
        """Win Theme dict 리스트를 WinTheme 모델 리스트로 변환 (v3.6)"""
        if not win_themes:
            return None
        models = []
        for wt in win_themes[:4]:
            try:
                models.append(WinTheme(
                    name=wt.get("name", ""),
                    description=wt.get("description", ""),
                    evidence=wt.get("evidence", []),
                    related_phases=wt.get("related_phases", []),
                ))
            except Exception as e:
                logger.warning(f"Win Theme 모델 변환 실패: {e}")
                continue
        return models if models else None

    def _extract_key_messages(
        self,
        teaser: Optional[TeaserContent],
        phase1: Optional[PhaseContent]
    ):
        """티저와 Phase 1에서 핵심 메시지 추출"""
        one_sentence_pitch = None
        key_differentiators = []
        slogan = None

        # 티저에서 슬로건 추출
        if teaser:
            slogan = teaser.main_slogan
            if teaser.sub_message:
                one_sentence_pitch = teaser.sub_message

        # Phase 1에서 추가 정보 추출
        if phase1 and phase1.slides:
            for slide in phase1.slides:
                if slide.key_message and not one_sentence_pitch:
                    one_sentence_pitch = slide.key_message
                if slide.bullets:
                    for bullet in slide.bullets[:3]:
                        if bullet.emphasis:
                            key_differentiators.append(bullet.text)
                if slide.kpis:
                    for kpi in slide.kpis[:3]:
                        if kpi.metric and kpi.target:
                            key_differentiators.append(f"{kpi.metric}: {kpi.target}")

        return one_sentence_pitch, key_differentiators[:3], slogan

    def _determine_proposal_type(
        self,
        explicit_type: Optional[str],
        rfp_analysis: RFPAnalysis
    ) -> ProposalType:
        """제안서 유형 판단 (v3.6: RFP project_type 우선 사용)"""
        if explicit_type:
            try:
                return ProposalType(explicit_type)
            except ValueError:
                pass

        # v3.6: RFP 분석에서 추출된 project_type 사용
        rfp_project_type = getattr(rfp_analysis, 'project_type', None)
        if rfp_project_type and rfp_project_type != "general":
            try:
                return ProposalType(rfp_project_type)
            except ValueError:
                pass

        # RFP 내용 기반 자동 판단 (폴백)
        overview = rfp_analysis.project_overview.lower()
        keywords_map = {
            ProposalType.MARKETING_PR: [
                "소셜미디어", "sns", "마케팅", "홍보", "브랜딩", "채널운영",
                "인스타그램", "유튜브", "페이스북", "콘텐츠", "캠페인"
            ],
            ProposalType.EVENT: [
                "행사", "이벤트", "축제", "페스티벌", "마라톤", "대회",
                "컨퍼런스", "전시회", "박람회"
            ],
            ProposalType.PUBLIC: ["공공", "교육", "운영", "위탁", "용역", "정부", "지자체"],
            ProposalType.IT_SYSTEM: [
                "시스템", "플랫폼", "개발", "구축", "it", "소프트웨어",
                "앱", "웹", "데이터베이스"
            ],
            ProposalType.CONSULTING: ["컨설팅", "자문", "진단", "분석", "전략수립"],
        }

        for proposal_type, keywords in keywords_map.items():
            if any(kw in overview for kw in keywords):
                return proposal_type

        return ProposalType.GENERAL

    def _get_phase_system_prompt(self, phase_num: int) -> str:
        """Phase별 기본 시스템 프롬프트"""
        base_prompt = """당신은 경쟁 입찰에서 승리하는 제안서를 작성하는 전문가입니다.
Modern 제안서 스타일을 참고하여 설득력 있는 슬라이드를 생성합니다.

## Impact-8 Framework
이 제안서는 Impact-8 Framework를 따릅니다:
- Phase 0: HOOK (티저) - 임팩트 있는 오프닝
- Phase 1: SUMMARY - 5분 핵심 요약
- Phase 2: INSIGHT - 시장/문제 분석
- Phase 3: CONCEPT & STRATEGY - 전략/차별화
- Phase 4: ACTION PLAN - 상세 실행계획 (★핵심, 40% 비중)
- Phase 5: MANAGEMENT - 운영/품질
- Phase 6: WHY US - 수행역량
- Phase 7: INVESTMENT & ROI - 비용/효과

## 핵심 설득 원칙
1. **분량·상세도**: 한두 줄만 쓰지 말 것. 슬라이드당 불릿 3~5개 이상, 구체적 문장으로 채워 제안서로 사용 가능한 수준으로 작성.
2. **숫자로 말하기**: 모든 약속은 정량화 ("향상" → "40% 향상")
3. **Pain → Solution**: 문제 제시 → 해결책 → 증거 순서
4. **Why Us 명확화**: 경쟁사 대비 차별점 강조
5. **시각화 우선**: 텍스트 < 표 < 차트 (테이블은 3행 이상)
6. **RFP 키워드 반복**: 발주처 용어 그대로 사용
7. **콘텐츠 예시 포함**: 마케팅/PR의 경우 실제 예시 필수

## 응답 규칙
- 반드시 유효한 JSON 형식으로 응답
- 각 슬라이드에 key_message 적극 활용
- 표와 비교 데이터 활용
"""
        return base_prompt

    def _get_phase_specific_guide(self, phase_num: int, proposal_type: ProposalType) -> str:
        """Phase별 추가 가이드"""
        is_marketing = proposal_type == ProposalType.MARKETING_PR

        guides = {
            1: """
## Phase 1: SUMMARY 가이드
- 목차/Agenda 슬라이드 포함
- 한 문장 제안 + 슬로건
- 3가지 핵심 KPI (숫자로)
- Why Us - 3가지 차별점
- 투자 대비 ROI 요약
""",
            2: f"""
## Phase 2: INSIGHT 가이드
- 시장/트렌드 분석 (데이터 포함)
{"- 소비자 행동 변화, 기술 트렌드 (AI, 숏폼 등)" if is_marketing else ""}
- RFP 요구사항 대응표 (table)
- 핵심 문제/기회 3가지로 압축
- As-Is vs To-Be 비교
""",
            3: f"""
## Phase 3: CONCEPT & STRATEGY 가이드
- 기억에 남는 슬로건/컨셉
- 전략 프레임워크 시각화
{"- 채널별 역할 정의 (Instagram, YouTube 등)" if is_marketing else ""}
- 경쟁사 비교표 (competitor_comparison 필드)
- 성공 증거/사례
""",
            4: f"""
## Phase 4: ACTION PLAN 가이드 (★가장 중요, 40% 비중)
- 연간/분기별 로드맵
{"- 채널별 상세 전략 (Instagram, YouTube 등)" if is_marketing else "- Phase별 상세 계획"}
{"- 캠페인 상세 기획 (campaign 필드)" if is_marketing else "- 주요 태스크 및 산출물"}
{"- 실제 콘텐츠 예시 (content_examples 필드) - 비주얼, 카피 포함" if is_marketing else ""}
{"- 인플루언서/협업 전략" if is_marketing else "- 품질 관리 계획"}
{"- 광고/미디어 전략" if is_marketing else "- 리스크 관리"}
- 예산 계획 (table)

{'''### 콘텐츠 예시 작성 가이드 (마케팅/PR)
content_examples 필드를 사용하여:
- platform: "instagram", "youtube", "facebook" 등
- content_type: "feed", "story", "reel", "shorts" 등
- visual_description: 비주얼 컨셉 상세 설명
- copy_example: 실제 포스팅 문구 예시
- hashtags: 해시태그 전략
''' if is_marketing else ''}
""",
            5: """
## Phase 5: MANAGEMENT 가이드
- 수행 조직도 (org_chart)
- 핵심 인력 프로필 (table)
- 콘텐츠 검수/품질 관리 프로세스
- 퍼포먼스 리포팅 체계
- 커뮤니케이션/보고 체계
- 이슈 에스컬레이션 (table)
""",
            6: """
## Phase 6: WHY US 가이드
- 회사 핵심 역량 3가지
- 유사 수행 실적 5개 이상 (정량 성과 필수)
- 대표 케이스 스터디 2-3건
- 고객 추천사 (있는 경우)
- 인증/수상 내역
""",
            7: """
## Phase 7: INVESTMENT & ROI 가이드
- 투자 비용 총괄표 (table)
- 항목별 상세 비용
- 정량적 기대효과 (kpis 필드)
- ROI 분석
- 정성적 기대효과
- Next Step + 연락처
""",
        }
        return guides.get(phase_num, "")
