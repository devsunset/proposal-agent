"""
제안서 생성 오케스트레이터 (v3.0 - Impact-8 Framework)

전체 워크플로우를 조율합니다: RFP 파싱 → 회사 데이터 로드 → RFP 분석(LLM) → 제안서 콘텐츠 생성(LLM).
LLM은 .env의 LLM_PROVIDER에 따라 Claude/Gemini/Groq 중 하나가 사용됩니다.
"""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..parsers import get_parser_for_path
from ..agents.rfp_analyzer import RFPAnalyzer
from ..agents.content_generator import ContentGenerator
from ..schemas.proposal_schema import ProposalContent, ProposalType, PHASE_TITLES
from ..schemas.rfp_schema import RFPAnalysis
from ..utils.logger import get_logger
from config.settings import get_settings

logger = get_logger("proposal_orchestrator")


class ProposalOrchestrator:
    """
    제안서 콘텐츠 생성 오케스트레이터 (Impact-8 Framework).

    역할: RFP 문서 파싱 → RFP 분석(LLM) → 제안서 콘텐츠 생성(LLM) 순서로 실행하고
    ProposalContent를 반환합니다. API 키는 생성자에서 받거나 설정에서 가져옵니다.
    """

    def __init__(self, api_key: Optional[str] = None):
        settings = get_settings()
        # 선택된 LLM provider에 맞는 API 키 사용 (모델 변경 시 사이드 이펙트 방지)
        if api_key:
            self.api_key = api_key
        else:
            p = settings.llm_provider
            if p == "claude":
                self.api_key = settings.anthropic_api_key or ""
            elif p == "groq":
                self.api_key = settings.groq_api_key or ""
            else:
                self.api_key = settings.gemini_api_key or ""
        self.rfp_analyzer = RFPAnalyzer(api_key=self.api_key)
        self.content_generator = ContentGenerator(api_key=self.api_key)
        self._run_diagnostics: List[Dict[str, Any]] = []  # 고도화: Phase별 로깅·진단

    def get_run_diagnostics(self) -> List[Dict[str, Any]]:
        """
        마지막 execute() 실행 시 Phase별 진단 정보 반환.

        Returns:
            phase, phase_title, slides_count, elapsed_sec, json_ok 등을 담은 딕셔너리 목록
        """
        return list(self._run_diagnostics)

    async def execute(
        self,
        rfp_path: Path,
        company_data_path: Optional[Path] = None,
        project_name: str = "",
        client_name: str = "",
        submission_date: str = "",
        proposal_type: Optional[str] = None,
        progress_callback: Optional[Callable] = None,
    ) -> ProposalContent:
        """
        전체 제안서 콘텐츠 생성 워크플로우 실행 (Impact-8 Framework)

        Args:
            rfp_path: RFP 문서 경로
            company_data_path: 회사 정보 JSON 경로
            project_name: 프로젝트명 (미입력시 RFP에서 추출)
            client_name: 발주처명 (미입력시 RFP에서 추출)
            submission_date: 제출일
            proposal_type: 제안서 유형 (marketing_pr, event, it_system, public, consulting, general)
            progress_callback: 진행 상황 콜백

        Returns:
            ProposalContent: 생성된 제안서 콘텐츠 (Impact-8 구조)
        """
        try:
            # Step 1: 문서 파싱
            if progress_callback:
                progress_callback({
                    "phase": "parsing",
                    "step": 1,
                    "total": 4,
                    "message": "RFP 문서 파싱 중...",
                })

            parsed_rfp = self._parse_document(rfp_path)
            logger.info(f"RFP 파싱 완료: {len(parsed_rfp.get('raw_text', ''))} 문자")

            # Step 2: 회사 데이터 로드
            company_data = {}
            if company_data_path:
                company_data = self._load_company_data(company_data_path)

            # Step 3: RFP 분석 (설정된 LLM)
            _settings = get_settings()
            _llm_label = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini"}.get(
                _settings.llm_provider, _settings.llm_provider.title()
            )
            if progress_callback:
                progress_callback({
                    "phase": "analysis",
                    "step": 2,
                    "total": 4,
                    "message": f"RFP 분석 중 ({_llm_label})...",
                })

            rfp_analysis = await self.rfp_analyzer.execute(
                input_data=parsed_rfp,
                progress_callback=lambda p: progress_callback({
                    "phase": "analysis",
                    "sub_step": p["step"],
                    "sub_total": p["total"],
                    "message": p["message"],
                }) if progress_callback else None,
            )

            # 프로젝트명/발주처명 결정
            final_project_name = project_name or rfp_analysis.project_name
            final_client_name = client_name or rfp_analysis.client_name

            logger.info(f"RFP 분석 완료: {final_project_name} ({final_client_name})")

            # Step 4: 콘텐츠 생성 (설정된 LLM) - Impact-8 Framework
            if progress_callback:
                progress_callback({
                    "phase": "generation",
                    "step": 3,
                    "total": 4,
                    "message": f"제안서 콘텐츠 생성 중 ({_llm_label} - Impact-8)...",
                })

            run_diagnostics: List[Dict[str, Any]] = []
            proposal_content = await self.content_generator.execute(
                input_data={
                    "rfp_analysis": rfp_analysis,
                    "company_data": company_data,
                    "project_name": final_project_name,
                    "client_name": final_client_name,
                    "submission_date": submission_date,
                    "proposal_type": proposal_type,
                },
                progress_callback=lambda p: progress_callback({
                    "phase": "generation",
                    "sub_step": p["step"],
                    "sub_total": p["total"],
                    "message": p["message"],
                }) if progress_callback else None,
                diagnostics_out=run_diagnostics,
            )
            self._run_diagnostics = run_diagnostics

            if progress_callback:
                progress_callback({
                    "phase": "complete",
                    "step": 4,
                    "total": 4,
                    "message": "콘텐츠 생성 완료!",
                })

            # 슬라이드 수 계산
            total_slides = len(proposal_content.teaser.slides) if proposal_content.teaser else 0
            total_slides += sum(len(p.slides) for p in proposal_content.phases)

            logger.info(f"제안서 콘텐츠 생성 완료: {total_slides}장")
            return proposal_content

        except Exception as e:
            logger.error(f"제안서 생성 실패: {e}")
            raise

    def _parse_document(self, file_path: Path) -> Dict[str, Any]:
        """파일 확장자에 맞는 파서를 get_parser_for_path()로 선택한 뒤 parse() 호출."""
        parser = get_parser_for_path(file_path)
        return parser.parse(file_path)

    def _load_company_data(self, data_path: Path) -> Dict[str, Any]:
        """회사 정보 JSON 파일 로드. 없거나 파싱 실패 시 빈 딕셔너리 또는 예외."""
        if not data_path.exists():
            logger.warning(f"회사 데이터 파일 없음: {data_path}")
            return {}

        try:
            return json.loads(data_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("회사 데이터 로드 실패: %s: %s", type(e).__name__, str(e)[:200])
            raise

    def save_content_json(
        self, content: ProposalContent, output_path: Path
    ) -> None:
        """ProposalContent를 UTF-8 JSON 파일로 저장 (indent=2, ensure_ascii=False)."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            content.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info(f"콘텐츠 JSON 저장: {output_path}")

    def get_proposal_summary(self, content: ProposalContent) -> Dict[str, Any]:
        """제안서 요약(프로젝트명, 발주처, 유형, 슬로건, 슬라이드 수 등) 반환."""
        teaser_slides = len(content.teaser.slides) if content.teaser else 0
        phase_slides = {
            f"Phase {p.phase_number}: {PHASE_TITLES.get(p.phase_number, getattr(p, 'phase_title', '') or '')}": len(p.slides)
            for p in content.phases
        }
        total_slides = teaser_slides + sum(phase_slides.values())

        return {
            "project_name": content.project_name,
            "client_name": content.client_name,
            "proposal_type": content.proposal_type.value,
            "slogan": content.slogan,
            "one_sentence_pitch": content.one_sentence_pitch,
            "key_differentiators": content.key_differentiators,
            "total_slides": total_slides,
            "teaser_slides": teaser_slides,
            "phase_slides": phase_slides,
            "design_style": content.design_style,
        }
