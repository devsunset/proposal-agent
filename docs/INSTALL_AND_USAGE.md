# 설치 및 사용 가이드

---

## 1. 사전 요구사항

| 항목 | 요구 버전 |
|------|----------|
| **Python** | 3.10 이상 |
| **pip** | 최신 버전 권장 |
| **LLM API** | Claude / Gemini / Groq 중 하나의 API 키 (CLI 방식 사용 시, .env의 LLM_PROVIDER에 맞춤) |

> **두 가지 방식으로 사용할 수 있습니다**
> - **① AI 코드 어시스턴트 방식** — Cursor 등 AI 도구에게 말로 시키면 RFP 분석부터 PPTX 생성까지 알아서 처리합니다.
> - **② CLI(API) 방식** — `python main.py generate` 명령어로 실행합니다. **.env에서 LLM_PROVIDER(claude/gemini/groq)와 해당 API 키**가 필요합니다.

---

## 2. 설치

### 2-1. 프로젝트 클론

```bash
git clone https://github.com/your-username/proposal-agent.git
cd proposal-agent
```

### 2-2. 가상환경 생성 (권장)

```bash
python3 -m venv venv
source venv/bin/activate    # macOS/Linux
# venv\Scripts\activate     # Windows
```

### 2-3. 의존성 설치

```bash
pip install -r requirements.txt
```

설치되는 패키지:

| 카테고리 | 패키지 | 용도 |
|---------|--------|------|
| AI | `anthropic` | Claude (Anthropic) API 호출 |
| AI | `google-genai` | Gemini API 호출 |
| AI | `groq` | Groq API 호출 |
| 문서 파싱 | `pypdf`, `pdfplumber` | PDF 텍스트/테이블 추출 |
| 문서 파싱 | `python-docx` | DOCX 파싱 |
| PPTX 생성 | `python-pptx` | 파워포인트 생성 |
| 데이터 검증 | `pydantic` | 스키마 검증 |
| CLI | `typer`, `rich` | 터미널 인터페이스 |
| 유틸 | `python-dotenv`, `loguru` | 환경변수, 로깅 |
| 차트 (선택) | `matplotlib`, `Pillow` | 차트 이미지 생성 |

### 2-4. API 키 설정 (② CLI 방식을 사용할 경우에만)

> **① AI 코드 어시스턴트 방식**을 사용한다면 이 단계는 건너뛰세요. 해당 도구가 자체 인증을 처리합니다.

`.env` 파일을 만듭니다. `cp .env.example .env` 후 값을 채우거나, 아래를 참고해 작성합니다. 사용할 LLM 하나를 선택한 뒤 해당 API 키를 입력합니다.

**사용할 LLM 선택 (claude | gemini | groq):**

```env
LLM_PROVIDER=gemini
```

**선택한 프로바이더에 맞는 키만 설정:**

- **Claude:** [Anthropic Console](https://console.anthropic.com)에서 발급  
  `ANTHROPIC_API_KEY=...`, `ANTHROPIC_MODEL=claude-3-5-sonnet-20241022`
- **Gemini:** [Google AI Studio](https://aistudio.google.com/apikey)에서 발급  
  `GEMINI_API_KEY=...`, `GEMINI_MODEL=gemini-2.5-flash-lite`
- **Groq:** [Groq Console](https://console.groq.com)에서 발급 (무료 한도 넉넉)  
  `GROQ_API_KEY=...`, `GROQ_MODEL=llama-3.1-8b-instant`

---

## 3. 사용법

### 방법 ① AI 코드 어시스턴트로 제안서 생성 (권장)

AI 코드 어시스턴트(Cursor 등)에게 자연어로 지시하면 RFP 분석부터 PPTX 생성까지 알아서 처리합니다.

```
사용자: "제안요청서 폴더의 테스트 01 파일을 분석한 후 제안서를 제작해줘"

AI가 자동으로 수행:
  1. RFP 문서(PDF/DOCX/TXT/PPTX)를 읽고 분석 (프로젝트 유형 자동 판별)
  2. Impact-8 구조로 콘텐츠 기획 + Win Theme 3개 도출
  3. PPTX 오케스트레이터(pptx_generator 등)를 활용한 제안서 생성
  4. 스크립트 실행 → PPTX 출력 (output/프로젝트명_제안서.pptx)
  5. QC 검수 후 문제 발견 시 자동 수정 → 재생성
```

**장점:**
- API 키 설정 불필요 (코드 어시스턴트 도구 자체 인증)
- 슬라이드별 레이아웃을 세밀하게 조정 가능
- 차트, 다이어그램, 이미지 플레이스홀더 직접 배치
- QC 후 즉시 수정/재생성
- 추가 요청으로 특정 슬라이드만 수정 가능

### 방법 ② CLI 명령어로 제안서 생성

> .env에 LLM_PROVIDER와 해당 API 키가 필요합니다 (2-4 단계 참조).

#### 제안서 생성 (기본)

```bash
python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처명"
```

| 옵션 | 설명 | 필수 |
|------|------|------|
| `input/rfp.pdf` | RFP 파일 경로 (PDF/DOCX/TXT/PPTX) | O |
| `-n` / `--name` | 프로젝트명 | O |
| `-c` / `--client` | 발주처명 | O |
| `-t` / `--type` | 프로젝트 유형 (아래 참조) | X (자동 판별) |
| `-o` / `--output` | 출력 디렉토리 | X (기본: output/) |

#### 프로젝트 유형 지정

```bash
python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처" -t marketing_pr
```

지원 유형:

| 유형 코드 | 설명 | Phase 4 비중 |
|----------|------|-------------|
| `marketing_pr` | 마케팅/PR/소셜미디어 | 40% |
| `event` | 이벤트/행사 | 45% |
| `it_system` | IT/시스템 구축 | 35% |
| `public` | 공공/입찰 | 30% |
| `consulting` | 컨설팅 | 30% |
| `general` | 일반 (기본값) | 35% |

유형을 지정하지 않으면 RFP 내용을 분석하여 **자동 판별**합니다.

#### RFP 분석만 수행

```bash
python main.py analyze input/rfp.pdf
```

제안서를 생성하지 않고 RFP 분석 결과만 확인합니다.
분석 결과: 프로젝트 개요, 핵심 요구사항, 평가 기준, 예산, 일정 등

#### 도움말

```bash
python main.py --help
python main.py generate --help
```

---

## 4. 실행 흐름

```
$ python main.py generate input/rfp.pdf -n "디지털 마케팅" -c "A공사"

  ┌─────────────────────────────────────────┐
  │  제안서 자동 생성 에이전트 v3.0     │
  │  Impact-8 Framework                     │
  └─────────────────────────────────────────┘

  Step 1: 콘텐츠 생성 (설정된 LLM - Impact-8)
  ✓ RFP 파싱 완료 (PDF/DOCX/TXT/PPTX)
  ✓ RFP 분석 완료 (프로젝트명·발주처·유형)
  ✓ Phase 0: HOOK 생성 완료
  ✓ Phase 1: SUMMARY 생성 완료
  ✓ Phase 2~7 생성 완료

  Step 2: PPTX 생성 (Modern 스타일)
  ✓ 슬라이드 생성 완료
  ✓ 저장: output/디지털_마케팅_YYYYMMDDHHmmssfff.pptx
```

---

## 5. 출력 결과물

### 폴더 구조

```
output/
  └── 프로젝트명_YYYYMMDDHHmmssfff.pptx   ← 최종 결과물 (타임스탬프로 유일 파일명)
```

### 제안서 구성 (Impact-8 Framework)

| Phase | 이름 | 비중 | 내용 |
|-------|------|------|------|
| 0 | HOOK | 5% | 표지 + 목차 + 임팩트 오프닝 |
| 1 | EXECUTIVE SUMMARY | 5% | 의사결정자용 요약 + Win Theme 3개 |
| 2 | INSIGHT | 12% | 시장 환경 + Pain Point + 기회 분석 |
| 3 | CONCEPT & STRATEGY | 12% | 핵심 컨셉 + 차별화 전략 |
| 4 | ACTION PLAN | **40%** | 상세 실행 계획 (제안서의 핵심) |
| 5 | MANAGEMENT | 8% | 조직 구성 + 품질관리 + 리포팅 |
| 6 | WHY US | 12% | 수행 역량 + 유사 실적 |
| 7 | INVESTMENT & ROI | 6% | 비용 + KPI + 기대효과 |

---

## 6. AI 코드 어시스턴트 활용 팁

> 기본 사용법은 **3. 사용법 → 방법 ①**을 참조하세요.

### 추가 요청 예시

```
"Phase 4 실행 계획 슬라이드를 더 상세하게 만들어줘"
"표지 디자인을 좀 더 임팩트 있게 바꿔줘"
"KPI 차트를 바 차트 대신 파이 차트로 변경해줘"
"전체적으로 틸 테마로 변경해줘"
```

### QC 요청 예시

```
"생성된 PPTX를 확인하고 겹치는 도형이나 빈 공간이 있으면 수정해줘"
"슬라이드 15번의 텍스트가 박스 밖으로 나가는 것 같아. 수정해줘"
```

AI 코드 어시스턴트는 스크립트를 수정하고 다시 실행하여 즉시 결과물을 갱신합니다.

---

## 7. PPTX 생성 구조

PPTX는 **TemplateManager** + **PPTXGenerator** + **ChartGenerator** + **DiagramGenerator**로 생성됩니다.

### 주요 구성

| 구성 요소 | 역할 |
|----------|------|
| **TemplateManager** | 템플릿 로드(`templates/*.pptx`), 레이아웃 인덱스(`slide_layouts.json`), 디자인 시스템(색상·폰트·간격). 로드한 PPTX 테마를 동적으로 추출해 적용 |
| **PPTXGenerator** | 표지·섹션 구분·콘텐츠·테이블·2/3단·키메시지·비교·목차·티저 등 슬라이드 생성 |
| **ChartGenerator** | 차트, 타임라인, 조직도, KPI 카드, 경쟁사 비교, ROI 시각화 |
| **DiagramGenerator** | 프로세스 플로우, 피처 박스, Before/After, 컨셉 다이어그램 |

### 템플릿/스타일

- `-T` / `--template` 미지정 시: 템플릿 파일을 사용하지 않고 **빈 프레젠테이션 + 기본 디자인 시스템**으로 제안서를 생성합니다(권장).
- `-T guide_template` 등으로 지정 시: `templates/guide_template.pptx`가 있으면 해당 파일을 사용하고, 없으면 templates/ 내 '가이드' 또는 'guide'가 포함된 .pptx를 찾습니다. 둘 다 없으면 빈 프레젠테이션에 코드 상 디자인 시스템이 적용됩니다.
- `templates/` 폴더는 로컬용으로 `.gitignore`에 포함될 수 있어, 커스텀 템플릿은 커밋하지 않고 사용할 수 있습니다.

### 사용 예시 (코드 레벨)

```python
from src.generators.template_manager import TemplateManager
from src.generators.pptx_generator import PPTXGenerator

tm = TemplateManager()
gen = PPTXGenerator(tm)
gen.create_presentation("guide_template")  # templates/guide_template.pptx 또는 가이드/빈 프레젠
# gen.add_title_slide(...), gen.add_content_slide(...) 등
gen.save("output/제안서.pptx")
```

---

## 8. 프롬프트 커스터마이징

### Phase별 프롬프트 수정

```
config/prompts/
├── content_guidelines.txt   ← 전체 공통 규칙
├── phase0_hook.txt          ← Phase 0 전용 지침
├── phase1_summary.txt
├── phase2_insight.txt
├── phase3_concept.txt
├── phase4_action.txt        ← 가장 상세 (40% 비중)
├── phase5_management.txt
├── phase6_whyus.txt
└── phase7_investment.txt
```

각 프롬프트 파일을 수정하면 해당 Phase의 생성 결과가 변경됩니다.

### 디자인 스타일 수정

`src/generators/template_manager.py`의 `_get_default_design_system()`에서 컬러·폰트·간격을 변경할 수 있습니다. 템플릿 PPTX를 로드하면 해당 파일의 테마(색상·폰트)가 동적으로 추출되어 디자인 시스템에 병합됩니다.

```python
# template_manager.py 예시
"colors": {
    "primary": RGBColor(0, 82, 147),
    "secondary": RGBColor(0, 150, 199),
    "accent": RGBColor(255, 107, 0),
    ...
}
```

---

## 9. 제안서 구조 커스터마이징

제안서 구조를 수정하는 방법을 항목별로 안내합니다.

### 9-1. Phase 비중 및 슬라이드 수 변경

`config/proposal_types.py`에서 프로젝트 유형별 Phase 구조를 수정합니다.

```python
# 예: 마케팅/PR 유형에서 Phase 4 비중 변경
4: PhaseConfig(
    title="ACTION PLAN",
    subtitle="상세 실행 계획",
    weight=0.40,          # ← 비중 (0.0~1.0, 전체 합 = 1.0)
    min_slides=30,        # ← 최소 슬라이드 수
    max_slides=60,        # ← 최대 슬라이드 수
    special_focus=[       # ← 이 Phase에서 강조할 요소
        "채널별 상세 전략",
        "캠페인 상세 기획",
        "실제 콘텐츠 예시",
    ]
),
```

**주의사항:**
- 모든 Phase의 `weight` 합이 **1.0**이 되어야 합니다
- `min_slides`와 `max_slides`는 `weight`에 비례하게 조정하세요

### 9-2. 새로운 프로젝트 유형 추가

```python
# config/proposal_types.py

# 1단계: Enum에 유형 추가
class ProposalType(str, Enum):
    MARKETING_PR = "marketing_pr"
    EVENT = "event"
    # ... 기존 유형들
    MEDIA = "media"            # ← 새 유형

# 2단계: Config 정의
MEDIA_CONFIG = ProposalTypeConfig(
    type_name="미디어/방송",
    description="미디어 제작, 방송 콘텐츠, 영상 제작",
    total_pages_range=(60, 100),
    phases={
        0: PhaseConfig(title="HOOK", subtitle="오프닝",
                       weight=0.05, min_slides=3, max_slides=5),
        # ... Phase 1~7 정의
    },
    special_features=["포맷 기획서", "편성 전략", "제작 일정"]
)

# 3단계: 매핑에 등록
PROPOSAL_TYPE_CONFIGS[ProposalType.MEDIA] = MEDIA_CONFIG
```

### 9-3. Phase별 콘텐츠 생성 규칙 변경

`config/prompts/` 폴더의 프롬프트 파일을 수정하면 AI 생성 결과가 변경됩니다.

| 파일 | 역할 | 수정 시 영향 |
|------|------|------------|
| `content_guidelines.txt` | 전체 공통 규칙 | Action Title, Win Theme, C-E-I 등 전체 톤 변경 |
| `phase0_hook.txt` | 오프닝/티저 | 표지, 임팩트 슬라이드 스타일 |
| `phase1_summary.txt` | Executive Summary | Win Theme 정의 방식 |
| `phase2_insight.txt` | 시장 분석 | 인사이트 도출 깊이 |
| `phase3_concept.txt` | 컨셉 & 전략 | 전략 프레임워크 구조 |
| `phase4_action.txt` | 실행 계획 (핵심) | 세부 실행 항목, 콘텐츠 예시 |
| `phase5_management.txt` | 운영 관리 | 조직도, 품질관리 체계 |
| `phase6_whyus.txt` | 수행 역량 | 실적/포트폴리오 구성 |
| `phase7_investment.txt` | 투자 & ROI | KPI, 기대효과 산출 방식 |

**수정 예시 — Phase 4에 새로운 강조 항목 추가:**

```text
# phase4_action.txt 끝에 추가

## 추가 필수 포함 항목
- ESG 연계 전략
- 지속가능성 KPI
```

### 9-4. 디자인 스타일 변경

`src/generators/template_manager.py`의 `_get_default_design_system()`에서 컬러·폰트·간격을 수정합니다. 템플릿 PPTX를 사용할 경우 해당 파일의 테마가 추출되어 디자인 시스템에 반영됩니다.

### 9-5. 슬라이드 레이아웃 변경

레이아웃 인덱스는 `src/generators/template_manager.py`의 `_load_layouts()`에서 정의됩니다. `templates/slide_layouts.json`이 있으면 해당 설정을 사용하고, 없으면 `_default_layouts()`의 기본 인덱스(title, section, content, two_column, comparison, blank)를 사용합니다. 슬라이드 유형별 생성 로직은 `src/orchestrators/pptx_orchestrator.py`의 `_add_content_slide()`에서 분기하며, `src/generators/pptx_generator.py`, `chart_generator.py`, `diagram_generator.py`를 호출합니다.

### 9-6. Win Theme 커스터마이징

Win Theme은 제안서 전체에 반복되는 3대 핵심 전략 메시지입니다.

- **자동 생성** (기본): RFP 분석 결과에서 AI가 자동 도출
- **수동 지정**: 생성 스크립트에서 직접 정의

```python
WIN = {
    "data": "데이터 기반 타겟 마케팅",
    "community": "시민 참여형 브랜드 빌딩",
    "integration": "온-오프라인 통합 시너지",
}
```

Win Theme 규칙은 `content_guidelines.txt`에서 조정:
- Phase 1에서 정의 → Phase 2~7에서 반복
- 섹션 구분자에 관련 Win Theme 뱃지 표시
- Phase 6에서 Win Theme별 증거 매핑

### 9-7. 전체 구조 수정 요약

| 수정 목적 | 수정 파일 |
|----------|----------|
| Phase 비중/슬라이드 수 변경 | `config/proposal_types.py` |
| 새 프로젝트 유형 추가 | `config/proposal_types.py` (Enum, Config, PROPOSAL_TYPE_CONFIGS) |
| AI 생성 콘텐츠 규칙 변경 | `config/prompts/phase*.txt` |
| 전체 톤/스타일 규칙 변경 | `config/prompts/content_guidelines.txt` |
| 컬러/폰트/디자인 변경 | `src/generators/template_manager.py` (`_get_default_design_system`) |
| 슬라이드 레이아웃 수정 | `templates/slide_layouts.json` 또는 `template_manager._default_layouts()` |
| Win Theme 전달 방식 변경 | `src/agents/content_generator.py` |
| RFP 분석 항목 변경 | `src/agents/rfp_analyzer.py` |
| 데이터 모델 변경 | `src/schemas/proposal_schema.py`, `src/schemas/rfp_schema.py` |

---

## 10. 트러블슈팅

### API 키 오류 (② CLI 방식만 해당)

```
ANTHROPIC_API_KEY / GEMINI_API_KEY / GROQ_API_KEY가 설정되지 않았습니다.
```

해결: `.env`에서 `LLM_PROVIDER`와 선택한 프로바이더에 맞는 키가 있는지 확인

```bash
# 예: LLM_PROVIDER=groq 이면 GROQ_API_KEY=... 필수
cat .env
```

> ① AI 코드 어시스턴트 방식을 사용 중이라면 API 키가 필요하지 않으므로 이 오류는 발생하지 않습니다.

### PDF 파싱 오류

```
PDF 파싱에 실패했습니다.
```

해결:
- PDF가 텍스트 기반인지 확인 (이미지 스캔 PDF는 미지원)
- PDF 파일이 암호화되어 있지 않은지 확인
- 다른 PDF 뷰어에서 정상적으로 열리는지 확인

### PPTX 생성 오류

```
python-pptx 관련 오류
```

해결:
```bash
pip install --upgrade python-pptx
```

### 토큰 한도 초과

Phase 4 (ACTION PLAN)에서 토큰 한도에 도달할 수 있습니다.

해결: `src/agents/content_generator.py`에서 `max_tokens` 조정

```python
max_tokens = 16384 if phase_num == 4 else 8192
```

---

## 11. 디렉토리 구조

```
proposal-agent/
├── main.py                        # CLI (generate, analyze, types, info, templates)
├── .env.example                   # 환경 변수 예시 (복사 후 .env로 사용)
├── config/
│   ├── settings.py                # API 키·LLM 선택·경로·재시도/토큰
│   ├── proposal_types.py         # 제안서 유형 6종·가중치
│   └── prompts/                   # Phase별 프롬프트
├── src/
│   ├── parsers/                   # get_parser_for_path, PDF/DOCX/TXT/PPTX
│   ├── agents/                    # base_agent, rfp_analyzer, content_generator
│   ├── schemas/                   # proposal_schema, rfp_schema
│   ├── generators/                # template_manager, pptx_generator, chart_generator, diagram_generator
│   ├── orchestrators/             # proposal_orchestrator, pptx_orchestrator
│   └── utils/                     # logger, path_utils (safe_filename, safe_output_path)
├── tests/                         # pytest (parsers, path_utils, settings, template_manager 등)
├── templates/                     # PPTX 템플릿 (선택, .gitignore 대상)
├── company_data/                  # 회사 정보 JSON
├── input/                         # RFP 입력
├── output/                        # PPTX 출력
└── docs/                          # 가이드 문서
```

---

## 12. 빠른 시작 체크리스트

### ① AI 코드 어시스턴트 방식

```
[ ] Python 3.10+ 설치 확인
[ ] git clone 완료
[ ] pip install -r requirements.txt
[ ] input/ 폴더에 RFP PDF 배치
[ ] AI 코드 어시스턴트에게 "input 폴더의 RFP를 분석한 후 제안서를 제작해줘" 요청
[ ] output/ 폴더에서 PPTX 결과물 확인
```

### ② CLI(API) 방식

```
[ ] Python 3.10+ 설치 확인
[ ] git clone 완료
[ ] pip install -r requirements.txt
[ ] .env에 LLM_PROVIDER(claude/gemini/groq)와 해당 *_API_KEY 설정
[ ] input/ 폴더에 RFP PDF 배치
[ ] python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처" 실행
[ ] output/ 폴더에서 PPTX 결과물 확인
```
