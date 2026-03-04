# 설치 및 사용 가이드 (v4.0)

---

## 1. 사전 요구사항

| 항목 | 요구 버전 |
|------|----------|
| **Python** | 3.10 이상 |
| **pip** | 최신 버전 권장 |
| **LLM API** | Claude / Gemini / Groq 중 하나의 API 키 (.env의 LLM_PROVIDER에 맞춤) |

> **두 가지 방식으로 사용할 수 있습니다**
> - **① AI 코드 어시스턴트 방식** — Cursor 등 AI 도구에게 말로 시키면 RFP 분석부터 PPTX 생성까지 자동 처리
> - **② CLI(API) 방식** — `python main.py generate` 명령어로 실행. `.env`의 LLM_PROVIDER와 API 키 필요

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

설치되는 주요 패키지:

| 카테고리 | 패키지 | 용도 |
|---------|--------|------|
| AI | `anthropic`, `google-genai`, `groq` | LLM API 호출 |
| 문서 파싱 | `pypdf`, `pdfplumber`, `python-docx` | PDF/DOCX 파싱 |
| PPTX 생성 | `python-pptx` | 파워포인트 생성 |
| 데이터 검증 | `pydantic` | 스키마 검증 |
| CLI | `typer`, `rich` | 터미널 인터페이스 |
| 유틸 | `python-dotenv`, `loguru` | 환경변수, 로깅 |
| 차트 (선택) | `matplotlib`, `Pillow` | 차트 이미지 생성 |

### 2-4. API 키 설정

`.env` 파일을 만듭니다. `cp .env.example .env` 후 값을 채웁니다.

```env
# 사용할 LLM 선택 (하나만)
LLM_PROVIDER=gemini

# Claude 사용 시
# ANTHROPIC_API_KEY=...
# ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Gemini 사용 시
# GEMINI_API_KEY=...
# GEMINI_MODEL=gemini-2.5-flash-lite

# Groq 사용 시 (무료 한도 넉넉)
# GROQ_API_KEY=...
# GROQ_MODEL=llama-3.1-8b-instant
```

---

## 3. 사용법

### 방법 ① AI 코드 어시스턴트로 제안서 생성 (권장)

```
사용자: "제안요청서 폴더의 테스트 01 파일을 분석한 후 제안서를 제작해줘"

AI가 자동으로 수행:
  1. RFP Chunking으로 평가기준·요구사항 우선 파싱 (최대 40,000자)
  2. Impact-8 구조로 콘텐츠 기획 + Win Theme 3개 도출
  3. Cross-Phase Context + Industry Stats 주입으로 일관성 있는 제안서 생성
  4. PPTX 렌더링 (폰트 폴백 적용)
  5. Slide Quality Score 확인 → 품질 미달 슬라이드 수정
```

### 방법 ② CLI 명령어

#### (최초 1회) 회사 프로필 설정

```bash
python main.py setup-company
```

회사 정보를 대화형으로 입력하면 `company_data/company_profile.json`이 생성됩니다.
이후 모든 제안서의 **Phase 6(WHY US)**에 실제 역량·실적이 자동 반영됩니다.

#### 제안서 생성

```bash
python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처명"
```

| 옵션 | 설명 | 필수 |
|------|------|------|
| `input/rfp.pdf` | RFP 파일 경로 | O |
| `-n` / `--name` | 프로젝트명 | O |
| `-c` / `--client` | 발주처명 | O |
| `-t` / `--type` | 제안서 유형 | X (자동 판별) |
| `-d` / `--company` | 회사 정보 JSON | X (기본: company_data/company_profile.json) |
| `-o` / `--output` | 출력 디렉토리 | X (기본: output/) |
| `-T` / `--template` | PPTX 템플릿 파일명 | X (미지정 시 기본 디자인) |
| `--save-json` | 콘텐츠 JSON 저장 | X |

#### 제안서 유형

| 유형 코드 | 설명 | Phase 4 비중 |
|----------|------|-------------|
| `marketing_pr` | 마케팅/PR/소셜미디어 | 40% |
| `event` | 이벤트/행사 | 45% |
| `it_system` | IT/시스템 구축 | 35% |
| `public` | 공공/입찰 | 30% |
| `consulting` | 컨설팅 | 30% |
| `general` | 일반 (기본값) | 35% |

#### RFP 분석만 수행

```bash
python main.py analyze input/rfp.pdf
```

---

## 4. 실행 흐름

```
$ python main.py generate input/rfp.pdf -n "디지털 마케팅" -c "A공사"

┌─────────────────────────────────────────┐
│  제안서 자동 생성 에이전트 v4.0          │
│  Impact-8 Framework                     │
└─────────────────────────────────────────┘

Step 1: 콘텐츠 생성 (LLM - Impact-8)
  ✓ RFP 파싱 완료
  ✓ RFP Chunking 적용 (평가기준·요구사항 우선)
  ✓ RFP 분석 완료 (Win Theme 후보, Pain Point 포함)
  ✓ Phase 0: HOOK 생성 완료 [품질: 72.3점]
  ✓ Phase 1~7 생성 완료 (Cross-Phase Context 적용)

Step 2: PPTX 생성 (Modern 스타일, 폰트 폴백 적용)
  ✓ 슬라이드 생성 완료
  ✓ 저장: output/디지털_마케팅_YYYYMMDDHHmmssfff.pptx
```

---

## 5. 출력 결과물

```
output/
  ├── 프로젝트명_YYYYMMDDHHmmssfff.pptx   ← 최종 결과물
  ├── run_diagnostics_YYYYMMDDHHmmss.json  ← Phase별 진단 (소요시간·품질점수)
  └── _checkpoints/
        ├── phase_2_insight.json           ← Phase별 체크포인트
        ├── phase_3_concept.json
        └── ...
```

### 제안서 구성 (Impact-8 Framework)

| Phase | 이름 | 비중 | 내용 |
|-------|------|------|------|
| 0 | HOOK | 5% | 표지 + 목차 + 임팩트 오프닝 |
| 1 | EXECUTIVE SUMMARY | 5% | 의사결정자용 요약 + Win Theme 3개 |
| 2 | INSIGHT | 10% | 시장 환경 + Pain Point + 기회 분석 + 업종 통계 |
| 3 | CONCEPT & STRATEGY | 12% | 핵심 컨셉 + 차별화 전략 |
| 4 | ACTION PLAN | **40%** | 상세 실행 계획 (제안서의 핵심) |
| 5 | MANAGEMENT | 10% | 조직 구성 + 품질관리 + 리포팅 |
| 6 | WHY US | 12% | 수행 역량 + 유사 실적 (company_profile.json 자동 반영) |
| 7 | INVESTMENT & ROI | 6% | 비용 + KPI + 기대효과 |

---

## 6. v4.0 신기능 상세

### RFP Chunking (긴 RFP 완전 분석)
- 한국어 공공 문서 헤딩 패턴 인식으로 섹션 분류
- 평가기준·배점·요구사항 섹션을 HIGH 우선순위로 전문 포함
- 기존 25,000자 제한 → 최대 40,000자로 확장

### Slide Quality Scoring (자동 채점)
- Phase 완료 후 규칙 기반으로 각 슬라이드 자동 채점 (0~100점)
- 항목: Action Title 준수(25%), 내용 풍부성(30%), 구체성(25%), 플레이스홀더(15%), 유형 적합성(5%)
- 평균 60점 미만 Phase는 경고 로그 출력

### Cross-Phase Context (내러티브 일관성)
- 이전 Phase의 핵심 결론(Win Theme, KPI, 전략 방향)을 다음 Phase 프롬프트에 자동 주입
- Phase 간 메시지 단절 방지

### Industry Stats DB (수치 구체성)
- 업종별 검증 통계를 프롬프트에 자동 삽입
- 예: marketing_pr → SNS 활용률, 콘텐츠 마케팅 ROI 등
- `INDUSTRY_STATS_PATH` 환경변수로 커스텀 통계 JSON 지정 가능

### Phase Checkpoint (안정성)
- 각 Phase 완료 후 `output/_checkpoints/phase_N_*.json` 저장
- API 실패 시 성공한 Phase까지는 재실행 불필요

---

## 7. 커스터마이징

### Phase 프롬프트 수정

```
config/prompts/
├── content_guidelines.txt   ← 전체 공통 규칙 (Action Title, Win Theme 등)
├── phase0_hook.txt
├── phase1_summary.txt
├── phase2_insight.txt
├── phase3_concept.txt
├── phase4_action.txt        ← 가장 상세 (40% 비중)
├── phase5_management.txt
├── phase6_whyus.txt
└── phase7_investment.txt
```

### 프롬프트 버전 관리

```bash
# .env에 설정
PROMPT_VERSION=v4.1

# 디렉토리 구조
config/prompts/v4.1/
  ├── phase2_insight.txt
  └── ...
```

### 디자인 변경

`src/generators/template_manager.py`의 `_get_default_design_system()`에서 컬러·폰트·간격 변경.

### 구조 수정 요약

| 수정 목적 | 수정 파일 |
|----------|----------|
| Phase 비중/슬라이드 수 변경 | `config/proposal_types.py` |
| AI 생성 콘텐츠 규칙 변경 | `config/prompts/phase*.txt` |
| 컬러/폰트/디자인 변경 | `src/generators/template_manager.py` |
| RFP 청킹 설정 | `.env` ENABLE_RFP_CHUNKING, RFP_CHUNK_MAX_CHARS |
| 품질 기준 변경 | `.env` MIN_QUALITY_SCORE |
| 업종 통계 커스터마이징 | `INDUSTRY_STATS_PATH` |

---

## 8. 트러블슈팅

### API 키 오류

```
ANTHROPIC_API_KEY / GEMINI_API_KEY / GROQ_API_KEY가 설정되지 않았습니다.
```

`.env`에서 `LLM_PROVIDER`와 선택한 프로바이더에 맞는 키 확인.

### PDF 파싱 오류

- 텍스트 기반 PDF인지 확인 (스캔 이미지 PDF 미지원)
- 암호화된 PDF 미지원

### PPTX 생성 오류

```bash
pip install --upgrade python-pptx
```

### 슬라이드 품질 경고 로그

```
WARNING | Phase 3 품질 점수: 45.2점 (기준: 60점 미만)
```

프롬프트를 강화하거나 `.env`에서 `MIN_QUALITY_SCORE=40` 으로 기준 완화 가능.

---

## 9. 디렉토리 구조

```
proposal-agent/
├── main.py                        # CLI (generate, analyze, setup-company, types, info, templates)
├── .env.example                   # 환경 변수 예시 (v4.0 고도화 옵션 포함)
├── config/
│   ├── settings.py                # API 키·LLM·v4.0 옵션
│   ├── proposal_types.py          # 제안서 유형 6종·가중치
│   └── prompts/                   # Phase별 프롬프트
├── src/
│   ├── parsers/                   # get_parser_for_path + RFPChunker
│   ├── agents/                    # base_agent, rfp_analyzer, content_generator (v4.0)
│   ├── data/                      # company_profiler, industry_stats
│   ├── quality/                   # slide_scorer
│   ├── schemas/                   # proposal_schema, rfp_schema
│   ├── generators/                # template_manager (폰트 폴백), pptx_generator, chart_generator, diagram_generator
│   ├── orchestrators/             # proposal_orchestrator, pptx_orchestrator
│   └── utils/                     # logger, path_utils
├── tests/                         # pytest
├── templates/                     # PPTX 템플릿 (선택)
├── company_data/                  # 회사 프로필 JSON
├── input/                         # RFP 입력
└── output/                        # PPTX 출력 + _checkpoints/
```

---

## 10. 빠른 시작 체크리스트

### ① AI 코드 어시스턴트 방식

```
[ ] Python 3.10+ 설치
[ ] pip install -r requirements.txt
[ ] input/ 폴더에 RFP 배치
[ ] AI 어시스턴트에게 "input 폴더의 RFP를 분석한 후 제안서를 제작해줘" 요청
[ ] output/ 폴더에서 PPTX 확인
```

### ② CLI 방식

```
[ ] Python 3.10+ 설치
[ ] pip install -r requirements.txt
[ ] .env 생성: LLM_PROVIDER, *_API_KEY 설정
[ ] python main.py setup-company (최초 1회)
[ ] input/ 폴더에 RFP 배치
[ ] python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처"
[ ] output/ 폴더에서 프로젝트명_타임스탬프.pptx 확인
```
