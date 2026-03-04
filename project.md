# Proposal Agent — 소스코드 전체 분석 문서

> 작성일: 2026-03-04
> 버전: v3.6 (Impact-8 Framework + Win Theme + 설득 구조 강화)

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [디렉토리 구조](#2-디렉토리-구조)
3. [전체 아키텍처 및 데이터 흐름](#3-전체-아키텍처-및-데이터-흐름)
4. [설정 및 환경변수](#4-설정-및-환경변수)
5. [진입점: main.py](#5-진입점-mainpy)
6. [제안서 유형 시스템: config/proposal_types.py](#6-제안서-유형-시스템-configproposal_typespy)
7. [에이전트 레이어: src/agents/](#7-에이전트-레이어-srcagents)
8. [파서 레이어: src/parsers/](#8-파서-레이어-srcparsers)
9. [스키마 정의: src/schemas/](#9-스키마-정의-srcschemas)
10. [오케스트레이터: src/orchestrators/](#10-오케스트레이터-srcorhestrators)
11. [PPTX 생성 레이어: src/generators/](#11-pptx-생성-레이어-srcgenerators)
12. [유틸리티: src/utils/](#12-유틸리티-srcutils)
13. [프롬프트 파일: config/prompts/](#13-프롬프트-파일-configprompts)
14. [Impact-8 Framework 상세](#14-impact-8-framework-상세)
15. [LLM 호출 메커니즘 상세](#15-llm-호출-메커니즘-상세)
16. [슬라이드 유형 분류 체계](#16-슬라이드-유형-분류-체계)
17. [디자인 시스템](#17-디자인-시스템)
18. [테스트 구조](#18-테스트-구조)
19. [핵심 설계 패턴 및 특징](#19-핵심-설계-패턴-및-특징)

---

## 1. 프로젝트 개요

**Proposal Agent**는 RFP(제안요청서) 문서를 입력받아 Impact-8 구조의 PPTX 제안서를 자동 생성하는 AI 에이전트 시스템이다.

### 핵심 가치
- **RFP 파싱**: PDF/DOCX/TXT/PPTX 등 다양한 형식의 RFP 문서를 파싱
- **LLM 기반 분석·생성**: Claude / Gemini / Groq 중 하나를 선택해 RFP를 전략적으로 분석하고 제안서 콘텐츠를 생성
- **자동 PPTX 생성**: LLM 생성 콘텐츠를 Modern 스타일의 PPTX 파일로 변환
- **Impact-8 Framework**: 실제 수주 성공 제안서 분석을 기반으로 설계된 8-Phase 구조 (Phase 0~7)

### 기술 스택
| 분류 | 라이브러리 | 역할 |
|------|-----------|------|
| CLI | typer, rich | 커맨드라인 인터페이스 및 콘솔 출력 |
| AI/LLM | anthropic, google-genai, groq | LLM API 호출 (선택적) |
| 문서파싱 | pypdf, pdfplumber, python-docx | PDF/DOCX 파싱 |
| PPTX생성 | python-pptx | 슬라이드 생성 |
| 데이터검증 | pydantic v2 | 스키마 정의 및 타입 검증 |
| 로깅 | loguru | 구조화 로깅 |
| 설정 | python-dotenv | 환경변수 로드 |

### Python 버전
- Python 3.10+ 필요 (tuple 타입힌트: `tuple[str, str]` 문법 사용)

---

## 2. 디렉토리 구조

```
proposal-agent/
│
├── main.py                         # CLI 진입점 (typer 앱)
├── requirements.txt                # 패키지 의존성
├── .env.example                    # 환경변수 예시
├── .env                            # 실제 환경변수 (git 제외)
├── process.md                      # 본 문서
│
├── config/                         # 설정 모듈
│   ├── settings.py                 # 앱 전역 설정 (Pydantic BaseModel, 싱글톤)
│   ├── proposal_types.py           # 제안서 유형별 Phase 설정 (ProposalType Enum)
│   ├── phase_profiles.json.example # 외부 Phase 설정 예시 (선택적)
│   └── prompts/                    # Phase별 LLM 시스템 프롬프트
│       ├── rfp_analysis.txt        # RFP 분석 전문가 프롬프트
│       ├── content_guidelines.txt  # 콘텐츠 생성 공통 가이드라인
│       ├── phase0_hook.txt         # Phase 0: HOOK 프롬프트
│       ├── phase1_summary.txt      # Phase 1: SUMMARY 프롬프트
│       ├── phase2_insight.txt      # Phase 2: INSIGHT 프롬프트
│       ├── phase3_concept.txt      # Phase 3: CONCEPT & STRATEGY 프롬프트
│       ├── phase4_action.txt       # Phase 4: ACTION PLAN 프롬프트
│       ├── phase5_management.txt   # Phase 5: MANAGEMENT 프롬프트
│       ├── phase6_whyus.txt        # Phase 6: WHY US 프롬프트
│       └── phase7_investment.txt   # Phase 7: INVESTMENT & ROI 프롬프트
│
├── src/                            # 핵심 소스 모듈
│   ├── agents/                     # LLM 에이전트
│   │   ├── base_agent.py           # 추상 기반 에이전트 (LLM 호출 공통 로직)
│   │   ├── rfp_analyzer.py         # RFP 분석 에이전트
│   │   └── content_generator.py    # 제안서 콘텐츠 생성 에이전트 (Phase별 LLM 호출)
│   │
│   ├── parsers/                    # 문서 파서
│   │   ├── __init__.py             # get_parser_for_path() 통합 함수
│   │   ├── base_parser.py          # 파서 추상 클래스
│   │   ├── pdf_parser.py           # PDF 파서 (pypdf + pdfplumber)
│   │   ├── docx_parser.py          # DOCX 파서 (python-docx)
│   │   ├── txt_parser.py           # TXT 파서
│   │   └── pptx_parser.py          # PPTX 파서 (python-pptx)
│   │
│   ├── schemas/                    # Pydantic 데이터 스키마
│   │   ├── proposal_schema.py      # 제안서 콘텐츠 스키마 (SlideContent, PhaseContent 등)
│   │   └── rfp_schema.py           # RFP 분석 결과 스키마 (RFPAnalysis)
│   │
│   ├── orchestrators/              # 워크플로우 조율
│   │   ├── proposal_orchestrator.py # 제안서 콘텐츠 생성 오케스트레이터
│   │   └── pptx_orchestrator.py    # PPTX 생성 오케스트레이터
│   │
│   ├── generators/                 # PPTX 생성기
│   │   ├── template_manager.py     # 템플릿 로드·디자인 시스템 관리
│   │   ├── pptx_generator.py       # 슬라이드 생성기 (python-pptx 래퍼)
│   │   ├── chart_generator.py      # 차트·타임라인·조직도 생성기
│   │   └── diagram_generator.py    # 프로세스 다이어그램·KPI 카드 등
│   │
│   └── utils/                      # 유틸리티
│       ├── logger.py               # loguru 기반 로거 설정
│       └── path_utils.py           # 파일명 안전화·경로 이탈 방지
│
├── templates/                      # PPTX 템플릿 파일
│   ├── guide_template.pptx         # 기본 가이드 템플릿
│   └── guide_template_sub.pptx     # 서브 템플릿
│
├── input/                          # RFP 입력 파일 디렉토리
│   └── sample.txt                  # 샘플 RFP 문서
│
├── output/                         # 생성된 PPTX 출력 디렉토리
│
├── tests/                          # 테스트 코드
│   ├── conftest.py
│   ├── test_base_agent_json.py
│   ├── test_path_utils.py
│   ├── test_settings.py
│   ├── test_template_manager.py
│   └── parsers/
│       ├── test_get_parser.py
│       └── test_txt_parser.py
│
├── docs/                           # 문서
│   ├── INSTALL_AND_USAGE.md
│   ├── PROPOSAL_AGENT_GUIDE.md
│   └── 실행_가이드.md 등
│
└── scripts/                        # 환경 로드 스크립트
    ├── load-mcp-env.bat
    ├── load-mcp-env.ps1
    └── load-mcp-env.sh
```

---

## 3. 전체 아키텍처 및 데이터 흐름

### 3.1 전체 파이프라인

```
[사용자]
   │
   ▼ python main.py generate input/rfp.pdf -n "프로젝트명" -t marketing_pr
   │
[main.py]
   │ CLI 인수 파싱 (typer)
   │ API 키 검증 / 유형 검증
   │ asyncio.run() 실행
   │
   ▼
[_generate_async_impl()]
   │
   │  ┌─────────────────────────────────────────┐
   │  │          Step 1: 콘텐츠 생성             │
   │  │     ProposalOrchestrator.execute()       │
   │  └─────────────────────────────────────────┘
   │     │
   │     ▼
   │  [1-1] 문서 파싱
   │     get_parser_for_path(rfp_path) → PDFParser / DOCXParser / TXTParser / PPTXParser
   │     parser.parse(rfp_path) → {raw_text, tables, sections, metadata}
   │     │
   │     ▼
   │  [1-2] 회사 데이터 로드
   │     company_data/company_profile.json → Dict
   │     │
   │     ▼
   │  [1-3] RFP 분석 (LLM)
   │     RFPAnalyzer.execute(parsed_rfp) → RFPAnalysis
   │     LLM(Claude/Gemini/Groq)에 RFP 텍스트 전달
   │     JSON 응답 → Pydantic 검증 → RFPAnalysis 객체
   │     │
   │     ▼
   │  [1-4] 제안서 콘텐츠 생성 (LLM, Phase별 순차 호출)
   │     ContentGenerator.execute(rfp_analysis, company_data, ...) → ProposalContent
   │     Phase 0~7 각각 LLM 호출 → SlideContent 목록 생성
   │     │
   │     ▼
   │  ProposalContent 반환
   │
   │  ┌─────────────────────────────────────────┐
   │  │          Step 2: PPTX 생성               │
   │  │     PPTXOrchestrator.execute()           │
   │  └─────────────────────────────────────────┘
   │     │
   │     ▼
   │  [2-1] 프레젠테이션 초기화
   │     TemplateManager.load_template() → Presentation 객체
   │     │
   │     ▼
   │  [2-2] Phase 0: 티저/HOOK 슬라이드 추가
   │     _add_teaser_slides() → add_teaser_slide / add_title_slide
   │     │
   │     ▼
   │  [2-3] Phase 1~7: 슬라이드 추가 (순차)
   │     _add_phase_slides() → add_section_divider + _add_content_slide
   │     슬라이드 유형(slide_type)에 따라 PPTXGenerator / ChartGenerator / DiagramGenerator 호출
   │     │
   │     ▼
   │  [2-4] PPTX 저장
   │     PPTXGenerator.save(output_path)
   │
   ▼
[출력] output/[프로젝트명]_[타임스탬프].pptx
```

### 3.2 객체 관계도

```
ProposalOrchestrator
 ├── RFPAnalyzer (BaseAgent 구현)
 │    └── _call_llm() → Claude / Gemini / Groq
 └── ContentGenerator (BaseAgent 구현)
      └── _call_llm() per Phase (0~7)

PPTXOrchestrator
 ├── TemplateManager
 │    ├── load_template() → Presentation
 │    ├── design_system (colors, fonts, spacing)
 │    └── get_placeholder_geometry()
 ├── PPTXGenerator
 │    ├── add_title_slide()
 │    ├── add_section_divider()
 │    ├── add_content_slide()
 │    ├── add_two_column_slide()
 │    ├── add_three_column_slide()
 │    ├── add_table_slide()
 │    ├── add_teaser_slide()
 │    ├── add_key_message_slide()
 │    ├── add_comparison_slide()
 │    ├── add_index_slide()
 │    ├── add_content_example_slide()
 │    ├── add_channel_strategy_slide()
 │    ├── add_campaign_slide()
 │    ├── add_budget_slide()
 │    └── add_case_study_slide()
 ├── ChartGenerator
 │    ├── add_chart_slide()
 │    ├── add_timeline_slide()
 │    └── add_org_chart_slide()
 └── DiagramGenerator
      └── add_process_slide()
```

---

## 4. 설정 및 환경변수

### 4.1 config/settings.py

`Settings` 클래스(Pydantic BaseModel)가 모든 설정을 담는다. `get_settings()`로 싱글톤 인스턴스를 반환한다.

```python
class Settings(BaseModel):
    # LLM 프로바이더 선택
    llm_provider: str               # "claude" | "gemini" | "groq" (기본: "gemini")

    # Claude (Anthropic) API
    anthropic_api_key: str          # ANTHROPIC_API_KEY
    anthropic_model: str            # 기본: "claude-3-5-sonnet-20241022"

    # Gemini (Google) API
    gemini_api_key: str             # GEMINI_API_KEY
    gemini_model: str               # 기본: "gemini-2.5-flash-lite"

    # Groq API
    groq_api_key: str               # GROQ_API_KEY
    groq_model: str                 # 기본: "llama-3.1-8b-instant"
    groq_max_user_message_chars: int # 413 방지 (기본 0=무제한)
    groq_max_request_tokens: int    # 413 방지 (기본 5000 토큰)

    # 로그
    log_level: str                  # "DEBUG" | "INFO" | "WARNING" | "ERROR"

    # LLM 공통
    llm_max_tokens_default: int     # 기본 8192 (최대 출력 토큰)
    llm_temperature: float          # 기본 0.4 (0~2, 낮을수록 JSON 준수↑)
    llm_retry_count: int            # 기본 3 (API 실패 시 재시도 횟수 1~10)
    llm_retry_base_delay_seconds: float  # 기본 5.0 (지수 백오프 기준)
    llm_delay_seconds: float        # 기본 8.0 (호출 후 대기시간, 429 방지)
    llm_json_retry_count: int       # 기본 2 (JSON 추출 실패 시 재시도 1~5)

    # 경로
    base_dir: Path                  # 프로젝트 루트
    templates_dir: Path             # templates/
    prompts_dir: Path               # config/prompts/
    output_dir: Path                # output/
    input_dir: Path                 # input/

    # PPTX 기본값
    slide_width_inches: float       # 13.33 (16:9 기준)
    slide_height_inches: float      # 7.5
```

### 4.2 환경변수 (.env)

```env
# 필수: LLM 프로바이더 선택
LLM_PROVIDER=gemini          # claude | gemini | groq

# 해당 프로바이더의 API 키
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AIza...
GROQ_API_KEY=gsk_...

# 선택: 모델 지정
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
GEMINI_MODEL=gemini-2.5-flash-lite
GROQ_MODEL=llama-3.1-8b-instant

# 선택: LLM 동작 튜닝
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=0.4
LLM_RETRY_COUNT=3
LLM_JSON_RETRY_COUNT=2
LLM_RETRY_BASE_DELAY=5
LLM_DELAY_SECONDS=8

# Groq 전용: 413 방지
GROQ_MAX_USER_MESSAGE_CHARS=10000
GROQ_MAX_REQUEST_TOKENS=5000

# 로그 레벨
LOG_LEVEL=INFO
```

### 4.3 Pydantic 유효성 검사

- `llm_provider`: "claude", "gemini", "groq" 중 하나 (그 외는 ValueError)
- `llm_max_tokens_default`: 1~128000 범위
- `llm_retry_count`: 1~10 범위
- `llm_json_retry_count`: 1~5 범위
- `llm_temperature`: 0~2 범위
- `llm_delay_seconds`, `llm_retry_base_delay_seconds`: 0 이상

---

## 5. 진입점: main.py

### 5.1 CLI 명령 구조

typer 앱으로 4개 명령을 제공한다.

| 명령 | 설명 |
|------|------|
| `generate` | RFP 경로로 제안서 PPTX 생성 (핵심 명령) |
| `analyze` | RFP 분석만 수행 (PPTX 미생성) |
| `types` | 지원 제안서 유형 목록 출력 |
| `templates` | 사용 가능한 PPTX 템플릿 목록 출력 |
| `info` | Impact-8 Framework 정보 출력 |

### 5.2 generate 명령 옵션

```bash
python main.py generate <RFP_PATH> [OPTIONS]

OPTIONS:
  -n, --name       프로젝트명 (미입력시 RFP에서 추출)
  -c, --client     발주처명 (미입력시 RFP에서 추출)
  -t, --type       제안서 유형 (marketing_pr | event | it_system | public | consulting | general)
  -d, --company    회사 정보 JSON 경로 (기본: company_data/company_profile.json)
  -o, --output     출력 디렉토리 (기본: output/)
  -T, --template   템플릿 파일명 (확장자 제외, 미지정시 기본 디자인)
  --save-json      중간 JSON 파일 저장 여부
```

### 5.3 generate 내부 실행 흐름

```python
def generate(...):
    # 1. API 키 확인 (LLM_PROVIDER에 따라 다른 키 검사)
    # 2. 제안서 유형 유효성 검증
    # 3. 헤더 패널 출력 (Rich Panel)
    # 4. output_dir 생성
    # 5. asyncio.run(_generate_async(...))  ← 비동기 실행
    # 6. 에러 처리 (429 할당량 초과 / 기타)

async def _generate_async_impl(...):
    # Step 1: ProposalOrchestrator.execute() → ProposalContent
    #   - Rich Progress 스피너 표시
    #   - Phase 전환마다 패널 출력
    # Step 2: PPTXOrchestrator.execute() → PPTX 파일
    #   - 타임스탬프 기반 유니크 파일명 생성
    # 결과 패널 출력 (파일 경로, 슬라이드 수 등)
    # Phase별 진단 정보 JSON 저장 (run_diagnostics_*.json)
```

### 5.4 Progress 콜백 시스템

Phase 전환을 화면에 시각화하는 두 가지 콜백이 있다.

**`_make_progress_callback`** (Step 1 콘텐츠 생성용):
- 메시지가 `"Phase N:"` 형식이면 Phase 전환으로 판단
- `console.print()` → 줄바꿈 → `progress.update(refresh=True)` → Phase 패널 출력
- loguru 로그가 Progress 라이브 라인에 붙지 않도록 선행 줄바꿈 처리

**`_make_pptx_progress_callback`** (Step 2 PPTX 생성용):
- 동일 패턴, PPTX_MSG는 고정 문구 "PPTX 생성 중..."

### 5.5 출력 진단 테이블

실행 후 두 가지 테이블이 콘솔에 출력된다.

1. **콘텐츠 요약**: Phase별 슬라이드 수, 총 슬라이드 수, 슬로건, 핵심 제안
2. **Phase별 진단**: Phase, 제목, 슬라이드 수, 소요시간(초), JSON 성공 여부(✓/✗)

---

## 6. 제안서 유형 시스템: config/proposal_types.py

### 6.1 ProposalType Enum

6가지 제안서 유형을 정의한다.

| 코드 | 한글명 | 설명 |
|------|--------|------|
| `marketing_pr` | 마케팅/PR | 소셜미디어 운영, 브랜드 마케팅, PR 캠페인 |
| `event` | 이벤트/행사 | 기업 행사, 컨퍼런스, 전시회, 프로모션 |
| `it_system` | IT/시스템 | 시스템 구축, 소프트웨어 개발, 플랫폼 구축 |
| `public` | 공공/입찰 | 정부/지자체 사업, 공공 입찰 |
| `consulting` | 컨설팅 | 경영/전략/디지털 전환 컨설팅 |
| `general` | 일반 | 기타 일반 프로젝트 |

### 6.2 PhaseConfig 데이터클래스

각 Phase의 설정을 담는다.

```python
@dataclass
class PhaseConfig:
    title: str           # Phase 제목 (예: "ACTION PLAN")
    subtitle: str        # 부제목/설명
    weight: float        # 전체 대비 비중 (0.0~1.0)
    min_slides: int      # 최소 슬라이드 수
    max_slides: int      # 최대 슬라이드 수
    required: bool       # 필수 Phase 여부 (기본 True)
    special_focus: List[str]  # 특별 강조 요소 목록
```

### 6.3 유형별 Phase 비중 비교

| Phase | marketing_pr | event | it_system | public | consulting | general |
|-------|-------------|-------|-----------|--------|------------|---------|
| 0 HOOK | 8% | 6% | 3% | 3% | 5% | 5% |
| 1 SUMMARY | 5% | 5% | 8% | 8% | 8% | 6% |
| 2 INSIGHT | 12% | 8% | 12% | 15% | 15% | 10% |
| 3 CONCEPT | 12% | 10% | 10% | 10% | 12% | 10% |
| **4 ACTION** | **40%** | **45%** | **35%** | **30%** | **30%** | **35%** |
| 5 MANAGEMENT | 8% | 10% | 12% | 12% | 10% | 10% |
| 6 WHY US | 10% | 10% | 12% | 15% | 12% | 12% |
| 7 INVESTMENT | 5% | 6% | 8% | 7% | 8% | 7% |

→ **ACTION PLAN이 전체의 30~45%**로 제안서의 핵심 섹션

### 6.4 phase_profiles.json (선택적 외부 설정)

`config/phase_profiles.json` 파일이 존재하면 코드 수정 없이 Phase 설정을 외부에서 재정의할 수 있다.

```json
{
  "marketing_pr": {
    "total_pages_range": [100, 150],
    "phases": {
      "4": {
        "title": "ACTION PLAN",
        "weight": 0.45,
        "min_slides": 35,
        "max_slides": 70
      }
    }
  }
}
```

`get_config(proposal_type)` → JSON 우선 적용 → 없으면 코드 기본값 반환

### 6.5 페이지 수 계산 알고리즘

```python
def calculate_pages(proposal_type, total_pages=100):
    for phase_num, phase_config in config.phases.items():
        base_pages = int(total_pages * phase_config.weight)
        min_pages = max(phase_config.min_slides, int(base_pages * 0.8))
        max_pages = min(phase_config.max_slides, int(base_pages * 1.2))
        result[phase_num] = (min_pages, max_pages)
```

---

## 7. 에이전트 레이어: src/agents/

### 7.1 BaseAgent (base_agent.py)

모든 LLM 에이전트의 추상 기반 클래스. LLM 호출 공통 로직을 제공한다.

#### 초기화 (LLM 프로바이더 분기)

```python
class BaseAgent(ABC):
    def __init__(self, api_key=None, model=None):
        if provider == "claude":
            self._anthropic_client = Anthropic(api_key=...)
            self._use_claude = True
        elif provider == "groq":
            self._groq_client = Groq(api_key=...)
            self._use_groq = True
        else:  # gemini (기본)
            self.client = genai.Client(api_key=...)
```

#### 핵심 메서드

| 메서드 | 설명 |
|--------|------|
| `_call_llm(system_prompt, user_message, max_tokens, temperature)` | LLM API 호출 (프로바이더 자동 분기) |
| `_call_claude(...)` | Claude API 호출 (재시도 포함) |
| `_call_groq(...)` | Groq API 호출 (413/429 대응, 입력 길이 제한) |
| `_call_gemini(...)` | Gemini API 호출 (재시도 포함) |
| `_call_llm_and_extract_json(...)` | LLM 호출 + JSON 추출 + 실패시 재시도 |
| `_extract_json(text)` | 응답 텍스트에서 JSON 파싱 (다단계 폴백) |
| `_load_prompt(prompt_name)` | 프롬프트 파일 로드 (캐시 적용) |
| `_normalize_json_keys(data, alias_map)` | camelCase 등 키 통일 |
| `_truncate_text(text, max_chars)` | 텍스트 길이 제한 |

#### JSON 추출 다단계 폴백 (_extract_json)

LLM 응답에서 JSON을 추출하는 견고한 로직:

```
1. ```json ... ``` 코드 블록에서 추출 (정규식)
2. { ... } 중괄호 블록에서 추출
3. 깊이 추적으로 가장 큰 중괄호 블록 추출
4. 알려진 키 앵커 기반 복구
   (project_name, slides, bullets, table, timeline 등)
5. **key**: "value" 마크다운 형식에서 복구 (Groq 등이 마크다운 반환 시)
6. 모두 실패 시 {} 반환
```

trailing comma 등 비표준 JSON도 정규식으로 수정 후 파싱 시도.

#### Groq 413 방지 메커니즘

Groq on-demand 한도(6000 TPM)를 초과하면 413 에러 발생. 두 단계로 방지:

1. **`GROQ_MAX_USER_MESSAGE_CHARS`**: user 메시지 문자 수 상한 (0=무제한)
2. **`_truncate_for_groq_limit()`**: 토큰 상한(`GROQ_MAX_REQUEST_TOKENS`) 초과 시 자동 절단
   - 한글은 1토큰 ≈ 2자로 보수적 추정 (`_GROQ_CHARS_PER_TOKEN = 2`)
   - user 메시지 우선 절단 → 부족하면 system 프롬프트까지 절단

#### JSON 재시도 메커니즘 (_call_llm_and_extract_json)

```
for attempt in range(max_json_retries):  # 기본 2회
    response = _call_llm(...)
    data = _extract_json(response)
    if data and isinstance(data, dict) and len(data) > 0:
        return data
    # 실패 시 원본 응답 WARNING 로그 (최대 2000자)
    # 재시도: user_message에 "[재요청] JSON만 출력" 힌트 추가
return {}
```

### 7.2 RFPAnalyzer (rfp_analyzer.py)

RFP 문서를 분석해 `RFPAnalysis` 객체를 반환한다.

#### 입력
```python
input_data = {
    "raw_text": str,           # 파서가 추출한 전체 텍스트 (최대 25,000자 truncate)
    "tables": List[Dict],      # 테이블 데이터 (최대 10개, JSON 최대 5,000자)
    "sections": List[Dict],    # 헤딩 기반 섹션
}
```

#### 프롬프트 구조

- **시스템 프롬프트**: `config/prompts/rfp_analysis.txt` (제안서 전문 컨설턴트 역할)
  - 기본 정보 추출: 프로젝트명, 발주처, 기간, 예산
  - 요구사항 분석: 기능/비기능/기술/관리 요구사항
  - 평가 기준 분석: 항목별 배점, 고배점 항목 식별
  - 전략적 분석: CSF, 리스크, 차별화 포인트, 수주 전략
- **사용자 메시지**: RFP 텍스트 + 테이블 데이터 + 요청 JSON 스키마

#### 분석 결과 JSON 스키마 (핵심 필드)

```json
{
  "project_name": "프로젝트명",
  "client_name": "발주처명",
  "project_overview": "개요 2-3문장",
  "project_type": "marketing_pr | event | it_system | public | consulting | general",
  "key_requirements": [{"category": "기능", "requirement": "...", "priority": "필수"}],
  "evaluation_criteria": [{"category": "기술", "item": "...", "weight": 30}],
  "pain_points": ["발주처 핵심 고민 1", "2", "3"],
  "hidden_needs": ["RFP에 명시되지 않은 숨겨진 니즈"],
  "evaluation_strategy": {
    "high_weight_items": [{"item": "...", "weight": 30, "proposal_emphasis": "..."}],
    "emphasis_mapping": {
      "Phase 2 (INSIGHT)": "강조할 평가 항목",
      "Phase 4 (ACTION)": "강조할 평가 항목",
      "Phase 6 (WHY US)": "강조할 평가 항목"
    }
  },
  "win_theme_candidates": [
    {"name": "Win Theme 이름", "rationale": "이유", "rfp_alignment": "연결 요구사항"},
    {"name": "Win Theme 2", ...},
    {"name": "Win Theme 3", ...}
  ],
  "competitive_landscape": "예상 경쟁 환경 분석",
  "winning_strategy": "수주 전략"
}
```

#### 키 정규화 (camelCase → snake_case)

```python
RFP_KEY_ALIASES = {
    "projectName": "project_name",
    "clientName": "client_name",
    "winThemeCandidates": "win_theme_candidates",
    # ... 등 다수
}
```

모델별 응답 키 차이를 흡수한다.

### 7.3 ContentGenerator (content_generator.py)

`RFPAnalysis`를 입력받아 Phase 0~7 각각에 대해 LLM을 순차 호출하고 `ProposalContent`를 반환한다.

#### Phase별 프롬프트 매핑

```python
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
```

#### 실행 흐름

```
1. RFP 분석 결과 + 회사 데이터 + 프로젝트 정보 정리
2. Win Theme 3개 선택 (rfp_analysis.win_theme_candidates 기반)
3. 제안서 유형 결정 (rfp_analysis.project_type → ProposalType Enum)
4. Phase별 LLM 호출 (순차):
   - Phase 0 (HOOK/티저): teaser_data → TeaserContent 구성
   - Phase 1~7: phase_data → PhaseContent 구성
5. ProposalContent 조립 (teaser + phases 리스트)
6. diagnostics_out에 Phase별 진단 정보 추가
   (phase, phase_title, slides_count, elapsed_sec, json_ok)
```

#### 콘텐츠 생성 프롬프트 구조 (각 Phase)

시스템 프롬프트:
- `content_guidelines.txt` (공통 가이드라인: Action Title, Win Theme, C-E-I 설득 구조)
- `phase{N}_{name}.txt` (Phase별 상세 지침)

사용자 메시지:
- 프로젝트명, 발주처명, 유형, 제출일
- RFP 핵심 요약 (pain_points, win_theme_candidates, evaluation_strategy 포함)
- 회사 프로필 데이터
- Phase별 목표 슬라이드 수 (제안서 유형 기반 계산)
- 요청 JSON 스키마

#### v3.6 설득 구조 강화 기능

- **Win Theme 전달 체인**: 3개 Win Theme이 Phase 전체에 반복적으로 등장
- **Action Title 강제**: 모든 슬라이드 제목이 인사이트 기반 (Topic Title 금지)
- **C-E-I 설득 구조**: Claim(주장) → Evidence(근거) → Impact(효과) 순서
- **KPIWithBasis**: KPI 목표값에 산출 근거와 데이터 출처 포함

---

## 8. 파서 레이어: src/parsers/

### 8.1 통합 선택 함수 (\_\_init\_\_.py)

```python
def get_parser_for_path(path) -> Parser:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":    return PDFParser()
    if suffix in (".docx", ".doc"): return DOCXParser()
    if suffix == ".txt":    return TXTParser()
    if suffix == ".pptx":   return PPTXParser()
    raise ValueError(f"지원하지 않는 형식: {suffix}")
```

### 8.2 BaseParser (추상 클래스)

```python
class BaseParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path) -> Dict[str, Any]:
        # 반환: {raw_text, tables, sections, metadata}
        pass

    @abstractmethod
    def extract_text(self, file_path: Path) -> str:
        pass

    @abstractmethod
    def extract_tables(self, file_path: Path) -> List[Dict]:
        pass

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        pass
```

### 8.3 파서별 구현

| 파서 | 라이브러리 | 특이사항 |
|------|----------|----------|
| PDFParser | pypdf + pdfplumber | pdfplumber로 테이블 추출, pypdf로 텍스트 추출 |
| DOCXParser | python-docx | 단락, 테이블, 스타일 추출 |
| TXTParser | 표준 라이브러리 | 인코딩 자동 감지 (utf-8, cp949 등) |
| PPTXParser | python-pptx | 슬라이드별 텍스트, 테이블, 노트 추출 |

### 8.4 파서 반환 형식

```python
{
    "raw_text": "전체 추출 텍스트 (모든 페이지/슬라이드 합산)",
    "tables": [
        {"headers": [...], "rows": [[...], [...]], "caption": "..."}
    ],
    "sections": [
        {"title": "섹션 제목", "content": "내용", "level": 1}
    ],
    "metadata": {
        "title": "문서 제목",
        "author": "작성자",
        "pages": 30,
        "file_type": "pdf"
    }
}
```

---

## 9. 스키마 정의: src/schemas/

### 9.1 rfp_schema.py (RFP 분석 결과)

#### 주요 모델

```python
class RFPAnalysis(BaseModel):
    # 기본 정보
    project_name: str
    client_name: str
    project_overview: str

    # 요구사항
    key_requirements: List[Requirement]
    technical_requirements: List[Requirement]
    functional_requirements: List[Requirement]

    # 평가 기준
    evaluation_criteria: List[EvaluationCriterion]

    # 산출물·일정·예산
    deliverables: List[Deliverable]
    timeline: Optional[TimelineInfo]
    budget: Optional[BudgetInfo]

    # 분석 인사이트
    key_success_factors: List[str]
    potential_risks: List[str]
    winning_strategy: Optional[str]
    differentiation_points: List[str]

    # v3.6 전략 필드
    project_type: str                        # 자동 분류된 유형
    pain_points: List[str]                   # 발주처 핵심 고민 3~5개
    hidden_needs: List[str]                  # 명시되지 않은 숨겨진 니즈
    evaluation_strategy: Optional[Dict]      # 평가기준 → Phase 강조 매핑
    win_theme_candidates: List[Dict[str,str]] # Win Theme 후보 3개
    competitive_landscape: Optional[str]     # 경쟁 환경 분석
```

### 9.2 proposal_schema.py (제안서 콘텐츠)

#### SlideType Enum (슬라이드 유형 21종)

```python
class SlideType(str, Enum):
    TITLE = "title"                    # 표지 슬라이드
    SECTION_DIVIDER = "section_divider" # Phase 구분자
    CONTENT = "content"                # 일반 콘텐츠
    TWO_COLUMN = "two_column"          # 2단 레이아웃
    THREE_COLUMN = "three_column"      # 3단 레이아웃
    TABLE = "table"                    # 테이블
    CHART = "chart"                    # 차트
    TIMELINE = "timeline"              # 타임라인
    ORG_CHART = "org_chart"            # 조직도
    IMAGE = "image"                    # 이미지 플레이스홀더
    COMPARISON = "comparison"          # AS-IS / TO-BE 비교
    KEY_MESSAGE = "key_message"        # 핵심 메시지 강조
    INDEX = "index"                    # 목차
    PROCESS = "process"                # 프로세스 플로우
    TEASER = "teaser"                  # 티저/임팩트 슬라이드
    CASE_STUDY = "case_study"          # 사례 연구
    CONTENT_EXAMPLE = "content_example" # 콘텐츠 예시 (마케팅/PR)
    CHANNEL_STRATEGY = "channel_strategy" # 채널별 전략
    CAMPAIGN = "campaign"              # 캠페인 소개
    BUDGET = "budget"                  # 예산 테이블
    EXECUTIVE_SUMMARY = "executive_summary" # Executive Summary
    NEXT_STEP = "next_step"            # Next Step / Call to Action
    DIFFERENTIATION = "differentiation" # 차별화 포인트
```

#### SlideContent 모델 (슬라이드 하나)

```python
class SlideContent(BaseModel):
    slide_type: SlideType
    title: str                          # Action Title 형식 권장
    subtitle: Optional[str]
    bullets: Optional[List[BulletPoint]]
    table: Optional[TableData]
    chart: Optional[ChartData]
    timeline: Optional[List[TimelineItem]]
    org_chart: Optional[OrgChartNode]
    left_content: Optional[List[BulletPoint]]   # two_column용
    right_content: Optional[List[BulletPoint]]  # two_column용
    center_content: Optional[List[BulletPoint]] # three_column용
    left_title / right_title / center_title: Optional[str]
    key_message: Optional[str]          # 슬라이드 하단 핵심 메시지
    kpis: Optional[List[KPIItem]]
    comparison: Optional[ComparisonData] # Before/After
    content_examples: Optional[List[ContentExample]]  # 마케팅/PR 전용
    channel_strategy: Optional[ChannelStrategy]
    campaign: Optional[CampaignPlan]
    notes: Optional[str]                # 발표자 노트
    layout_hint: Optional[str]          # "full_bleed", "centered", "left_heavy"
    visual_style: Optional[str]         # "dark", "light", "gradient", "image_bg"
    accent_color: Optional[str]
```

#### ProposalContent 모델 (제안서 전체)

```python
class ProposalContent(BaseModel):
    # 기본 정보
    project_name: str
    client_name: str
    submission_date: str
    company_name: str = "[회사명]"

    # 유형
    proposal_type: ProposalType

    # 핵심 메시지
    one_sentence_pitch: Optional[str]       # 한 문장 제안
    key_differentiators: Optional[List[str]] # 3가지 차별점
    slogan: Optional[str]

    # v3.1 추가
    win_themes: Optional[List[WinTheme]]         # 3~4개 Win Theme
    executive_summary: Optional[ExecutiveSummary] # 의사결정권자용 요약
    next_step: Optional[NextStep]                 # Call to Action

    # 구조
    rfp_summary: Dict                       # RFP 분석 결과 요약
    table_of_contents: Optional[List[TOCItem]]
    teaser: Optional[TeaserContent]         # Phase 0: HOOK
    phases: List[PhaseContent]              # Phase 1~7 (6~8개 필수)

    # 디자인
    design_style: Optional[str] = "guide_template"
```

#### PHASE_TITLES 상수 (단일 소스)

```python
PHASE_TITLES = {
    0: "HOOK",
    1: "SUMMARY",
    2: "INSIGHT",
    3: "CONCEPT & STRATEGY",
    4: "ACTION PLAN",
    5: "MANAGEMENT",
    6: "WHY US",
    7: "INVESTMENT & ROI",
}
```
→ main.py, content_generator.py, pptx_orchestrator.py 모두 이 상수를 import해 사용 (DRY 원칙)

---

## 10. 오케스트레이터: src/orchestrators/

### 10.1 ProposalOrchestrator (proposal_orchestrator.py)

RFP → 제안서 콘텐츠 전체 워크플로우를 조율한다.

#### 4단계 실행

```python
async def execute(rfp_path, company_data_path, project_name, client_name,
                  submission_date, proposal_type, progress_callback) -> ProposalContent:
    # Step 1: 문서 파싱
    parsed_rfp = self._parse_document(rfp_path)

    # Step 2: 회사 데이터 로드 (있는 경우)
    company_data = self._load_company_data(company_data_path)

    # Step 3: RFP 분석 (LLM)
    rfp_analysis = await self.rfp_analyzer.execute(parsed_rfp, ...)

    # Step 4: 콘텐츠 생성 (LLM, Phase별)
    proposal_content = await self.content_generator.execute(
        input_data={
            "rfp_analysis": rfp_analysis,
            "company_data": company_data,
            "project_name": final_project_name,
            "client_name": final_client_name,
            "submission_date": submission_date,
            "proposal_type": proposal_type,
        },
        diagnostics_out=run_diagnostics,  # 진단 정보 수집
    )
    self._run_diagnostics = run_diagnostics
    return proposal_content
```

#### 제공 메서드

- `get_run_diagnostics()`: 마지막 실행의 Phase별 진단 정보 반환
- `save_content_json(content, output_path)`: ProposalContent를 JSON 파일로 저장
- `get_proposal_summary(content)`: 제안서 요약 딕셔너리 반환

### 10.2 PPTXOrchestrator (pptx_orchestrator.py)

ProposalContent → PPTX 파일 변환 워크플로우를 조율한다.

#### 실행 흐름

```python
def execute(content, output_path, template_name, progress_callback) -> Path:
    # 1. 프레젠테이션 초기화 (템플릿 또는 기본 디자인)
    self.generator.create_presentation(template_name or "")

    # 2. Phase 0: 티저/HOOK 슬라이드
    self._add_teaser_slides(content.teaser, content)

    # 3. Phase 1~7: 순차 슬라이드 추가
    for phase in content.phases:
        self._add_phase_slides(phase, content)

    # 4. 저장
    self.generator.save(output_path)
```

#### 슬라이드 추가 분기 (_add_content_slide)

슬라이드 유형에 따라 21가지 분기 처리:

```
section_divider  → PPTXGenerator.add_section_divider()
content          → PPTXGenerator.add_content_slide()
two_column       → PPTXGenerator.add_two_column_slide()
three_column     → PPTXGenerator.add_three_column_slide()
table            → PPTXGenerator.add_table_slide() (rows가 있을 때)
                   없으면 → add_content_slide() (폴백)
chart            → ChartGenerator.add_chart_slide()
timeline         → ChartGenerator.add_timeline_slide()
org_chart        → ChartGenerator.add_org_chart_slide()
comparison       → PPTXGenerator.add_comparison_slide()
key_message      → PPTXGenerator.add_key_message_slide()
content_example  → PPTXGenerator.add_content_example_slide()
channel_strategy → PPTXGenerator.add_channel_strategy_slide()
campaign         → PPTXGenerator.add_campaign_slide()
budget           → PPTXGenerator.add_budget_slide()
case_study       → PPTXGenerator.add_case_study_slide()
teaser           → PPTXGenerator.add_teaser_slide()
index            → PPTXGenerator.add_index_slide()
process          → DiagramGenerator.add_process_slide()
기타             → PPTXGenerator.add_content_slide() (폴백)
```

#### 에러 폴백 처리

```python
try:
    # 슬라이드 유형별 처리
    ...
except (TypeError, AttributeError, ValueError) as e:
    logger.warning("슬라이드 처리 실패 → 콘텐츠로 대체 | ...")
    _fallback_content()  # add_content_slide()로 대체 (PPTX 생성 중단 방지)
```

---

## 11. PPTX 생성 레이어: src/generators/

### 11.1 TemplateManager (template_manager.py)

PPTX 템플릿 로드, 레이아웃 인덱스 관리, 디자인 시스템 제공을 담당한다.

#### 초기화

```python
class TemplateManager:
    def __init__(self, templates_dir):
        self.layouts = self._load_layouts()    # slide_layouts.json 또는 기본값
        self.design_system = self._get_design_system()
        self._layout_geometry = None           # 템플릿 로드 후 채워짐
```

#### 템플릿 로드 흐름

```python
def load_template(self, template_name: str) -> Presentation:
    if not template_name:
        # 빈 프레젠테이션 + 기본 디자인 시스템 사용
        return Presentation()

    # templates/{template_name}.pptx 로드
    # 테마에서 동적 추출:
    #   - 슬라이드 크기 (width, height)
    #   - 색상 테마 (lt1, dk1, lt2, dk2, accent1~6)
    #   - 폰트 테마 (major, minor)
    #   - 플레이스홀더 위치/크기 (title, body 등)
    # design_system 업데이트 (추출된 값으로 덮어쓰기)
```

#### design_system 구조

```python
design_system = {
    "colors": {
        "primary": RGBColor(0, 44, 95),      # 다크 블루 #002C5F
        "secondary": RGBColor(0, 170, 210),   # 스카이블루 #00AAD2
        "accent": RGBColor(230, 51, 18),      # 액센트 레드 #E63312
        "background": RGBColor(255, 255, 255),
        "dark_bg": RGBColor(26, 26, 26),
        "text_primary": RGBColor(51, 51, 51),
        "text_secondary": RGBColor(102, 102, 102),
        "text_light": RGBColor(255, 255, 255),
    },
    "fonts": {
        "title": "Pretendard",
        "body": "Pretendard",
    },
    "spacing": {
        "margin": Inches(0.5),
    }
}
```

#### 레이아웃 인덱스 (slide_layouts.json)

```json
{
  "layouts": {
    "title":       {"index": 0, "name": "Title Slide"},
    "section":     {"index": 2, "name": "Section Header"},
    "content":     {"index": 1, "name": "Title and Content"},
    "two_column":  {"index": 3, "name": "Two Content"},
    "comparison":  {"index": 4, "name": "Comparison"},
    "blank":       {"index": 6, "name": "Blank"}
  }
}
```

`_safe_layout_index()`: 템플릿 레이아웃 개수 내로 인덱스 보정 (index out of range 방지)

### 11.2 PPTXGenerator (pptx_generator.py)

실제 슬라이드를 생성하는 메인 생성기. python-pptx를 사용한다.

#### 치수 계산 (하드코딩 최소화)

```python
def _slide_width_inches(self):
    # 우선순위: TemplateManager → prs.slide_width → 기본값 13.33

def _margin_inches(self):
    # 우선순위: 템플릿 title 플레이스홀더 left → design_system spacing → 0.5

def _content_width_inches(self):
    # 우선순위: 템플릿 title 플레이스홀더 width → 슬라이드 - 2*여백
```

#### 주요 슬라이드 생성 메서드

| 메서드 | 설명 |
|--------|------|
| `add_title_slide(title, subtitle, slogan)` | 표지 슬라이드 |
| `add_teaser_slide(headline, subheadline, background_color)` | 다크 배경 티저 |
| `add_section_divider(phase_number, phase_title, phase_subtitle)` | Phase 구분자 |
| `add_content_slide(title, subtitle, bullets, key_message, layout_hint)` | 일반 콘텐츠 |
| `add_two_column_slide(title, left_title, right_title, left_bullets, right_bullets)` | 2단 레이아웃 |
| `add_three_column_slide(title, columns, key_message)` | 3단 레이아웃 |
| `add_table_slide(title, table_data, key_message)` | 테이블 |
| `add_key_message_slide(message, supporting_text, background_style)` | 핵심 메시지 강조 |
| `add_comparison_slide(title, as_is, to_be)` | AS-IS / TO-BE 비교 |
| `add_index_slide(title, items, current_index)` | 목차 |
| `add_content_example_slide(title, examples)` | 마케팅/PR 콘텐츠 예시 |
| `add_channel_strategy_slide(title, channels)` | 채널별 전략 |
| `add_campaign_slide(title, campaign_name, period, objective, activities)` | 캠페인 |
| `add_budget_slide(title, budget_items, total)` | 예산 테이블 |
| `add_case_study_slide(title, case)` | 케이스 스터디 |

### 11.3 ChartGenerator (chart_generator.py)

타임라인, 조직도, 차트, KPI 카드, 경쟁사 비교 등의 시각화를 생성한다.

#### 주요 메서드

| 메서드 | 설명 |
|--------|------|
| `add_chart_slide(generator, title, chart_data, key_message)` | 차트 슬라이드 |
| `add_timeline_slide(generator, title, timeline_items, key_message)` | 타임라인 |
| `add_org_chart_slide(generator, title, org_chart, key_message)` | 조직도 |

python-pptx의 셰이프·텍스트박스를 직접 배치하는 방식으로 구현.

### 11.4 DiagramGenerator (diagram_generator.py)

프로세스 플로우, 피처 박스, KPI 대시보드, Before/After, 컨셉 다이어그램 등을 생성한다.

지원 다이어그램:
- **프로세스 플로우**: arrow / chevron / circle 스타일
- **피처 박스**: 3~4열 그리드
- **KPI 대시보드**: 숫자 강조 카드
- **Before/After 비교**
- **컨셉 다이어그램**: 중앙 + 주변 요소
- **경쟁 비교**: 바 차트

---

## 12. 유틸리티: src/utils/

### 12.1 logger.py

loguru 기반 로거 설정.

```python
def setup_logger(level=None):
    # 기존 핸들러 제거
    logger.remove()

    # Rich Progress와 겹치지 않도록 매 로그 앞에 줄바꿈 삽입
    def _sink_newline_first(message):
        if sys.stderr.isatty():
            sys.stderr.write("\n")
        sys.stderr.write(message)

    fmt = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
    logger.add(_sink_newline_first, format=fmt, level=level, colorize=True)

def get_logger(name: str):
    return logger.bind(name=name)  # 모듈별 이름 태그
```

**중요**: `main.py`에서 `load_dotenv()` → `get_settings()` → `setup_logger()` 순서로 호출해야 LOG_LEVEL 환경변수가 적용됨.

로그 구분 상수:
```python
LOG_SEPARATOR = "----------------------------------------------"
STEP_SEPARATOR = "══════════════════════════════════════════════════════════"
PHASE_SEPARATOR = "  ──────────────────────────────────────────"
```

### 12.2 path_utils.py

파일명 보안 정규화 및 경로 이탈 방지.

```python
def safe_filename(name: str, max_len: int = 100) -> str:
    # 공백 → 언더스코어, 슬래시 → 하이픈
    # 허용: 영숫자, 공백, 하이픈, 언더스코어, 마침표
    # max_len으로 자르기
    # 비어 있으면 "output" 반환

def safe_output_path(output_dir, base_name, suffix="", extension="") -> Path:
    # safe_filename 적용
    # resolve() 후 relative_to(output_dir) 검증
    # 경로 이탈 시 output_dir 기준으로 교정
```

출력 파일명 패턴: `{safe_project_name}_{YYYYMMDDHHmmssmmm}.pptx`

---

## 13. 프롬프트 파일: config/prompts/

### 13.1 rfp_analysis.txt

RFP 분석 전문 컨설턴트 역할 정의:
- 기본 정보 추출 (프로젝트명, 발주처, 예산, 기간)
- 요구사항 분석 (기능/비기능/기술/관리)
- 평가 기준 분석 (배점별 공략 포인트)
- 전략적 분석 (CSF, 리스크, Win Theme, 숨겨진 니즈)
- **Pain Point 추출 원칙**: "~해야 한다", "~이 필요하다" 표현에서 추출
- **Win Theme 후보 원칙**: 3개, 서로 다른 축 (데이터/분석, 실행력/전문성, 통합/시너지)
- **평가 기준 전략화**: 배점 25% 이상 → 최고 우선순위

### 13.2 content_guidelines.txt

모든 Phase 생성에 공통 적용되는 가이드라인:
- **Action Title**: 모든 슬라이드 제목을 인사이트 기반으로
- **Win Theme**: 3개 Win Theme이 각 Phase에서 어떻게 표현되는지
- **C-E-I 구조**: Claim(주장) → Evidence(근거 데이터) → Impact(정량적 효과)

### 13.3 Phase별 프롬프트 특징

| 파일 | Phase | 핵심 지침 |
|------|-------|----------|
| phase0_hook.txt | 0 HOOK | 감성+임팩트, 티저 슬라이드, Win Theme 암시, 비주얼 중심 |
| phase1_summary.txt | 1 SUMMARY | Executive Summary, 의사결정권자용 5분 요약, KPI 약속 |
| phase2_insight.txt | 2 INSIGHT | 시장 트렌드, Pain Point 공감, 데이터 기반 |
| phase3_concept.txt | 3 CONCEPT | 핵심 컨셉, 차별화 전략, 경쟁 비교 |
| phase4_action.txt | 4 ACTION | 구체성이 신뢰, 채널별 상세 계획, 실제 콘텐츠 예시 포함 |
| phase5_management.txt | 5 MANAGEMENT | 조직 체계, 품질 관리, 리포팅 체계 |
| phase6_whyus.txt | 6 WHY US | 유사 실적, 역량 증명, 수치화된 성과 |
| phase7_investment.txt | 7 INVESTMENT | 예산 상세, ROI, Next Step |

---

## 14. Impact-8 Framework 상세

### 14.1 8-Phase 구조

```
Phase 0: HOOK (티저)
  ├── 임팩트 있는 오프닝 (다크 배경, 대형 텍스트)
  ├── 시장/트렌드 변화 선언
  ├── 비전·슬로건 제시
  └── 표지 슬라이드

Phase 1: SUMMARY (Executive Summary)
  ├── 의사결정권자용 5분 핵심 요약
  ├── Win Theme 3개 제시
  ├── 핵심 KPI (산출 근거 포함)
  └── "왜 우리인가" 포인트

Phase 2: INSIGHT (시장 환경 & 문제 정의)
  ├── 시장 트렌드 분석
  ├── 타겟 오디언스 분석
  ├── Pain Point 공감
  └── 기회 발굴

Phase 3: CONCEPT & STRATEGY (핵심 컨셉 & 전략)
  ├── 우리만의 해결책 (컨셉 워드)
  ├── 차별화 전략
  ├── 경쟁사 비교 (AS-IS / TO-BE)
  └── 채널 역할 정의

Phase 4: ACTION PLAN (상세 실행 계획) ★핵심★
  ├── 전체 운영 로드맵 (연간/분기)
  ├── 채널별 상세 전략 (Instagram, YouTube 등)
  ├── 실제 콘텐츠 예시 (비주얼, 카피)
  ├── 캠페인 상세 기획
  ├── 인플루언서 협업 계획
  └── 일정표 (간트 차트, 타임테이블)

Phase 5: MANAGEMENT (운영 & 품질 관리)
  ├── 프로젝트 조직 체계
  ├── 품질 관리 프로세스
  ├── 리포팅 체계
  └── 리스크 관리

Phase 6: WHY US (수행 역량 & 실적)
  ├── 회사 역량 소개
  ├── 유사 프로젝트 실적 (수치화)
  ├── 전문 인력 프로필
  └── 수상/인증 실적

Phase 7: INVESTMENT & ROI (투자 & 기대효과)
  ├── 예산 내역 (항목별)
  ├── 정량적 기대효과 (ROI)
  ├── Next Step (Call to Action)
  └── 연락처 정보
```

### 14.2 Win Theme 시스템

Win Theme은 RFP 분석 시 발굴하고 제안서 전체에 반복적으로 등장하는 핵심 수주 전략 메시지다.

```python
class WinTheme(BaseModel):
    name: str              # 짧은 키워드 (예: "데이터 기반 타겟 마케팅")
    description: str       # 상세 설명
    evidence: List[str]    # 뒷받침 근거/증거
    related_phases: List[int]  # 주로 등장하는 Phase
```

Win Theme 3개 도출 원칙:
- 축 1: 데이터/분석/기술 역량
- 축 2: 실행력/전문성/실적
- 축 3: 통합/시너지/혁신

### 14.3 Action Title 가이드라인

```python
ACTION_TITLE_GUIDELINES = {
    "principles": [
        "슬라이드 내용의 결론/인사이트를 제목에 담기",
        "숫자나 구체적 데이터 포함 권장",
        "동사 또는 명사형 결론문으로 구성",
        "15-30자 내외로 간결하게"
    ],
    "examples": [
        # ❌ Topic Title → ✅ Action Title
        "사업 개요 및 목표" → "10개월간 브랜드 인지도 +20%p 달성이 핵심 과제",
        "타겟 분석" → "MZ세대 2030이 핵심, 하루 SNS 55분 사용",
        "차별화 포인트" → "유사 사업 130% 목표 초과 달성, 검증된 실행력 보유",
    ]
}
```

---

## 15. LLM 호출 메커니즘 상세

### 15.1 재시도 전략

```
API 에러 발생
  ├── 429 / RATE_LIMIT / OVERLOADED / TIMEOUT → 재시도 가능 에러
  │     └── wait = base_delay * (2^attempt) [지수 백오프]
  │         attempt 0: wait = 5초
  │         attempt 1: wait = 10초
  │         attempt 2: wait = 20초 (기본 3회)
  └── 기타 에러 → 즉시 RuntimeError 발생
```

Groq는 추가로 `413` 에러도 재시도 가능으로 처리.

### 15.2 Claude 호출 상세

```python
message = self._anthropic_client.messages.create(
    model=self._anthropic_model,
    max_tokens=max_tokens,
    temperature=temperature,
    system=system_prompt,
    messages=[{"role": "user", "content": user_message}],
)
result = message.content[0].text.strip()
```

빈 응답 감지 시 즉시 ValueError.

### 15.3 Gemini 호출 상세

```python
response = self.client.models.generate_content(
    model=self.model,
    contents=user_message,
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        max_output_tokens=max_tokens,
        temperature=temperature,
    )
)
result = response.text
```

할당량 초과(429/RESOURCE_EXHAUSTED) 시 전환 안내 메시지:
> "Gemini API 할당량 초과. .env에서 LLM_PROVIDER=groq 또는 LLM_PROVIDER=claude 로 바꾸세요."

### 15.4 Groq 호출 상세

```python
response = self._groq_client.chat.completions.create(
    model=self._groq_model,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ],
    max_tokens=max_tokens,
    temperature=temperature,
)
result = response.choices[0].message.content.strip()
```

**입력 크기 자동 조절**:
1. `GROQ_MAX_USER_MESSAGE_CHARS` 초과 시 user 메시지 절단
2. `_truncate_for_groq_limit()` 호출:
   - `reserve = min(max_tokens, 1024)` (응답 예약)
   - `input_limit = max(500, max_request_tokens - reserve)`
   - 한글 1토큰 ≈ 2자로 보수적 추정
   - user 메시지 먼저 절단 → 부족하면 system 프롬프트까지

### 15.5 LLM 호출 후 대기

모든 프로바이더에서 성공적인 응답 후 `llm_delay_seconds` (기본 8초) 대기.
무료 플랜의 RPM(Requests Per Minute) 한도 준수를 위함.

---

## 16. 슬라이드 유형 분류 체계

### 16.1 Phase별 주요 슬라이드 유형

| Phase | 주로 사용되는 slide_type |
|-------|------------------------|
| 0 HOOK | `teaser`, `key_message`, `title` |
| 1 SUMMARY | `content`, `two_column`, `executive_summary` |
| 2 INSIGHT | `content`, `chart`, `comparison`, `two_column` |
| 3 CONCEPT | `content`, `key_message`, `comparison`, `process` |
| 4 ACTION | `content`, `timeline`, `table`, `chart`, `content_example`, `channel_strategy`, `campaign` |
| 5 MANAGEMENT | `content`, `org_chart`, `table`, `process` |
| 6 WHY US | `content`, `case_study`, `table`, `two_column` |
| 7 INVESTMENT | `budget`, `table`, `chart`, `next_step` |

### 16.2 마케팅/PR 전용 슬라이드 유형

Phase 4 ACTION PLAN에서만 사용되는 특화 슬라이드:

**ContentExample (콘텐츠 예시)**:
```python
class ContentExample(BaseModel):
    platform: str          # "instagram", "youtube", "facebook"
    content_type: str      # "feed", "story", "reel", "shorts"
    title: str
    description: str
    visual_description: str  # 비주얼 설명
    copy_example: str        # 카피 예시
    hashtags: List[str]
    kpi_target: str
```

**ChannelStrategy (채널별 전략)**:
```python
class ChannelStrategy(BaseModel):
    channel_name: str
    role: str
    target_audience: str
    content_pillars: List[str]
    posting_frequency: str
    kpis: List[KPIItem]
```

**CampaignPlan (캠페인 계획)**:
```python
class CampaignPlan(BaseModel):
    campaign_name: str
    concept: str
    period: str
    objectives: List[str]
    target: str
    channels: List[str]
    key_activities: List[str]
    expected_results: List[str]
```

---

## 17. 디자인 시스템

### 17.1 기본 색상 팔레트

| 용도 | 색상 코드 | 설명 |
|------|----------|------|
| Primary | `#002C5F` | 다크 블루 (헤더, 섹션 구분자) |
| Secondary | `#00AAD2` | 스카이블루 (액센트, 차트) |
| Accent | `#E63312` | 액센트 레드 (강조, CTA) |
| Background | `#FFFFFF` | 흰색 배경 |
| Dark BG | `#1A1A1A` | 다크 배경 (티저 슬라이드) |
| Text Primary | `#333333` | 본문 텍스트 |
| Text Secondary | `#666666` | 보조 텍스트 |
| Text Light | `#FFFFFF` | 다크 배경 위 흰색 텍스트 |

### 17.2 타이포그래피

| 용도 | 폰트 | 크기 |
|------|------|------|
| 슬라이드 제목 | Pretendard | 44pt |
| 부제목 | Pretendard | 28pt |
| 본문 | Pretendard | 18pt |
| 캡션 | Pretendard | 14pt |
| 줄 간격 | - | 1.5배 |

### 17.3 레이아웃

- **슬라이드 크기**: 1920×1080 (16:9, `slide_width_inches=13.33`)
- **여백**: 상 80px, 하 60px, 좌우 100px 기준
- **섹션 구분자**: 전체 다크 배경, 중앙 정렬, 큰 아웃라인 Phase 번호
- **티저 슬라이드**: Cinematic 스타일, Gradient 다크 배경

### 17.4 테이블 스타일

- 헤더 배경: `#002C5F` (Primary)
- 헤더 텍스트: `#FFFFFF`
- 짝수 행 배경: 연한 회색 (alternate row)
- 테두리: minimal 스타일

---

## 18. 테스트 구조

### 18.1 테스트 파일 구성

```
tests/
├── conftest.py                     # pytest 픽스처 (settings mock 등)
├── test_base_agent_json.py         # BaseAgent._extract_json() 단위 테스트
├── test_path_utils.py              # safe_filename, safe_output_path 테스트
├── test_settings.py                # Settings 유효성 검사 테스트
├── test_template_manager.py        # TemplateManager 테스트
└── parsers/
    ├── test_get_parser.py          # get_parser_for_path() 테스트
    └── test_txt_parser.py          # TXTParser 단위 테스트
```

### 18.2 핵심 테스트 시나리오

**test_base_agent_json.py**:
- 정상 JSON 블록 추출 (`\`\`\`json ... \`\`\``)
- 중괄호만 있는 JSON 추출
- trailing comma 수정 후 파싱
- 마크다운 **key**: "value" 형식 복구
- 빈 응답 처리

**test_path_utils.py**:
- 한글 파일명 정규화
- 특수문자 제거
- 최대 길이 제한
- 경로 이탈 방지 (path traversal)

**test_settings.py**:
- 유효하지 않은 LLM_PROVIDER (ValueError)
- 범위 벗어난 max_tokens, temperature 등

### 18.3 실행 방법

```bash
pytest tests/
pytest tests/test_base_agent_json.py -v
pytest tests/ -k "json"
```

---

## 19. 핵심 설계 패턴 및 특징

### 19.1 LLM 프로바이더 전략 패턴

`BaseAgent`에서 프로바이더를 초기화 시 결정하고, `_call_llm()`에서 분기. 상위 코드는 프로바이더를 신경 쓰지 않아도 됨:

```python
# 사용 코드
response = self._call_llm(system_prompt, user_message)  # 프로바이더 무관
```

### 19.2 싱글톤 설정

```python
_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

프로그램 전체에서 단 하나의 Settings 인스턴스 사용.

### 19.3 프롬프트 파일 캐시

```python
def _load_prompt(self, prompt_name: str) -> str:
    if prompt_name in self._prompt_cache:
        return self._prompt_cache[prompt_name]
    # 디스크에서 읽기
    self._prompt_cache[prompt_name] = text
    return text
```

동일 Phase에 대해 여러 번 호출해도 디스크 I/O 1회.

### 19.4 폴백 체계

PPTX 생성 시 알 수 없는 슬라이드 유형이나 에러 발생 시 `add_content_slide()`로 폴백. 전체 생성이 중단되지 않도록 보장.

### 19.5 Phase별 진단 시스템

```python
diagnostics_out: List[Dict] = []
# ContentGenerator 내부에서 Phase 처리 후 추가:
diagnostics_out.append({
    "phase": phase_number,
    "phase_title": phase_title,
    "slides_count": len(slides),
    "elapsed_sec": round(elapsed, 2),
    "json_ok": json_success,
})
```

실행 후 `output/run_diagnostics_{timestamp}.json`으로 자동 저장.

### 19.6 Windows cp949 인코딩 에러 방지

Rich Console에서 한글을 출력할 때 Windows cp949 환경에서 에러 발생 가능. API 오류 메시지는 Rich Panel 대신 `print()` 직접 사용:

```python
try:
    print("제안서 생성 실패:", msg)
except Exception:
    print("Proposal generation failed. Check API key and quota.")
```

### 19.7 외부 Phase 프로파일 (hot-reload 가능 구조)

`config/phase_profiles.json`은 매 `get_config()` 호출 시 새로 로드. 코드 재시작 없이 Phase 설정 변경 가능 (단, 현재 실행 중인 LLM 호출에는 영향 없음).

### 19.8 파일명 보안

출력 파일명에 path traversal(`../`) 공격 방지:
- `safe_filename()`: 허용 문자만 남김
- `safe_output_path()`: `resolve()` + `relative_to()` 검증

### 19.9 로그 포맷 (loguru {} 스타일)

```python
# 올바른 방식 (loguru {} 스타일)
logger.info("RFP 파싱 완료: {} 문자", len(text))
logger.warning("오류 발생: {}: {}", type(e).__name__, str(e)[:200])

# 틀린 방식 (f-string은 피해야 하나 일부 혼재)
logger.info(f"파일: {path}")  # 성능상 불리하나 동작은 함
```

### 19.10 비동기 실행 구조

전체가 `asyncio.run()`으로 실행되지만 LLM 호출 자체는 동기(`time.sleep()` 포함). 현재 비동기의 실질적 이점은 Windows 인코딩 에러를 안전하게 처리하기 위한 예외 래핑에 있음:

```python
async def _generate_async(...):
    try:
        return await _generate_async_impl(...)
    except Exception as e:
        return ("error", e)   # 예외를 반환값으로 전달 (Windows 콘솔 인코딩 에러 방지)
```

---

*이 문서는 proposal-agent v3.6 소스코드 전체를 기반으로 작성되었습니다.*
