#!/usr/bin/env python3
"""
제안서 자동 생성 에이전트 (Impact-8 Framework)

RFP 문서(PDF/DOCX/TXT/PPTX)를 입력받아 Impact-8 구조의 PPTX 제안서를 자동 생성합니다.
실제 수주 성공 제안서 분석을 기반으로 Phase 구성·비중이 설계되어 있습니다.

역할 분리:
- LLM (Claude / Gemini / Groq / Ollama): RFP 분석, 제안서 콘텐츠 생성 (.env LLM_PROVIDER)
- PPTX 레이어: ProposalContent → Modern 스타일 PPTX 변환

CLI 명령:
- generate: RFP 경로로 제안서 생성 (옵션: 프로젝트명, 발주처, 유형, 템플릿, 출력 경로, --manual 수동 모드)
- continue: 수동 모드에서 응답 파일 처리 후 다음 단계 (--manual 사용 시)
- status: 수동 모드 진행 상태 확인
- analyze: RFP 분석만 수행 (PPTX 미생성)
- setup-company: 회사 프로필 대화형 설정 (Phase 6 품질 향상)
- types: 지원 제안서 유형 목록
- templates: 사용 가능한 PPTX 템플릿 목록
- info: Impact-8 Framework 설명
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# .env를 먼저 로드해야 config.settings가 올바른 LLM_PROVIDER를 읽음
load_dotenv()

from config.settings import get_settings
from config.proposal_types import ProposalType as ConfigProposalType, get_type_display_name
from src.orchestrators.proposal_orchestrator import ProposalOrchestrator
from src.orchestrators.pptx_orchestrator import PPTXOrchestrator
from src.utils.logger import LOG_SEPARATOR, setup_logger
from src.utils.path_utils import safe_filename, safe_output_path
from src.schemas.proposal_schema import PHASE_TITLES

setup_logger()  # LOG_LEVEL 환경 변수 사용 (기본 INFO)

# 고도화: proposal_type별 기본 템플릿 (미지정 시 -T 없으면 빈 값으로 기본 디자인 사용)
# 예: {"it_system": "guide_template"} 로 지정 시 it_system 유형은 템플릿 미지정이어도 해당 템플릿 사용
DEFAULT_TEMPLATE_BY_PROPOSAL_TYPE: dict = {}


def _default_template_for_proposal_type(proposal_type_value: str) -> str:
    """
    제안서 유형에 따른 기본 템플릿명 반환.

    DEFAULT_TEMPLATE_BY_PROPOSAL_TYPE에 정의된 경우 해당 템플릿, 없으면 빈 문자열(기본 디자인).
    """
    return DEFAULT_TEMPLATE_BY_PROPOSAL_TYPE.get(proposal_type_value, "")

app = typer.Typer(
    name="proposal-agent",
    help="제안서 자동 생성 에이전트 (Impact-8 Framework)",
    add_completion=False,
)
console = Console()

# 제안서 유형 상수
# 제안서 유형 표시명은 config.proposal_types.get_type_display_name() 사용 (단일 소스)


@app.command()
def generate(
    rfp_path: Path = typer.Argument(
        ...,
        help="RFP 문서 경로 (PDF/DOCX/TXT/PPTX)",
        exists=True,
        file_okay=True,
        dir_okay=False,
    ),
    project_name: Optional[str] = typer.Option(
        None,
        "--name",
        "-n",
        help="프로젝트명 (미입력시 RFP에서 추출)",
    ),
    client_name: Optional[str] = typer.Option(
        None,
        "--client",
        "-c",
        help="발주처명 (미입력시 RFP에서 추출)",
    ),
    proposal_type: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="제안서 유형 (marketing_pr, event, it_system, public, consulting, general)",
    ),
    company_data: Path = typer.Option(
        Path("company_data/company_profile.json"),
        "--company",
        "-d",
        help="회사 정보 JSON 경로",
    ),
    output_dir: Path = typer.Option(
        Path("output"),
        "--output",
        "-o",
        help="출력 디렉토리",
    ),
    template: Optional[str] = typer.Option(
        None,
        "--template",
        "-T",
        help="템플릿 PPTX 파일명(확장자 제외). 미지정 시 템플릿 없이 기본 디자인으로 제안서 생성(권장). 지정 시 해당 .pptx 테마/레이아웃 기준으로 생성.",
    ),
    save_json: bool = typer.Option(
        False,
        "--save-json",
        help="중간 JSON 파일 저장",
    ),
    manual: bool = typer.Option(
        False,
        "--manual",
        "-m",
        help="수동 모드: LLM API 호출 없이 파일 기반으로 진행 (Gemini 수작업 질의용)",
    ),
):
    """
    RFP 문서로부터 제안서(PPTX) 자동 생성 (Impact-8 Framework)

    예시:
        python main.py generate input/rfp.pdf -n "[프로젝트명]" -c "[발주처명]" -t marketing_pr
        python main.py generate input/rfp.pdf --manual   # 수동 모드 (LLM API 없이)
    """
    # 수동 모드: LLM API 불필요, 파일 기반으로 진행
    if manual:
        _run_manual_generate(
            rfp_path=rfp_path,
            project_name=project_name or "",
            client_name=client_name or "",
            proposal_type=proposal_type,
            company_data=company_data,
            output_dir=output_dir,
            template=template,
        )
        return

    # API 키 확인 (LLM_PROVIDER에 따라 검사. ollama는 로컬이라 키 불필요)
    _settings = get_settings()
    _p = _settings.llm_provider
    if _p == "ollama":
        api_key = "ollama"  # BaseAgent에서 무시, 일관된 시그니처용
    elif _p == "claude":
        api_key = _settings.anthropic_api_key
        key_name = "ANTHROPIC_API_KEY"
        key_hint = "https://console.anthropic.com"
    elif _p == "groq":
        api_key = _settings.groq_api_key
        key_name = "GROQ_API_KEY"
        key_hint = "https://console.groq.com"
    else:
        api_key = _settings.gemini_api_key
        key_name = "GEMINI_API_KEY"
        key_hint = "https://aistudio.google.com/apikey"
    if _p != "ollama" and not api_key:
        console.print(
            Panel(
                f"[red]{key_name}가 설정되지 않았습니다.[/red]\n\n"
                f".env에 LLM_PROVIDER={_p} 로 설정된 경우 해당 API 키가 필요합니다.\n"
                f"예: {key_name}=your-api-key (발급: {key_hint})",
                title="Error",
            )
        )
        raise typer.Exit(1)

    # 유형 검증
    _valid_types = {p.value for p in ConfigProposalType}
    if proposal_type and proposal_type not in _valid_types:
        console.print(f"[red]지원하지 않는 제안서 유형: {proposal_type}[/red]")
        console.print(f"사용 가능한 유형: {', '.join(_valid_types)}")
        raise typer.Exit(1)

    # 헤더 출력 (사용 중인 LLM 표시)
    _llm_label = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini", "ollama": "Ollama (로컬)"}.get(_p, _p)
    console.print(
        Panel(
            "[bold cyan]제안서 자동 생성 에이전트[/bold cyan]\n"
            "[bold]Impact-8 Framework[/bold]\n\n"
            f"[dim]LLM: {_llm_label} (콘텐츠 생성) | [회사명]: Modern 스타일 PPTX[/dim]",
            title="Proposal Agent",
            border_style="green",
        )
    )

    console.print(f"\n[bold]입력 파일:[/bold] {rfp_path}")
    if project_name:
        console.print(f"[bold]프로젝트명:[/bold] {project_name}")
    if client_name:
        console.print(f"[bold]발주처:[/bold] {client_name}")
    if proposal_type:
        console.print(f"[bold]제안서 유형:[/bold] {get_type_display_name(proposal_type)}")
    console.print()

    # 출력 디렉토리 생성
    output_dir.mkdir(parents=True, exist_ok=True)

    # 비동기 실행 (예외는 내부에서 잡아 반환해 Windows cp949 인코딩 오류 방지)
    out = asyncio.run(
        _generate_async(
            rfp_path=rfp_path,
            project_name=project_name or "",
            client_name=client_name or "",
            proposal_type=proposal_type,
            company_data=company_data,
            output_dir=output_dir,
            template=template,
            save_json=save_json,
            api_key=api_key,
        )
    )
    if out[0] == "error":
        err = out[1]
        _s = get_settings()
        _llm = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini", "ollama": "Ollama"}.get(
            _s.llm_provider, _s.llm_provider.title()
        )
        if "429" in str(err) or "할당량" in str(err):
            msg = f"{_llm} API 할당량 초과(429). 잠시 후 재시도하거나 플랜/결제를 확인하세요."
        else:
            msg = str(err) or f"제안서 생성 실패 ({_llm} API 키, 네트워크, 로그 확인)."
        try:
            print("제안서 생성 실패:", msg)
        except Exception:
            print("Proposal generation failed. Check API key and quota.")
        raise typer.Exit(1)


async def _generate_async(
    rfp_path: Path,
    project_name: str,
    client_name: str,
    proposal_type: Optional[str],
    company_data: Path,
    output_dir: Path,
    template: str,
    save_json: bool,
    api_key: str,
):
    """비동기 제안서 생성 (Impact-8 Framework). 성공 시 ('ok', None), 실패 시 ('error', exception) 반환."""
    try:
        return await _generate_async_impl(
            rfp_path=rfp_path,
            project_name=project_name,
            client_name=client_name,
            proposal_type=proposal_type,
            company_data=company_data,
            output_dir=output_dir,
            template=template,
            save_json=save_json,
            api_key=api_key,
        )
    except Exception as e:
        return ("error", e)


async def _generate_async_impl(
    rfp_path: Path,
    project_name: str,
    client_name: str,
    proposal_type: Optional[str],
    company_data: Path,
    output_dir: Path,
    template: str,
    save_json: bool,
    api_key: str,
):
    """제안서 생성 실제 로직"""

    # Step 1: 콘텐츠 생성 (설정된 LLM)
    _llm = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini", "ollama": "Ollama"}.get(
        get_settings().llm_provider, "LLM"
    )
    console.print()
    console.print(
        Panel(
            f"[bold]{_llm}[/bold] - Impact-8",
            title="[bold]Step 1: 콘텐츠 생성[/bold]",
            border_style="cyan",
        )
    )

    proposal_orchestrator = ProposalOrchestrator(api_key=api_key)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("분석 및 콘텐츠 생성 중...", total=None)
        _last_phase = [-1]
        update_progress = _make_progress_callback(console, progress, task, _last_phase)

        submission_date = datetime.now().strftime("%Y-%m-%d")

        content = await proposal_orchestrator.execute(
            rfp_path=rfp_path,
            company_data_path=company_data if company_data.exists() else None,
            project_name=project_name,
            client_name=client_name,
            submission_date=submission_date,
            proposal_type=proposal_type,
            progress_callback=update_progress,
        )

    console.print(
        Panel("[green]✓ 완료[/green]", title="[bold]Step 1 완료[/bold]", border_style="cyan")
    )
    console.print()

    # 콘텐츠 요약 출력
    summary = proposal_orchestrator.get_proposal_summary(content)
    _print_content_summary(summary)

    # 고도화: Phase별 진단(소요시간·슬라이드 수·JSON 성공) 출력 및 저장
    diagnostics = proposal_orchestrator.get_run_diagnostics()
    if diagnostics:
        _print_run_diagnostics(diagnostics)
        try:
            import json as _json
            _ts_diag = datetime.now().strftime("%Y%m%d%H%M%S")
            _diag_path = output_dir / f"run_diagnostics_{_ts_diag}.json"
            _diag_path.write_text(_json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
            console.print(f"[dim]진단 저장: {_diag_path}[/dim]")
        except Exception:
            pass

    # 최종 프로젝트명 확정 (보안: 허용 문자·길이 제한)
    final_project_name = content.project_name or "제안서"
    safe_base = safe_filename(final_project_name)

    # 중간 JSON 저장 (옵션)
    if save_json:
        json_path = safe_output_path(output_dir, final_project_name, suffix="_content", extension=".json")
        proposal_orchestrator.save_content_json(content, json_path)
        console.print(f"[dim]JSON 저장: {json_path}[/dim]")

    # Step 2: PPTX 생성 ([회사명])
    console.print()
    console.print(
        Panel(
            "Modern 스타일",
            title="[bold]Step 2: PPTX 생성[/bold]",
            border_style="cyan",
        )
    )

    pptx_orchestrator = PPTXOrchestrator()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("PPTX 생성 중...", total=None)
        _last_phase_pptx = [-1]
        update_progress = _make_pptx_progress_callback(console, progress, task, _last_phase_pptx)

        # 유니크 파일명: 제목_접미사.pptx (접미사 = YYYYMMDDHHmmssfff)
        _now = datetime.now()
        _ts = _now.strftime("%Y%m%d%H%M%S") + f"{_now.microsecond // 1000:03d}"
        output_path = safe_output_path(
            output_dir, final_project_name, suffix=f"_{_ts}", extension=".pptx"
        )

        template_used = template if template is not None else _default_template_for_proposal_type(content.proposal_type.value)
        pptx_orchestrator.execute(
            content=content,
            output_path=output_path,
            template_name=template_used,
            progress_callback=update_progress,
        )

    console.print(
        Panel("[green]✓ 완료[/green]", title="[bold]Step 2 완료[/bold]", border_style="cyan")
    )
    console.print()

    # 결과 출력
    total_slides = summary["total_slides"]
    console.print(
        Panel(
            f"[bold green]제안서가 생성되었습니다![/bold green]\n\n"
            f"[bold]파일:[/bold] {output_path}\n"
            f"[bold]프로젝트:[/bold] {content.project_name}\n"
            f"[bold]발주처:[/bold] {content.client_name}\n"
            f"[bold]유형:[/bold] {get_type_display_name(content.proposal_type.value)}\n"
            f"[bold]슬라이드 수:[/bold] {total_slides}장\n"
            f"[bold]디자인 스타일:[/bold] {template_used if template_used else '기본(템플릿 미사용)'}",
            title="Complete",
            border_style="green",
        )
    )
    return ("ok", None)


def _make_progress_callback(console, progress, task, last_phase_ref):
    """
    Step 1(콘텐츠 생성)용. Phase 전환 시:
    1) 먼저 줄바꿈으로 Progress 라이브 라인 종료
    2) 스피너를 현재 Phase로 갱신 + refresh로 즉시 반영
    3) 해당 Phase 패널 출력 → 그 아래에는 해당 Phase 로그만 나오게 (loguru는 logger에서 선행 \\n으로 분리)
    """
    def update_progress(p):
        msg = p.get("message", "처리 중...")
        parts = msg.split(":", 1)
        if len(parts) >= 2 and parts[0].strip().startswith("Phase "):
            tok = parts[0].strip().split()
            if len(tok) == 2 and tok[1].isdigit():
                n = int(tok[1])
                if 0 <= n <= 7 and n != last_phase_ref[0]:
                    # 1) 줄바꿈으로 이전 Progress 라이브 라인 종료 → loguru가 그 줄에 붙지 않게
                    console.print()
                    # 2) 스피너를 현재 Phase로 갱신하고 즉시 리프레시 (패널 아래에 올바른 문구로 그려지게)
                    progress.update(task, description=msg, refresh=True)
                    if getattr(progress, "refresh", None):
                        progress.refresh()
                    # 3) 해당 Phase 패널 출력
                    console.print(
                        Panel(
                            "",
                            title=f"[bold]Phase {n}: {PHASE_TITLES.get(n, '')}[/bold]",
                            border_style="yellow",
                        )
                    )
                    last_phase_ref[0] = n
                    return
        progress.update(task, description=msg, refresh=True)
    return update_progress


def _make_pptx_progress_callback(console, progress, task, last_phase_ref):
    """
    Step 2(PPTX 생성)용. Phase 전환 시 줄바꿈 → 스피너 갱신(refresh) → 패널 출력.
    패널 아래에는 해당 Phase 슬라이드 생성 완료 로그만 나오게 (loguru 선행 \\n으로 분리).
    """
    PPTX_MSG = "PPTX 생성 중..."

    def update_progress(p):
        msg = p.get("message", "처리 중...")
        parts = msg.split(":", 1)
        if len(parts) >= 2 and parts[0].strip().startswith("Phase "):
            tok = parts[0].strip().split()
            if len(tok) == 2 and tok[1].isdigit():
                n = int(tok[1])
                if 0 <= n <= 7 and n != last_phase_ref[0]:
                    console.print()
                    progress.update(task, description=PPTX_MSG, refresh=True)
                    if getattr(progress, "refresh", None):
                        progress.refresh()
                    console.print(
                        Panel(
                            "",
                            title=f"[bold]Phase {n}: {PHASE_TITLES.get(n, '')}[/bold]",
                            border_style="yellow",
                        )
                    )
                    last_phase_ref[0] = n
                    return
        progress.update(task, description=msg if msg else PPTX_MSG, refresh=True)
    return update_progress


def _print_content_summary(summary: dict):
    """콘텐츠 요약 출력"""
    console.print("[bold]생성된 콘텐츠 요약:[/bold]")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Phase", style="dim")
    table.add_column("슬라이드 수", justify="right")

    if summary.get("teaser_slides", 0) > 0:
        table.add_row("Phase 0: HOOK", str(summary["teaser_slides"]))

    for phase_name, count in summary.get("phase_slides", {}).items():
        table.add_row(phase_name, str(count))

    table.add_row("[bold]총계[/bold]", f"[bold]{summary['total_slides']}[/bold]")

    console.print(table)

    if summary.get("slogan"):
        console.print(f"\n[bold]슬로건:[/bold] {summary['slogan']}")
    if summary.get("one_sentence_pitch"):
        console.print(f"[bold]핵심 제안:[/bold] {summary['one_sentence_pitch']}")


def _print_run_diagnostics(diagnostics: list):
    """Phase별 진단(소요시간·슬라이드 수·JSON 성공) 테이블 출력 (고도화: 로깅·진단)."""
    if not diagnostics:
        return
    console.print("[bold]Phase별 진단:[/bold]")
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Phase", style="dim")
    table.add_column("제목", style="dim")
    table.add_column("슬라이드", justify="right")
    table.add_column("소요(초)", justify="right")
    table.add_column("JSON", justify="center")
    for d in diagnostics:
        table.add_row(
            f"Phase {d.get('phase', '')}",
            str(d.get("phase_title", ""))[:20],
            str(d.get("slides_count", 0)),
            str(d.get("elapsed_sec", "")),
            "✓" if d.get("json_ok") else "✗",
        )
    console.print(table)


# ================================================================
# 수동 모드 (LLM API 없이 파일 기반 진행)
# ================================================================

def _run_manual_generate(
    rfp_path: Path,
    project_name: str,
    client_name: str,
    proposal_type: Optional[str],
    company_data: Path,
    output_dir: Path,
    template: Optional[str],
) -> None:
    """수동 모드: RFP 파싱 후 Step 1 요청 파일 생성"""
    from src.manual import ManualOrchestrator, _step_request_file_name, _step_response_file_name

    _valid_types = {p.value for p in ConfigProposalType}
    if proposal_type and proposal_type not in _valid_types:
        console.print(f"[red]지원하지 않는 제안서 유형: {proposal_type}[/red]")
        console.print(f"사용 가능한 유형: {', '.join(_valid_types)}")
        raise typer.Exit(1)

    console.print(
        Panel(
            "[bold cyan]제안서 자동 생성 에이전트 - 수동 모드[/bold cyan]\n"
            "[bold]Impact-8 Framework[/bold]\n\n"
            "[dim]LLM API 없이 Gemini 수작업 질의로 진행합니다.[/dim]\n"
            "[dim]총 9단계: RFP 분석 1회 + Phase 0~7 생성 8회[/dim]",
            title="Proposal Agent (Manual Mode)",
            border_style="yellow",
        )
    )
    console.print(f"\n[bold]입력 파일:[/bold] {rfp_path}")
    if project_name:
        console.print(f"[bold]프로젝트명:[/bold] {project_name}")
    if client_name:
        console.print(f"[bold]발주처:[/bold] {client_name}")

    orchestrator = ManualOrchestrator(manual_dir=Path("manual"))
    try:
        orchestrator.start(
            rfp_path=rfp_path,
            project_name=project_name,
            client_name=client_name,
            proposal_type=proposal_type,
            company_data_path=company_data if company_data.exists() else None,
            output_dir=output_dir,
            template=template,
        )
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1)

    req_f, res_f = _step_request_file_name(1), _step_response_file_name(1)
    console.print(
        Panel(
            "[bold green]Step 1/9 준비 완료![/bold green]\n\n"
            "[bold]다음 단계:[/bold]\n"
            f"1. [cyan]manual/{req_f}[/cyan] 파일을 열어 프롬프트를 확인하세요.\n"
            "2. [시스템 프롬프트]와 [사용자 메시지]를 Google AI Studio에 입력하세요.\n"
            "   → https://aistudio.google.com/\n"
            f"3. Gemini 응답(JSON)을 [cyan]manual/{res_f}[/cyan] 에 붙여넣으세요.\n"
            "4. [bold]python main.py continue[/bold] 를 실행하세요.",
            title="수동 모드 시작",
            border_style="yellow",
        )
    )


@app.command(name="continue")
def manual_continue(
    manual_dir: Path = typer.Option(
        Path("manual"),
        "--manual-dir",
        help="수동 모드 작업 폴더 (기본: manual/)",
    ),
) -> None:
    """
    수동 모드: 현재 단계 응답 처리 및 다음 단계 요청 파일 생성

    응답 파일(N_step_Phase명_response.txt)을 작성한 후 이 명령을 실행하세요.

    예시:
        python main.py continue
    """
    from src.manual import ManualOrchestrator, _step_request_file_name, _step_response_file_name

    orchestrator = ManualOrchestrator(manual_dir=manual_dir)
    try:
        status = orchestrator.get_status()
    except Exception as e:
        console.print(f"[red]상태 확인 실패: {e}[/red]")
        raise typer.Exit(1)

    if not status.get("started"):
        console.print(
            Panel(
                "[red]수동 모드가 시작되지 않았습니다.[/red]\n\n"
                "먼저 다음 명령을 실행하세요:\n"
                "  [bold]python main.py generate <rfp파일> --manual[/bold]",
                title="오류",
                border_style="red",
            )
        )
        raise typer.Exit(1)

    if status.get("done"):
        console.print(
            Panel(
                "[green]모든 단계가 완료되었습니다. PPTX가 이미 생성되었습니다.[/green]",
                border_style="green",
            )
        )
        return

    current_step = status["current_step"]
    total_steps = status["total_steps"]
    console.print(
        Panel(
            f"[bold]Step {current_step}/{total_steps} 처리 중...[/bold]",
            border_style="cyan",
        )
    )

    try:
        done = orchestrator.continue_step()
    except FileNotFoundError as e:
        console.print(Panel(f"[red]파일 없음:[/red]\n{e}", title="오류", border_style="red"))
        raise typer.Exit(1)
    except ValueError as e:
        console.print(Panel(f"[red]응답 파싱 오류:[/red]\n{e}", title="오류", border_style="red"))
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1)

    if done:
        console.print(
            Panel(
                "[bold green]모든 단계 완료! PPTX가 생성되었습니다.[/bold green]\n\n"
                "[bold]출력 디렉토리:[/bold] output/",
                title="Complete",
                border_style="green",
            )
        )
    else:
        new_status = orchestrator.get_status()
        next_step = new_status["current_step"]
        next_desc = new_status["steps"][next_step - 1]["description"] if next_step <= total_steps else ""
        next_req, next_res = _step_request_file_name(next_step), _step_response_file_name(next_step)
        console.print(
            Panel(
                f"[green]Step {current_step} 완료![/green]\n\n"
                f"[bold]다음 단계:[/bold] Step {next_step}/{total_steps} - {next_desc}\n\n"
                f"1. [cyan]manual/{next_req}[/cyan] 파일을 열어 프롬프트를 확인하세요.\n"
                f"2. Gemini에 입력하고 응답을 [cyan]manual/{next_res}[/cyan] 에 붙여넣으세요.\n"
                "3. [bold]python main.py continue[/bold] 를 다시 실행하세요.",
                title=f"Step {current_step} 완료",
                border_style="yellow",
            )
        )


@app.command()
def status(
    manual_dir: Path = typer.Option(
        Path("manual"),
        "--manual-dir",
        help="수동 모드 작업 폴더 (기본: manual/)",
    ),
) -> None:
    """
    수동 모드 진행 상태 확인

    예시:
        python main.py status
    """
    from src.manual import ManualOrchestrator, _step_response_file_name

    orchestrator = ManualOrchestrator(manual_dir=manual_dir)
    try:
        s = orchestrator.get_status()
    except Exception as e:
        console.print(f"[red]상태 확인 실패: {e}[/red]")
        raise typer.Exit(1)

    if not s.get("started"):
        console.print(
            Panel(
                "[yellow]수동 모드가 시작되지 않았습니다.[/yellow]\n\n"
                "시작하려면:\n"
                "  [bold]python main.py generate <rfp파일> --manual[/bold]",
                border_style="yellow",
            )
        )
        return

    project = s.get("project_name") or ""
    client = s.get("client_name") or ""
    current = s["current_step"]
    total = s["total_steps"]
    if s.get("done"):
        status_text = "[bold green]완료[/bold green]"
    else:
        status_text = f"[bold cyan]진행 중 (Step {current}/{total})[/bold cyan]"
    console.print(
        Panel(
            f"[bold]프로젝트:[/bold] {project}\n"
            f"[bold]발주처:[/bold] {client}\n"
            f"[bold]상태:[/bold] {status_text}",
            title="수동 모드 상태",
            border_style="cyan",
        )
    )
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Step", justify="center", style="dim")
    table.add_column("내용")
    table.add_column("요청파일", justify="center")
    table.add_column("응답파일", justify="center")
    table.add_column("상태", justify="center")
    for step_info in s["steps"]:
        sn = step_info["step"]
        req = "O" if step_info["request_ready"] else "-"
        res = "O" if step_info["response_ready"] else "-"
        if step_info["completed"]:
            st = "완료"
        elif step_info["current"]:
            st = "대기중"
        else:
            st = "미진행"
        table.add_row(str(sn), step_info["description"], req, res, st)
    try:
        console.print(table)
    except Exception:
        print(f"\n{'Step':<5} {'내용':<40} {'요청':^6} {'응답':^6} {'상태':^8}")
        print("-" * 70)
        for step_info in s["steps"]:
            sn, req = step_info["step"], "O" if step_info["request_ready"] else "-"
            res = "O" if step_info["response_ready"] else "-"
            st = "완료" if step_info["completed"] else ("대기중" if step_info["current"] else "미진행")
            try:
                print(f"{sn:<5} {step_info['description']:<40} {req:^6} {res:^6} {st:^8}")
            except Exception:
                print(f"{sn:<5} Step {sn:<37} {req:^6} {res:^6} {st:^8}")
    if not s.get("done") and current <= total:
        current_res = _step_response_file_name(current)
        try:
            console.print(
                f"\n[dim]현재 대기: manual/{current_res} 를 작성 후 "
                "'python main.py continue' 실행[/dim]"
            )
        except Exception:
            print(f"\n현재 대기: manual/{current_res} 를 작성 후 'python main.py continue' 실행")


@app.command()
def analyze(
    rfp_path: Path = typer.Argument(
        ...,
        help="RFP 문서 경로 (PDF/DOCX/TXT/PPTX)",
        exists=True,
    ),
):
    """
    RFP 문서 분석만 수행 (PPTX 생성 없이)
    """
    _settings = get_settings()
    _p = _settings.llm_provider
    if _p == "ollama":
        api_key = "ollama"
    elif _p == "claude":
        api_key = _settings.anthropic_api_key
        key_name = "ANTHROPIC_API_KEY"
    elif _p == "groq":
        api_key = _settings.groq_api_key
        key_name = "GROQ_API_KEY"
    else:
        api_key = _settings.gemini_api_key
        key_name = "GEMINI_API_KEY"
    if _p != "ollama" and not api_key:
        console.print(f"[red]{key_name}가 설정되지 않았습니다. .env에서 LLM_PROVIDER={_p} 에 맞는 API 키를 설정하세요.[/red]")
        raise typer.Exit(1)

    console.print(LOG_SEPARATOR)
    console.print(f"[bold]RFP 분석:[/bold] {rfp_path}\n")

    from src.parsers import get_parser_for_path
    from src.agents.rfp_analyzer import RFPAnalyzer

    # 파싱 (확장자에 따라 파서 선택 — 통합 함수 사용)
    try:
        parser = get_parser_for_path(rfp_path)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    parsed = parser.parse(rfp_path)
    console.print(f"파싱 완료: {len(parsed.get('raw_text', ''))} 문자\n")

    # 분석 (예외는 Progress 블록 안에서 잡아 반환해, Windows cp949 인코딩 오류 방지)
    async def _analyze():
        analyzer = RFPAnalyzer(api_key=api_key)
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("RFP 분석 중...", total=None)

                def update_progress(p):
                    progress.update(task, description=p.get("message", "분석 중..."))

                result = await analyzer.execute(parsed, progress_callback=update_progress)
            return ("ok", result)
        except Exception as e:
            return ("error", e)

    out = asyncio.run(_analyze())
    if out[0] == "error":
        e = out[1]
        _s = get_settings()
        _llm = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini"}.get(
            _s.llm_provider, _s.llm_provider.title()
        )
        # Windows cp949 콘솔 인코딩 오류 방지: Rich 대신 print 사용, 메시지는 ASCII/한글만
        if "429" in str(e) or "할당량" in str(e):
            msg = f"{_llm} API 할당량 초과(429). 잠시 후 재시도하거나 플랜/결제를 확인하세요."
        else:
            msg = f"{_llm} API 호출 실패. API 키와 네트워크를 확인하세요."
        try:
            print("RFP 분석 실패:", msg)
        except Exception:
            print("RFP analysis failed. Check API key and quota.")
        raise typer.Exit(1)

    result = out[1]

    # 결과 출력
    console.print(LOG_SEPARATOR)
    console.print(
        Panel(
            f"[bold]프로젝트명:[/bold] {result.project_name}\n"
            f"[bold]발주처:[/bold] {result.client_name}\n"
            f"[bold]개요:[/bold] {result.project_overview[:200]}...\n\n"
            f"[bold]핵심 요구사항:[/bold] {len(result.key_requirements)}개\n"
            f"[bold]평가 기준:[/bold] {len(result.evaluation_criteria)}개\n"
            f"[bold]산출물:[/bold] {len(result.deliverables)}개\n\n"
            f"[bold]수주 전략:[/bold]\n{result.winning_strategy or '분석 필요'}",
            title="RFP 분석 결과",
            border_style="cyan",
        )
    )


@app.command()
def types():
    """사용 가능한 제안서 유형 목록"""
    console.print("\n[bold]사용 가능한 제안서 유형 (Impact-8 Framework):[/bold]\n")

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("유형 코드", style="cyan")
    table.add_column("설명")
    table.add_column("ACTION PLAN 비중", justify="right")

    weights = {
        "marketing_pr": "40%",
        "event": "45%",
        "it_system": "35%",
        "public": "30%",
        "consulting": "30%",
        "general": "35%",
    }

    for p in ConfigProposalType:
        code, desc = p.value, get_type_display_name(p.value)
        table.add_row(code, desc, weights.get(code, "35%"))

    console.print(table)
    console.print("\n[dim]사용 예: python main.py generate rfp.pdf -t marketing_pr[/dim]")


@app.command()
def templates():
    """사용 가능한 PPTX 템플릿 목록"""
    templates_dir = get_settings().templates_dir

    console.print("\n[bold]디자인 스타일:[/bold]")
    console.print("  - [dim]템플릿 미지정 시[/dim] (기본) - 템플릿 없이 기본 디자인으로 제안서 생성 (권장)")
    console.print("  - [cyan]-T guide_template[/cyan] 등 지정 시 - 해당 .pptx 테마/레이아웃 기준으로 생성")

    if not templates_dir.exists():
        console.print("\n[yellow]templates 디렉토리가 없습니다.[/yellow]")
        return

    pptx_files = list(templates_dir.glob("*.pptx"))

    if pptx_files:
        console.print("\n[bold]커스텀 템플릿:[/bold]")
        for t in pptx_files:
            console.print(f"  - {t.stem}")


@app.command(name="setup-company")
def setup_company(
    output_path: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="저장 경로 (기본: company_data/company_profile.json)",
    ),
):
    """
    회사 프로필 대화형 설정 (Phase 6: WHY US 품질 향상)

    회사명·주요 서비스·수행 실적·핵심 인력 등을 입력하면
    company_data/company_profile.json에 저장되어 제안서 생성 시 자동으로 활용됩니다.

    예시:
        python main.py setup-company
        python main.py setup-company -o company_data/my_profile.json
    """
    from src.data.company_profiler import run_interactive_setup

    try:
        saved_path = run_interactive_setup(output_path=output_path)
        console.print(
            Panel(
                f"[bold green]회사 프로필이 저장되었습니다![/bold green]\n\n"
                f"[bold]파일:[/bold] {saved_path}\n\n"
                "이제 제안서 생성 시 Phase 6(WHY US)에 실제 역량·실적이 자동으로 반영됩니다.\n"
                "[dim]생성 시: python main.py generate rfp.pdf (--company 옵션으로 경로 지정 가능)[/dim]",
                title="Setup Company Complete",
                border_style="green",
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]취소되었습니다.[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print(f"[red]오류: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def info():
    """Impact-8 Framework 정보"""
    console.print(
        Panel(
            """[bold cyan]Impact-8 Framework[/bold cyan]

실제 수주 성공 제안서 분석을 기반으로 개선된 8-Phase 구조

[bold]Phase 구성:[/bold]
  Phase 0: HOOK (5%)      - 임팩트 있는 오프닝
  Phase 1: SUMMARY (5%)   - Executive Summary
  Phase 2: INSIGHT (10%)  - 시장 환경 & 문제 정의
  Phase 3: CONCEPT (12%)  - 핵심 컨셉 & 전략
  Phase 4: ACTION (40%)   - ★ 상세 실행 계획 (핵심!)
  Phase 5: MANAGEMENT (10%) - 운영 & 품질 관리
  Phase 6: WHY US (12%)   - 수행 역량 & 실적
  Phase 7: INVESTMENT (6%) - 투자 & ROI

[bold]핵심 특징:[/bold]
  • 티저(HOOK) 섹션으로 강력한 첫인상
  • ACTION PLAN이 전체의 40% (Modern 스타일)
  • 실제 콘텐츠 예시 포함 (마케팅/PR)
  • 프로젝트 유형별 가변 구조
  • Modern 스타일 디자인 시스템

[bold]디자인 스타일:[/bold]
  • 컬러: #002C5F (다크 블루), #00AAD2 (스카이블루)
  • 폰트: Pretendard
  • 레이아웃: 16:9 (1920x1080)
""",
            title="About Impact-8 Framework",
            border_style="cyan",
        )
    )


if __name__ == "__main__":
    app()
