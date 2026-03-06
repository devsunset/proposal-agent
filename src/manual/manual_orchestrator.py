"""
수동 모드 오케스트레이터 (Manual Mode Orchestrator)

LLM API 호출 없이 파일 기반으로 제안서 생성.
각 단계마다 Gemini 질의용 프롬프트 파일을 생성하고,
사용자가 응답을 붙여넣은 후 continue 명령으로 다음 단계를 진행합니다.

단계 매핑:
  Step 1  → RFP 분석
  Step 2  → Phase 0: HOOK (티저)
  Step 3  → Phase 1: SUMMARY
  Step 4  → Phase 2: INSIGHT
  Step 5  → Phase 3: CONCEPT
  Step 6  → Phase 4: ACTION PLAN
  Step 7  → Phase 5: MANAGEMENT
  Step 8  → Phase 6: WHY US
  Step 9  → Phase 7: INVESTMENT
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..parsers import get_parser_for_path
from ..agents.rfp_analyzer import RFPAnalyzer, RFP_KEY_ALIASES
from ..agents.content_generator import ContentGenerator, TEASER_KEY_ALIASES, PHASE_KEY_ALIASES
from ..schemas.proposal_schema import (
    PhaseContent,
    ProposalContent,
    ProposalType,
    SlideContent,
    SlideType,
    TeaserContent,
    WinTheme,
    PHASE_TITLES,
    get_phase_weights,
)
from ..schemas.rfp_schema import RFPAnalysis
from ..utils.logger import get_logger
from config.settings import get_settings
from config.proposal_types import get_config, ProposalType as ConfigProposalType

logger = get_logger("manual_orchestrator")

TOTAL_STEPS = 9
RUN_ID_FMT = "%Y%m%d_%H%M%S"
LATEST_RUN_FILE = "latest_run.txt"


def resolve_manual_run_dir(base_dir: Path) -> Path:
    """
    수동 모드 기준 폴더(manual_req_res)를 넘기면, 실제 실행 폴더(run_YYYYMMDD_HHMMSS)로 해석.
    - base_dir 안에 state.json 이 있으면 base_dir 자체가 run 폴더.
    - 없으면 base_dir/latest_run.txt 를 읽어 base_dir/run_YYYYMMDD_HHMMSS 반환.
    """
    base_dir = Path(base_dir)
    if (base_dir / "state.json").exists():
        return base_dir
    latest = base_dir / LATEST_RUN_FILE
    if latest.exists():
        run_name = latest.read_text(encoding="utf-8").strip()
        if run_name:
            return base_dir / run_name
    return base_dir


def create_run_dir(base_dir: Path) -> Path:
    """실행 시점 기준 run_YYYYMMDD_HHMMSS 폴더 생성 후 경로 반환."""
    base_dir = Path(base_dir)
    base_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now().strftime(RUN_ID_FMT)
    run_dir = base_dir / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def find_run_by_rfp_path(rfp_path: Path, base_dir: Path = Path("manual_req_res")) -> Optional[Path]:
    """
    해당 RFP 파일로 이미 생성된 수동 모드 run 폴더가 있으면 그 경로 반환, 없으면 None.
    state.json 의 rfp_path 와 절대 경로로 비교.
    """
    rfp_path = Path(rfp_path).resolve()
    base_dir = Path(base_dir)
    if not base_dir.is_dir():
        return None
    for d in sorted(base_dir.iterdir(), reverse=True):
        if not d.is_dir() or not d.name.startswith("run_"):
            continue
        state_file = d / "state.json"
        if not state_file.exists():
            continue
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
            saved_rfp = state.get("rfp_path")
            if not saved_rfp:
                continue
            if Path(saved_rfp).resolve() == rfp_path:
                return d
        except Exception:
            continue
    return None

STEP_DESCRIPTIONS = {
    1: "RFP 분석",
    2: "Phase 0: HOOK (티저)",
    3: "Phase 1: SUMMARY (핵심 요약)",
    4: "Phase 2: INSIGHT (시장 환경 분석)",
    5: "Phase 3: CONCEPT (핵심 전략)",
    6: "Phase 4: ACTION PLAN (실행 계획)",
    7: "Phase 5: MANAGEMENT (운영 관리)",
    8: "Phase 6: WHY US (수행 역량)",
    9: "Phase 7: INVESTMENT (투자 & ROI)",
}

# 단계별 요청/응답 파일명에 쓰는 라벨 (예: 1_step_RFPAnalyzer_request.txt)
STEP_FILE_LABELS = {
    1: "RFPAnalyzer",
    2: "HOOK",
    3: "SUMMARY",
    4: "INSIGHT",
    5: "CONCEPT",
    6: "ACTION_PLAN",
    7: "MANAGEMENT",
    8: "WHY_US",
    9: "INVESTMENT",
}


def _step_to_phase(step: int) -> int:
    """step -> phase_num (step 2 = phase 0, step 9 = phase 7)"""
    return step - 2


def _step_request_file_name(step: int) -> str:
    """단계별 요청 파일명 (예: 1_step_RFPAnalyzer_request.txt)"""
    label = STEP_FILE_LABELS.get(step, f"step{step}")
    return f"{step}_step_{label}_request.txt"


def _step_response_file_name(step: int) -> str:
    """단계별 응답 파일명 (예: 1_step_RFPAnalyzer_response.txt)"""
    label = STEP_FILE_LABELS.get(step, f"step{step}")
    return f"{step}_step_{label}_response.txt"


class ManualOrchestrator:
    """
    수동 모드 오케스트레이터.

    generate --manual 로 시작하고, continue 명령으로 단계별로 진행합니다.
    기존 ContentGenerator / RFPAnalyzer 의 프롬프트 빌딩 로직을 재활용합니다.
    """

    def __init__(self, manual_dir: Path = Path("manual_req_res")):
        self.manual_dir = Path(manual_dir)
        self.manual_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.manual_dir / "state.json"
        self._content_gen, self._rfp_analyzer = self._create_agents()

    @staticmethod
    def _create_agents():
        """
        프롬프트 빌딩·파싱용 에이전트 인스턴스 생성.
        LLM_PROVIDER가 claude/groq이고 API 키가 없어도 초기화될 수 있도록
        Settings를 임시로 gemini 모드로 패치한 후 복원합니다.
        """
        import config.settings as _sm
        from config.settings import Settings

        orig = _sm._settings
        try:
            cur = _sm.get_settings()
            manual_settings = Settings.model_construct(
                **{
                    **cur.model_dump(),
                    "llm_provider": "gemini",
                    "gemini_api_key": "manual_mode_no_api_call",
                }
            )
            _sm._settings = manual_settings
            content_gen = ContentGenerator(api_key="manual_mode_no_api_call")
            rfp_analyzer = RFPAnalyzer(api_key="manual_mode_no_api_call")
        finally:
            _sm._settings = orig
        return content_gen, rfp_analyzer

    def start(
        self,
        rfp_path: Path,
        project_name: str = "",
        client_name: str = "",
        proposal_type: Optional[str] = None,
        company_data_path: Optional[Path] = None,
        output_dir: Path = Path("output"),
    ) -> None:
        """수동 모드 시작. RFP 파싱 후 Step 1 요청 파일 생성."""
        logger.info("수동 모드 시작: {}", rfp_path)
        parsed_rfp = self._parse_rfp(rfp_path)
        logger.info("RFP 파싱 완료: {}자", len(parsed_rfp.get("raw_text", "")))

        company_data: Dict = {}
        if company_data_path and company_data_path.exists():
            try:
                company_data = json.loads(company_data_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("회사 데이터 로드 실패: {}", e)

        system_prompt, user_message = self._build_rfp_analysis_prompt(parsed_rfp)
        self._write_request_file(1, system_prompt, user_message)

        state: Dict[str, Any] = {
            "version": 1,
            "rfp_path": str(rfp_path),
            "project_name": project_name,
            "client_name": client_name,
            "proposal_type": proposal_type,
            "company_data_path": str(company_data_path) if company_data_path else "",
            "company_data": company_data,
            "output_dir": str(output_dir),
            "current_step": 1,
            "total_steps": TOTAL_STEPS,
            "rfp_analysis": None,
            "phase_contents": {},
            "win_themes": [],
            "cross_phase_summaries": [],
            "started_at": datetime.now().isoformat(),
        }
        self._save_state(state)
        # 이번 실행 run 폴더를 latest_run.txt 에 기록 (continue/status 기본 해석용)
        base = self.manual_dir.parent
        (base / LATEST_RUN_FILE).write_text(self.manual_dir.name, encoding="utf-8")
        logger.info("Step 1 요청 파일 생성: {}", self.manual_dir / _step_request_file_name(1))

    def continue_step(self) -> bool:
        """현재 단계 응답 처리 및 다음 단계 요청 파일 생성. 완료 시 True."""
        if not self.state_file.exists():
            raise FileNotFoundError(
                "상태 파일이 없습니다. 먼저 'python main.py generate <rfp> --manual' 을 실행하세요."
            )
        state = self._load_state()
        step = state["current_step"]
        if step > TOTAL_STEPS:
            # PPTX 생성이 이전에 실패했을 수 있음 → 파일 없으면 재생성
            pptx_path = state.get("pptx_output_path")
            if pptx_path and Path(pptx_path).exists():
                logger.info("이미 모든 단계가 완료되었고 PPTX가 생성되어 있습니다.")
                return True
            logger.info("모든 단계 완료. PPTX가 없어 다시 생성합니다.")
            return self._generate_pptx(state)

        response_path = self.manual_dir / _step_response_file_name(step)
        if not response_path.exists():
            raise FileNotFoundError(
                f"응답 파일이 없습니다: {response_path}\n"
                f"Gemini 응답을 {response_path} 에 저장한 후 다시 실행하세요."
            )
        response_text = response_path.read_text(encoding="utf-8").strip()
        if not response_text:
            raise ValueError(
                f"응답 파일이 비어 있습니다: {response_path}\n"
                "Gemini 응답 JSON을 붙여넣은 후 다시 실행하세요."
            )
        json_data = self._extract_json(response_text)
        if not json_data:
            raise ValueError(
                f"응답 파일에서 유효한 JSON을 찾을 수 없습니다: {response_path}\n"
                "Gemini가 JSON 형식으로 응답했는지 확인하세요."
            )
        logger.info("Step {}/{} 응답 처리 중: {}", step, TOTAL_STEPS, STEP_DESCRIPTIONS.get(step, ""))

        if step == 1:
            self._process_step1(json_data, state)
        elif 2 <= step <= TOTAL_STEPS:
            phase_num = _step_to_phase(step)
            done = self._process_phase_step(step, phase_num, json_data, state)
            if done:
                return True
        self._save_state(state)
        return False

    def _process_step1(self, json_data: Dict, state: Dict) -> None:
        """Step 1: RFP 분석 응답 처리 → Step 2 요청 파일 생성"""
        json_data = self._normalize_keys(json_data, RFP_KEY_ALIASES)
        json_data.setdefault("project_name", state.get("project_name") or "프로젝트명 미확인")
        json_data.setdefault("client_name", state.get("client_name") or "발주처 미확인")
        json_data.setdefault("project_overview", "")

        rfp_analysis = RFPAnalysis(**json_data)
        state["rfp_analysis"] = rfp_analysis.model_dump()
        if not state.get("project_name"):
            state["project_name"] = rfp_analysis.project_name
        if not state.get("client_name"):
            state["client_name"] = rfp_analysis.client_name
        if not state.get("proposal_type"):
            state["proposal_type"] = getattr(rfp_analysis, "project_type", None)
        logger.info("RFP 분석 완료: {} ({})", rfp_analysis.project_name, rfp_analysis.client_name)

        system_prompt, user_message = self._build_phase0_prompt(rfp_analysis, state)
        self._write_request_file(2, system_prompt, user_message)
        state["current_step"] = 2

    def _process_phase_step(
        self, step: int, phase_num: int, json_data: Dict, state: Dict
    ) -> bool:
        """Step 2~9: Phase 콘텐츠 응답 처리. 완료 시 PPTX 생성 후 True."""
        rfp_analysis = RFPAnalysis(**state["rfp_analysis"])

        if phase_num == 0:
            json_data = self._normalize_keys(json_data, TEASER_KEY_ALIASES)
            teaser = self._parse_teaser(json_data, state)
            state["phase_contents"]["0"] = {"type": "teaser", "data": teaser.model_dump()}
            logger.info("Phase 0 (HOOK) 파싱 완료: {}장", len(teaser.slides))
        else:
            json_data = self._normalize_keys(json_data, PHASE_KEY_ALIASES)
            slides = self._content_gen._parse_slides(json_data.get("slides", []))
            if not slides:
                logger.warning("Phase {} 슬라이드가 없습니다. 응답을 확인하세요.", phase_num)
                slides = [SlideContent(slide_type=SlideType.CONTENT, title=PHASE_TITLES[phase_num])]
            phase_content = PhaseContent(
                phase_number=phase_num,
                phase_title=PHASE_TITLES[phase_num],
                phase_subtitle=self._content_gen.PHASE_SUBTITLES[phase_num],
                win_theme=json_data.get("win_theme_key"),
                slides=slides,
            )
            state["phase_contents"][str(phase_num)] = {"type": "phase", "data": phase_content.model_dump()}
            logger.info("Phase {} ({}) 파싱 완료: {}장", phase_num, PHASE_TITLES[phase_num], len(slides))

            if phase_num == 1:
                win_themes = self._content_gen._extract_win_themes(json_data)
                if not win_themes:
                    candidates = getattr(rfp_analysis, "win_theme_candidates", []) or []
                    win_themes = [
                        c.model_dump() if hasattr(c, "model_dump") else (c if isinstance(c, dict) else {})
                        for c in candidates
                    ]
                state["win_themes"] = win_themes
                if win_themes:
                    logger.info("Win Theme {}개 확정", len(win_themes))
            summary = self._content_gen._extract_phase_summary(phase_content)
            state["cross_phase_summaries"].append(summary)

        if step < TOTAL_STEPS:
            next_phase_num = phase_num + 1
            system_prompt, user_message = self._build_phase_prompt(next_phase_num, rfp_analysis, state)
            self._write_request_file(step + 1, system_prompt, user_message)
            state["current_step"] = step + 1
            return False
        state["current_step"] = TOTAL_STEPS + 1
        self._save_state(state)
        return self._generate_pptx(state)

    def get_status(self) -> Dict[str, Any]:
        """현재 진행 상태 반환. done=True는 9단계 완료 후 PPTX 파일이 실제로 있을 때만."""
        if not self.state_file.exists():
            return {"started": False}
        state = self._load_state()
        step = state["current_step"]
        completed = step - 1
        pptx_path = state.get("pptx_output_path")
        all_steps_done = step > TOTAL_STEPS
        pptx_exists = bool(pptx_path and Path(pptx_path).exists())
        status = {
            "started": True,
            "current_step": step,
            "total_steps": TOTAL_STEPS,
            "completed_steps": completed,
            "done": all_steps_done and pptx_exists,
            "project_name": state.get("project_name", ""),
            "client_name": state.get("client_name", ""),
            "steps": [],
        }
        for s in range(1, TOTAL_STEPS + 1):
            req_path = self.manual_dir / _step_request_file_name(s)
            res_path = self.manual_dir / _step_response_file_name(s)
            step_info = {
                "step": s,
                "description": STEP_DESCRIPTIONS.get(s, ""),
                "request_ready": req_path.exists(),
                "response_ready": res_path.exists() and res_path.stat().st_size > 0,
                "completed": s < step,
                "current": s == step,
            }
            status["steps"].append(step_info)
        return status

    def _build_rfp_analysis_prompt(self, parsed_rfp: Dict) -> Tuple[str, str]:
        """Step 1: RFP 분석 프롬프트 빌드"""
        system_prompt = self._rfp_analyzer._load_prompt("rfp_analysis")
        if not system_prompt:
            system_prompt = self._rfp_analyzer._get_default_system_prompt()
        settings = get_settings()
        raw_text_full = parsed_rfp.get("raw_text", "")
        tables = parsed_rfp.get("tables", [])

        if settings.enable_rfp_chunking and len(raw_text_full) > 10000:
            from ..parsers.chunker import RFPChunker
            chunker = RFPChunker()
            raw_text = chunker.build_analysis_context(
                raw_text_full, tables=tables, max_chars=settings.rfp_chunk_max_chars,
            )
        else:
            raw_text = self._rfp_analyzer._truncate_text(raw_text_full, 25000)
        tables_json = json.dumps(tables[:10], ensure_ascii=False, indent=2)[:5000]
        user_message = f"""
중요: 응답은 반드시 유효한 JSON만 포함해야 합니다. 마크다운(##, ###), 목록(-), 설명 없이, 오직 ```json 으로 감싼 코드 블록 한 개만 출력하세요.

다음 RFP(제안요청서) 문서를 분석해주세요.

## 문서 텍스트
{raw_text}

## 테이블 데이터
{tables_json}

위 내용을 분석하여 다음 JSON 형식으로 응답해주세요:

```json
{{
    "project_name": "프로젝트명",
    "client_name": "발주처명",
    "project_overview": "프로젝트 개요 (2-3문장)",
    "project_type": "marketing_pr / event / it_system / public / consulting / general 중 택1",
    "key_requirements": [{{"category": "기능/비기능/기술/관리", "requirement": "요구사항", "priority": "필수/선택"}}],
    "technical_requirements": [{{"category": "기술", "requirement": "기술 요구사항", "priority": "필수/선택"}}],
    "evaluation_criteria": [{{"category": "분야", "item": "평가 항목", "weight": 배점}}],
    "deliverables": [{{"name": "산출물명", "phase": "단계", "description": "설명"}}],
    "timeline": {{"total_duration": "전체 기간", "phases": [{{"name": "단계명", "duration": "기간"}}]}},
    "budget": {{"total_budget": "예산 (있는 경우)", "notes": "예산 관련 참고사항"}},
    "key_success_factors": ["핵심 성공 요인 1", "핵심 성공 요인 2"],
    "potential_risks": ["리스크 1", "리스크 2"],
    "winning_strategy": "수주를 위한 전략 제안",
    "differentiation_points": ["차별화 포인트 1", "차별화 포인트 2"],
    "pain_points": ["발주처 핵심 고민 1", "발주처 핵심 고민 2", "발주처 핵심 고민 3"],
    "hidden_needs": ["숨겨진 니즈 1", "숨겨진 니즈 2"],
    "evaluation_strategy": {{"high_weight_items": [{{"item": "배점 높은 항목", "weight": 30, "proposal_emphasis": "강조할 내용"}}], "emphasis_mapping": {{}}}},
    "win_theme_candidates": [{{"name": "Win Theme 1", "rationale": "이유", "rfp_alignment": "연결 요구사항"}}, {{"name": "Win Theme 2", "rationale": "이유", "rfp_alignment": "연결"}}, {{"name": "Win Theme 3", "rationale": "이유", "rfp_alignment": "연결"}}],
    "competitive_landscape": "예상 경쟁 환경 분석"
}}
```
"""
        return system_prompt, user_message

    def _build_phase0_prompt(self, rfp_analysis: RFPAnalysis, state: Dict) -> Tuple[str, str]:
        """Step 2: Phase 0 (HOOK 티저) 프롬프트 빌드"""
        system_prompt = self._content_gen._load_prompt(self._content_gen.PHASE_PROMPTS[0])
        if not system_prompt:
            system_prompt = self._content_gen._get_phase_system_prompt(0)
        proposal_type_str = state.get("proposal_type") or getattr(rfp_analysis, "project_type", "general") or "general"
        try:
            proposal_type = ProposalType(proposal_type_str)
        except ValueError:
            proposal_type = ProposalType.GENERAL
        type_config = get_config(ConfigProposalType(proposal_type.value))
        phase_config = type_config.phases.get(0)
        min_slides = phase_config.min_slides if phase_config else 3
        max_slides = phase_config.max_slides if phase_config else 10
        project_name = state.get("project_name") or rfp_analysis.project_name
        client_name = state.get("client_name") or rfp_analysis.client_name
        user_message = f"""
응답은 반드시 유효한 JSON만 출력해 주세요. 마크다운(##, 목록, 설명) 없이 ```json 코드 블록 한 개만 출력해 주세요.

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
        {{"slide_type": "teaser", "title": "슬라이드 제목", "subtitle": "부제목", "key_message": "핵심 메시지", "visual_style": "dark|gradient_dark|light", "layout_hint": "full_bleed|centered"}}
    ]
}}
```

## 중요 원칙
1. 텍스트 최소화, 비주얼 중심
2. 시대/시장 변화를 선언하는 메시지
3. 다크 배경으로 몰입감 조성
4. 마지막에 표지 슬라이드 포함
"""
        return system_prompt, user_message

    def _build_phase_prompt(
        self, phase_num: int, rfp_analysis: RFPAnalysis, state: Dict
    ) -> Tuple[str, str]:
        """Step 3~9: Phase 1~7 프롬프트 빌드"""
        guidelines = self._content_gen._load_prompt("content_guidelines")
        system_prompt = self._content_gen._load_prompt(self._content_gen.PHASE_PROMPTS[phase_num])
        if not system_prompt:
            system_prompt = self._content_gen._get_phase_system_prompt(phase_num)
        if (guidelines or "").strip():
            system_prompt = (guidelines or "").strip() + "\n\n---\n\n" + system_prompt
        proposal_type_str = state.get("proposal_type") or getattr(rfp_analysis, "project_type", "general") or "general"
        try:
            proposal_type = ProposalType(proposal_type_str)
        except ValueError:
            proposal_type = ProposalType.GENERAL
        weights = get_phase_weights(proposal_type)
        weight = weights.get(phase_num, 0.1)
        company_data = state.get("company_data", {})
        win_themes = state.get("win_themes", [])
        cross_phase_summaries = state.get("cross_phase_summaries", [])
        user_message = self._content_gen._build_phase_user_message(
            phase_num=phase_num,
            rfp_analysis=rfp_analysis,
            company_data=company_data,
            project_name=state.get("project_name") or rfp_analysis.project_name,
            client_name=state.get("client_name") or rfp_analysis.client_name,
            proposal_type=proposal_type,
            weight=weight,
            win_themes=win_themes if win_themes else None,
            cross_phase_summaries=cross_phase_summaries if cross_phase_summaries else None,
        )
        return system_prompt, user_message

    def _write_request_file(self, step: int, system_prompt: str, user_message: str) -> None:
        """단계별 요청 파일 작성"""
        description = STEP_DESCRIPTIONS.get(step, f"Step {step}")
        response_file = _step_response_file_name(step)
        header = f"""=====================================
제안서 자동 생성 에이전트 - 수동 모드
Step {step}/{TOTAL_STEPS}: {description}
=====================================

[사용법]
1. 아래 [시스템 프롬프트]와 [사용자 메시지]를 Google Gemini 또는 ChatGPT 등에 입력하세요.
   - Google Gemini: https://gemini.google.com/
   - ChatGPT: https://chat.openai.com/
   - [시스템 프롬프트] → 각 사이트의 시스템/지시 입력란에 입력
   - [사용자 메시지]  → 메인 입력란에 입력

2. LLM 응답(JSON 전체)을 복사하여 아래 파일에 붙여넣으세요:
   → {self.manual_dir.as_posix()}/{response_file}

3. 다음 명령 실행:
   python main.py continue

=====================================
[시스템 프롬프트 (System Instructions)]
=====================================
{system_prompt}

=====================================
[사용자 메시지 (User Message)]
=====================================
{user_message}
"""
        req_path = self.manual_dir / _step_request_file_name(step)
        req_path.write_text(header, encoding="utf-8")
        logger.info("요청 파일 생성: {}", req_path)

    def _extract_json(self, text: str) -> Dict[str, Any]:
        """응답 텍스트에서 JSON 추출"""
        return self._rfp_analyzer._extract_json(text)

    def _normalize_keys(self, data: Dict, aliases: Dict[str, str]) -> Dict:
        """camelCase → snake_case 키 정규화"""
        return self._rfp_analyzer._normalize_json_keys(data, aliases)

    def _parse_rfp(self, rfp_path: Path) -> Dict[str, Any]:
        """RFP 파일 파싱"""
        parser = get_parser_for_path(rfp_path)
        return parser.parse(rfp_path)

    def _parse_teaser(self, json_data: Dict, state: Dict) -> TeaserContent:
        """Phase 0 응답 JSON → TeaserContent"""
        project_name = state.get("project_name", "프로젝트")
        slides = self._content_gen._parse_slides(json_data.get("slides", []))
        if not slides and json_data.get("main_slogan"):
            slides = [SlideContent(slide_type=SlideType.TEASER, title=json_data["main_slogan"])]
        return TeaserContent(
            main_slogan=json_data.get("main_slogan", project_name),
            sub_message=json_data.get("sub_message"),
            visual_concept=json_data.get("visual_concept", "모던하고 임팩트 있는 디자인"),
            key_visuals=json_data.get("key_visuals"),
            slides=slides,
        )

    def _generate_pptx(self, state: Dict) -> bool:
        """수집된 모든 데이터로 PPTX 생성"""
        from ..orchestrators.pptx_orchestrator import PPTXOrchestrator
        from ..utils.path_utils import safe_output_path

        logger.info("PPTX 생성 시작...")
        try:
            content = self._build_proposal_content(state)
        except Exception as e:
            logger.error("ProposalContent 구성 실패: {}", e)
            raise
        output_dir = Path(state.get("output_dir", "output"))
        output_dir.mkdir(parents=True, exist_ok=True)
        _now = datetime.now()
        _ts = _now.strftime("%Y%m%d%H%M%S") + f"{_now.microsecond // 1000:03d}"
        output_path = safe_output_path(
            output_dir,
            content.project_name or "제안서",
            suffix=f"_{_ts}",
            extension=".pptx",
        )
        pptx_orchestrator = PPTXOrchestrator()
        pptx_orchestrator.execute(
            content=content,
            output_path=output_path,
            template_name="",
        )
        state["pptx_output_path"] = str(output_path.resolve())
        self._save_state(state)
        logger.info("PPTX 생성 완료: {}", output_path)
        print(f"\n제안서가 생성되었습니다: {output_path}")
        return True

    def _build_proposal_content(self, state: Dict) -> ProposalContent:
        """state.json 데이터로 ProposalContent 재구성"""
        rfp_data = state.get("rfp_analysis") or {}
        project_name = state.get("project_name") or rfp_data.get("project_name", "제안서")
        client_name = state.get("client_name") or rfp_data.get("client_name", "")
        proposal_type_str = state.get("proposal_type") or rfp_data.get("project_type", "general") or "general"
        try:
            proposal_type = ProposalType(proposal_type_str)
        except ValueError:
            proposal_type = ProposalType.GENERAL
        phase_contents_raw = state.get("phase_contents", {})

        teaser: Optional[TeaserContent] = None
        if "0" in phase_contents_raw:
            entry = phase_contents_raw["0"]
            if entry.get("type") == "teaser":
                try:
                    teaser = TeaserContent(**entry["data"])
                except Exception as e:
                    logger.warning("TeaserContent 복원 실패: {}", e)

        phases: List[PhaseContent] = []
        for phase_num in range(1, 8):
            key = str(phase_num)
            if key in phase_contents_raw:
                entry = phase_contents_raw[key]
                if entry.get("type") == "phase":
                    try:
                        phases.append(PhaseContent(**entry["data"]))
                    except Exception as e:
                        logger.warning("Phase {} 복원 실패: {}", phase_num, e)
                        phases.append(PhaseContent(
                            phase_number=phase_num,
                            phase_title=PHASE_TITLES.get(phase_num, f"Phase {phase_num}"),
                            phase_subtitle=self._content_gen.PHASE_SUBTITLES.get(phase_num, ""),
                            slides=[],
                        ))
            else:
                phases.append(PhaseContent(
                    phase_number=phase_num,
                    phase_title=PHASE_TITLES.get(phase_num, f"Phase {phase_num}"),
                    phase_subtitle=self._content_gen.PHASE_SUBTITLES.get(phase_num, ""),
                    slides=[],
                ))

        win_theme_models = self._content_gen._build_win_theme_models(state.get("win_themes", []))
        one_sentence_pitch, key_differentiators, slogan = self._content_gen._extract_key_messages(
            teaser, phases[0] if phases else None
        )
        company_data = state.get("company_data") or {}
        company_name = company_data.get("company_name", "[회사명]") if isinstance(company_data, dict) else "[회사명]"
        return ProposalContent(
            project_name=project_name,
            client_name=client_name,
            submission_date=datetime.now().strftime("%Y-%m-%d"),
            company_name=company_name,
            proposal_type=proposal_type,
            one_sentence_pitch=one_sentence_pitch,
            key_differentiators=key_differentiators,
            slogan=slogan,
            win_themes=win_theme_models if win_theme_models else None,
            rfp_summary=rfp_data,
            teaser=teaser,
            phases=phases,
            design_style="guide_template",
        )

    def _save_state(self, state: Dict) -> None:
        self.manual_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _load_state(self) -> Dict:
        return json.loads(self.state_file.read_text(encoding="utf-8"))
