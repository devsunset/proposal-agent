# Proposal Agent — 동작 방식 (Process)

이 문서는 **제안서 자동 생성 에이전트**가 RFP 문서를 입력받아 PPTX 제안서를 만들 때, 내부에서 어떤 순서로 어떤 컴포넌트가 동작하는지 **깊이 있고 상세하게** 기술합니다.

---

## 1. 개요

- **목적**: RFP(제안요청서) 파일(PDF/DOCX/TXT/PPTX)을 입력받아 **Impact-8 구조**의 PPTX 제안서를 자동 생성.
- **역할 분리**:
  - **LLM(Claude / Gemini / Groq)**: RFP 분석, Phase 0~7 콘텐츠 생성. `.env`의 `LLM_PROVIDER`로 한 종류만 선택.
  - **PPTX 레이어**: `ProposalContent`(JSON 구조)를 Modern 스타일 PPTX로 렌더링.

---

## 2. 진입점: CLI (main.py)

- **엔트리**: `python main.py <command> [options]`
- **.env 로드**: `load_dotenv()`가 가장 먼저 실행되어 `config.settings`가 올바른 `LLM_PROVIDER`·API 키를 읽음.
- **로거**: `setup_logger()`로 전역 로깅 설정 (환경 변수 `LOG_LEVEL` 사용).

### 2.1 지원 명령

| 명령 | 설명 |
|------|------|
| `generate` | RFP 경로 → 콘텐츠 생성(Step 1) → PPTX 생성(Step 2) → 파일 저장 |
| `analyze` | RFP 경로 → 파싱 → RFP 분석(LLM)만 수행, PPTX 미생성 |
| `types` | 지원 제안서 유형 목록 출력 |
| `templates` | 사용 가능한 PPTX 템플릿 목록 출력 |
| `info` | Impact-8 Framework 설명 출력 |

### 2.2 generate 실행 시 인자 처리

- **필수**: `rfp_path` (RFP 파일 경로).
- **옵션**: `--name`/`-n`(프로젝트명), `--client`/`-c`(발주처), `--type`/`-t`(제안서 유형), `--company`/`-d`(회사 정보 JSON), `--output`/`-o`(출력 디렉터리), `--template`/`-T`(템플릿 파일명, 확장자 제외), `--save-json`.
- **API 키 검사**: `LLM_PROVIDER`에 따라 `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` / `GROQ_API_KEY` 중 해당 키가 없으면 에러 메시지 출력 후 종료(Exit 1).
- **제안서 유형 검증**: `-t`로 준 값이 `config.proposal_types.ProposalType`에 없으면 에러 후 종료.

이후 **비동기** `_generate_async` → `_generate_async_impl`이 실제 2단계(콘텐츠 생성 → PPTX 생성)를 수행합니다.

---

## 3. 설정 (config)

### 3.1 config/settings.py

- **Settings**: Pydantic `BaseModel`, 환경 변수 기반.
- **LLM_PROVIDER**: `claude` | `gemini` | `groq` 중 하나. 이 값에 따라 사용할 API 클라이언트·모델·API 키가 결정됨.
- **API 키·모델**: `ANTHROPIC_*`, `GEMINI_*`, `GROQ_*` 등. Groq는 `GROQ_MAX_USER_MESSAGE_CHARS`로 사용자 메시지 길이 제한 가능.
- **로깅**: `LOG_LEVEL` (DEBUG/INFO/WARNING/ERROR).
- **LLM 공통**: `LLM_MAX_TOKENS`, `LLM_TEMPERATURE`, `LLM_RETRY_COUNT`, `LLM_RETRY_BASE_DELAY`, `LLM_DELAY_SECONDS` (429·일시 오류 대응).
- **경로**: `prompts_dir`, `templates_dir` 등. `get_settings()`로 싱글톤처럼 사용.

### 3.2 config/proposal_types.py

- **ProposalType**: `marketing_pr`, `event`, `it_system`, `public`, `consulting`, `general`.
- **PhaseConfig**: Phase별 title, subtitle, weight, min/max 슬라이드 수, special_focus 등.
- **ProposalTypeConfig**: 유형별 전체 설정(Phase 가중치, 총 페이지 범위, 특화 기능).
- **phase_profiles.json**: 있으면 외부에서 유형별 설정 로드(선택).
- **get_config(type)**, **get_phase_config(type, phase_num)**, **get_type_display_name(type)**, **calculate_pages()**, **get_prompt_file()** 등으로 Phase 비중·프롬프트 파일 경로 결정.

---

## 4. 전체 실행 흐름 (generate)

```
[사용자] python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처"
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  main.py                                                                  │
│  · .env 로드, API 키·유형 검증, 출력 디렉터리 생성                        │
│  · asyncio.run(_generate_async(...))                                      │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Step 1: 콘텐츠 생성 (ProposalOrchestrator)                                │
│  · RFP 파싱 → 회사 데이터 로드 → RFP 분석(LLM) → 제안서 콘텐츠 생성(LLM)   │
│  · 결과: ProposalContent (메모리)                                         │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  main.py 중간 처리                                                         │
│  · 요약·진단 출력, run_diagnostics 저장, --save-json 시 JSON 저장          │
│  · 출력 파일명: safe_output_path(프로젝트명, suffix=타임스탬프, .pptx)     │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Step 2: PPTX 생성 (PPTXOrchestrator)                                     │
│  · create_presentation(template) → 티저 슬라이드 → Phase 1~7 슬라이드      │
│  · generator.save(output_path)                                            │
└──────────────────────────────────────────────────────────────────────────┘
           │
           ▼
[결과] output/프로젝트명_YYYYMMDDHHmmssfff.pptx
```

---

## 5. Step 1 상세: 콘텐츠 생성 (ProposalOrchestrator)

`ProposalOrchestrator.execute()`가 다음 4단계를 순서대로 수행합니다.

### 5.1 1단계: 문서 파싱

- **입력**: `rfp_path` (파일 경로).
- **동작**: `get_parser_for_path(rfp_path)`로 확장자에 맞는 파서 인스턴스 선택 (.pdf → PDFParser, .docx/.doc → DOCXParser, .txt → TXTParser, .pptx → PPTXParser). 지원 확장자 외면 `ValueError`.
- **파서.parse(path)**: 해당 포맷에 맞게 텍스트·테이블·섹션 등 추출.
- **출력**: `parsed_rfp` (딕셔너리). 키 예: `raw_text`, `tables`, `sections`, `metadata` 등.

### 5.2 2단계: 회사 데이터 로드

- **입력**: `company_data_path` (예: `company_data/company_profile.json`). 없거나 미전달 시 생략.
- **동작**: JSON 파일을 UTF-8로 읽어 딕셔너리로 로드. 실패 시 예외.
- **출력**: `company_data` (dict). 이후 LLM 프롬프트·제안서 메타에 활용.

### 5.3 3단계: RFP 분석 (RFPAnalyzer)

- **입력**: `parsed_rfp`, (선택) progress_callback.
- **동작**:
  - 프롬프트: `config/prompts/rfp_analysis.txt` 또는 기본 시스템 프롬프트.
  - `raw_text`는 길이 제한(예: 25000자) 적용, tables는 상위 N개만 JSON 직렬화 후 LLM에 전달.
  - BaseAgent 공통 로직으로 **설정된 LLM**(Claude/Gemini/Groq) 1회 호출.
  - 응답에서 JSON 블록 추출 후 camelCase → snake_case 등 키 정규화(RFP_KEY_ALIASES).
  - Pydantic 모델로 파싱해 **RFPAnalysis** 인스턴스 반환.
- **RFPAnalysis 주요 필드**: project_name, client_name, project_overview, project_type, key_requirements, evaluation_criteria, deliverables, timeline, budget, winning_strategy, win_theme_candidates, pain_points, hidden_needs 등.
- **프로젝트명/발주처**: CLI에서 넘긴 값이 있으면 우선, 없으면 `rfp_analysis.project_name` / `client_name` 사용.

### 5.4 4단계: 제안서 콘텐츠 생성 (ContentGenerator)

- **입력**: rfp_analysis, company_data, project_name, client_name, submission_date, proposal_type(optional), progress_callback, diagnostics_out.
- **동작**:
  - **제안서 유형 결정**: `_determine_proposal_type()` — CLI 또는 RFP의 project_type, 없으면 general 등.
  - **Phase 가중치**: `get_phase_weights(proposal_type)` (proposal_schema 또는 proposal_types 연동).
  - **Phase 0 (HOOK)**: `_generate_teaser()` — 티저용 슬로건·메시지·슬라이드 리스트 생성. TeaserContent 반환.
  - **Phase 1 (SUMMARY)**: `_generate_phase_with_raw()` — Executive Summary·Win Theme 등. Phase 1 응답에서 **Win Theme 3개** 추출(`_extract_win_themes()`). 없으면 RFP의 win_theme_candidates 사용.
  - **Phase 2~7**: 루프에서 `_generate_phase(phase_num, ..., win_themes=win_themes)` 호출. 각 Phase별 프롬프트는 `config/proposal_types.get_prompt_file()` 또는 schema의 PHASE_DEFINITIONS 등과 연동. Phase별로 PhaseContent(phase_number, phase_title, slides 등) 생성.
  - **진단**: 각 Phase 소요 시간·슬라이드 수·JSON 성공 여부를 `diagnostics_out`에 추가. 이후 `get_run_diagnostics()`로 조회 가능.
- **출력**: **ProposalContent**. 필드 예: project_name, client_name, submission_date, company_name, proposal_type, slogan, one_sentence_pitch, key_differentiators, teaser(TeaserContent), phases(List[PhaseContent]), design_style 등.

### 5.5 Step 1 완료 후 (main.py)

- 콘텐츠 요약 테이블 출력 (`get_proposal_summary()`).
- Phase별 진단 테이블 출력 및 `output_dir/run_diagnostics_YYYYMMDDHHmmss.json` 저장(가능 시).
- `--save-json`이면 `save_content_json(content, json_path)`로 ProposalContent를 JSON 파일로 저장.
- **최종 출력 PPTX 경로**: `safe_output_path(output_dir, final_project_name, suffix=타임스탬프, extension=".pptx")` → `프로젝트명_YYYYMMDDHHmmssfff.pptx`.

---

## 6. Step 2 상세: PPTX 생성 (PPTXOrchestrator)

`PPTXOrchestrator.execute(content, output_path, template_name, progress_callback)`가 다음 순서로 동작합니다.

### 6.1 프레젠테이션 초기화

- **template_name**: CLI `-T`로 지정한 값 또는 `_default_template_for_proposal_type(content.proposal_type.value)`. None/빈 문자열이면 **템플릿 미사용**(빈 프레젠테이션 + 기본 디자인 시스템).
- **동작**: `PPTXGenerator.create_presentation(template_name or "")` → 내부에서 `TemplateManager.load_template(template_name)`.
  - 빈 문자열: 빈 Presentation 생성, TemplateManager의 `_get_default_design_system()`으로 색·폰트·간격 적용.
  - 값이 있으면: `templates_dir`에서 해당 이름의 .pptx 로드. 'guide' 또는 '가이드' 포함 파일 자동 선택 로직 있을 수 있음. 로드된 PPTX의 테마(색상·폰트)·슬라이드 크기·플레이스홀더 위치를 추출해 design_system·레이아웃 정보로 사용.

### 6.2 티저 슬라이드 (Phase 0)

- **입력**: `content.teaser` (TeaserContent).
- **동작**: `_add_teaser_slides(teaser, content)`.
  - teaser.slides 각 항목의 `slide_type`에 따라:
    - `teaser`: `add_teaser_slide(headline, subheadline, background_color="dark_blue", notes)`.
    - `title`: `add_title_slide(project_name, subtitle, slogan, is_part_divider=False)` (subtitle에 client_name, submission_date, company_name 조합).
  - 예외 시 표지 슬라이드로 대체.

### 6.3 Phase 1~7 슬라이드

- **입력**: `content.phases` (PhaseContent 리스트).
- **동작**: Phase 순서대로 `_add_phase_slides(phase, content)` 호출.
  - **섹션 구분자**: 해당 Phase의 첫 슬라이드가 section_divider가 아니면, 먼저 `add_section_divider(phase_number, phase_title, phase_subtitle)` 호출.
  - **Phase 내 각 슬라이드**: `_add_content_slide(slide, phase_number)`로 처리.

### 6.4 슬라이드 유형별 분기 (_add_content_slide)

| slide_type | 처리 |
|------------|------|
| section_divider | add_section_divider |
| content | add_content_slide |
| two_column | add_two_column_slide |
| three_column | add_three_column_slide (left/center/right 제목·내용) |
| table | add_table_slide (테이블 없으면 content로 대체) |
| chart | ChartGenerator.add_chart_slide |
| timeline | ChartGenerator.add_timeline_slide |
| org_chart | ChartGenerator.add_org_chart_slide |
| comparison | add_comparison_slide (as_is / to_be) |
| key_message | add_key_message_slide |
| content_example | add_content_example_slide |
| channel_strategy | add_channel_strategy_slide |
| campaign | add_campaign_slide |
| budget | add_budget_slide |
| case_study | add_case_study_slide |
| teaser | add_teaser_slide |
| index | add_index_slide |
| process | DiagramGenerator.add_process_slide |
| 기타 | add_content_slide로 폴백 |

예외 발생 시 해당 슬라이드는 **add_content_slide**로 폴백해 PPTX 생성이 중단되지 않도록 함.

### 6.5 저장

- `PPTXGenerator.save(output_path)` → python-pptx `Presentation.save()`.
- 반환값: `output_path`.

---

## 7. 데이터 스키마 흐름

```
[RFP 파일]
    │
    ▼  parsers (PDF/DOCX/TXT/PPTX)
[parsed_rfp: dict]
    raw_text, tables, sections, ...
    │
    ▼  RFPAnalyzer (LLM 1회)
[RFPAnalysis]
    project_name, client_name, project_overview, project_type,
    key_requirements, evaluation_criteria, deliverables,
    winning_strategy, win_theme_candidates, ...
    │
    ▼  ContentGenerator (LLM Phase 0~7)
[ProposalContent]
    project_name, client_name, proposal_type, teaser, phases[], ...
    │
    ▼  PPTXOrchestrator + PPTXGenerator / ChartGenerator / DiagramGenerator
[.pptx 파일]
```

- **RFPAnalysis** (rfp_schema): 평가 기준, 요구사항, 산출물, 일정, 예산, 수주 전략 등.
- **ProposalContent** (proposal_schema): Impact-8 전체 구조. TeaserContent, PhaseContent[], 각 Phase의 SlideContent[] (title, subtitle, bullets, slide_type, table, chart, timeline, comparison 등).
- **SlideType** 열거형: content, two_column, three_column, table, chart, timeline, org_chart, comparison, key_message, content_example, channel_strategy, campaign, budget, case_study, process, section_divider, executive_summary, next_step 등.

---

## 8. 컴포넌트 역할 요약

| 계층 | 컴포넌트 | 역할 |
|------|----------|------|
| CLI | main.py | 명령 파싱, API 키·유형 검증, 2단계 호출, 진행 표시, 결과 출력 |
| 설정 | config.settings | LLM 프로바이더·API 키·모델·재시도·경로 등 전역 설정 |
| 설정 | config.proposal_types | 제안서 유형·Phase 가중치·프롬프트 파일 경로 |
| 파싱 | src.parsers | get_parser_for_path → PDF/DOCX/TXT/PPTX 파서 → parse() → dict |
| 에이전트 | BaseAgent | LLM 호출 공통(Claude/Gemini/Groq), 재시도, JSON 추출, 키 정규화 |
| 에이전트 | RFPAnalyzer | RFP 텍스트·테이블 → RFPAnalysis |
| 에이전트 | ContentGenerator | RFPAnalysis + 회사 데이터 → Phase 0~7 → ProposalContent |
| 오케스트레이션 | ProposalOrchestrator | 파싱 → 회사 데이터 로드 → RFP 분석 → 콘텐츠 생성 |
| 오케스트레이션 | PPTXOrchestrator | ProposalContent → 티저 + Phase별 슬라이드 추가 → 저장 |
| 생성기 | TemplateManager | 템플릿 .pptx 로드, 테마 추출, design_system, 레이아웃 인덱스 |
| 생성기 | PPTXGenerator | create_presentation, add_*_slide (title, content, table, 2/3단, comparison, teaser, key_message, index, content_example, channel_strategy, campaign, budget, case_study, executive_summary, next_step 등), save |
| 생성기 | ChartGenerator | add_chart_slide, add_timeline_slide, add_org_chart_slide (KPI 카드, 경쟁 비교 등) |
| 생성기 | DiagramGenerator | add_process_slide (프로세스 플로우) |
| 유틸 | logger, path_utils | 로깅, safe_filename, safe_output_path |

---

## 9. analyze 명령

- **흐름**: RFP 경로 → `get_parser_for_path` → `parse()` → `RFPAnalyzer.execute(parsed)` → RFPAnalysis 반환.
- **출력**: 파싱 문자 수, RFP 분석 결과 패널(프로젝트명, 발주처, 개요, 요구사항·평가 기준·산출물 개수, 수주 전략 등). PPTX 생성 없음.

---

## 10. 출력 및 파일명 규칙

- **PPTX**: `output_dir / safe_filename(프로젝트명)_YYYYMMDDHHmmssfff.pptx`. 타임스탬프로 유일 보장.
- **진단 JSON**: `output_dir/run_diagnostics_YYYYMMDDHHmmss.json` (generate 시, 선택 저장).
- **콘텐츠 JSON**: `--save-json` 시 `output_dir/프로젝트명_content.json` 형태로 ProposalContent 저장.

---

## 11. 환경 변수 요약

| 변수 | 용도 |
|------|------|
| LLM_PROVIDER | claude \| gemini \| groq (하나만) |
| ANTHROPIC_API_KEY, GEMINI_API_KEY, GROQ_API_KEY | 선택된 프로바이더에 맞는 키 |
| LOG_LEVEL | DEBUG, INFO, WARNING, ERROR |
| LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_RETRY_COUNT, LLM_DELAY_SECONDS 등 | LLM 호출 제어 |

이 문서는 위와 같은 순서와 데이터 흐름으로 에이전트가 동작하도록 정리한 것입니다. 코드 변경 시 이 파일을 함께 현행화하는 것을 권장합니다.
