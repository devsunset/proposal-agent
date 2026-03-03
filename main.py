#!/usr/bin/env python3
"""
입찰 제안서 자동 생성 에이전트 (v3.0 - Impact-8 Framework)

RFP 문서를 입력받아 PPTX 제안서를 자동 생성합니다.
실제 수주 성공 제안서 분석을 기반으로 개선된 구조 적용.

역할 분리:
- LLM (Claude / Gemini / Groq): RFP 분석, 콘텐츠 생성 (.env의 LLM_PROVIDER로 선택)
- [회사명]: PPTX 변환, Modern 스타일 디자인 적용
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

app = typer.Typer(
    name="proposal-agent",
    help="입찰 제안서 자동 생성 에이전트 (v3.0 - Impact-8 Framework)",
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
    template: str = typer.Option(
        "guide_template",
        "--template",
        "-T",
        help="템플릿 PPTX 파일명(확장자 제외). 미지정 시 templates 폴더에서 'guide' 포함 .pptx 자동 선택 후 해당 파일 규칙으로 생성.",
    ),
    save_json: bool = typer.Option(
        False,
        "--save-json",
        help="중간 JSON 파일 저장",
    ),
):
    """
    RFP 문서로부터 입찰 제안서(PPTX) 자동 생성 (Impact-8 Framework)

    예시:
        python main.py generate input/rfp.pdf -n "[프로젝트명]" -c "[발주처명]" -t marketing_pr
    """
    # API 키 확인 (LLM_PROVIDER에 따라 검사)
    _settings = get_settings()
    _p = _settings.llm_provider
    if _p == "claude":
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
    if not api_key:
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
    _llm_label = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini"}.get(_p, _p)
    console.print(
        Panel(
            "[bold cyan]입찰 제안서 자동 생성 에이전트[/bold cyan]\n"
            "[bold]v3.0 - Impact-8 Framework[/bold]\n\n"
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
        _llm = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini"}.get(
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
    _llm = {"claude": "Claude", "groq": "Groq", "gemini": "Gemini"}.get(
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
        update_progress = _make_progress_callback(console, progress, task, _last_phase_pptx)

        # 유니크 파일명: 제목_접미사.pptx (접미사 = YYYYMMDDHHmmssfff)
        _now = datetime.now()
        _ts = _now.strftime("%Y%m%d%H%M%S") + f"{_now.microsecond // 1000:03d}"
        output_path = safe_output_path(
            output_dir, final_project_name, suffix=f"_{_ts}", extension=".pptx"
        )

        pptx_orchestrator.execute(
            content=content,
            output_path=output_path,
            template_name=template,
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
            f"[bold]디자인 스타일:[/bold] {content.design_style or 'modern'}",
            title="Complete",
            border_style="green",
        )
    )
    return ("ok", None)


def _make_progress_callback(console, progress, task, last_phase_ref):
    """
    Phase 패널 출력 + progress.update. 패널 아래에는 해당 Phase 로그만 나오도록
    새 Phase 전환 시 먼저 줄바꿈으로 이전 스피너 줄을 닫고, 스피너 갱신 후 패널 출력.
    """
    def update_progress(p):
        msg = p.get("message", "처리 중...")
        parts = msg.split(":", 1)
        if len(parts) >= 2 and parts[0].strip().startswith("Phase "):
            tok = parts[0].strip().split()
            if len(tok) == 2 and tok[1].isdigit():
                n = int(tok[1])
                if 0 <= n <= 7 and n != last_phase_ref[0]:
                    # 1) 먼저 줄바꿈으로 현재 줄 종료 → 이전 Phase 스피너 문구가 다음 패널 아래에 안 찍히게
                    console.print()
                    # 2) 스피너를 현재 Phase 메시지로 갱신
                    progress.update(task, description=msg)
                    # 3) 해당 Phase 패널 출력 → 아래에는 이 Phase 로그만 나옴
                    console.print(
                        Panel(
                            "",
                            title=f"[bold]Phase {n}: {PHASE_TITLES.get(n, '')}[/bold]",
                            border_style="yellow",
                        )
                    )
                    last_phase_ref[0] = n
                    return
        progress.update(task, description=msg)
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
    if _p == "claude":
        api_key = _settings.anthropic_api_key
        key_name = "ANTHROPIC_API_KEY"
    elif _p == "groq":
        api_key = _settings.groq_api_key
        key_name = "GROQ_API_KEY"
    else:
        api_key = _settings.gemini_api_key
        key_name = "GEMINI_API_KEY"
    if not api_key:
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
    console.print("  - [cyan]guide_template[/cyan] (기본) - templates/ 내 이름에 'guide' 포함 .pptx 자동 선택, 해당 파일 테마로 제안서 생성")

    if not templates_dir.exists():
        console.print("\n[yellow]templates 디렉토리가 없습니다.[/yellow]")
        return

    pptx_files = list(templates_dir.glob("*.pptx"))

    if pptx_files:
        console.print("\n[bold]커스텀 템플릿:[/bold]")
        for t in pptx_files:
            console.print(f"  - {t.stem}")


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
