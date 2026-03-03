# 입찰 제안서 자동 생성 에이전트 (Impact-8 + pptx_generator + TemplateManager)

## 프로젝트 개요
RFP(제안요청서) 문서를 입력받아 PPTX 형식의 입찰 제안서를 자동 생성하는 Python 에이전트 시스템.

**현재 구현**: 문서 파싱(`get_parser_for_path` → PDF/DOCX/TXT/PPTX), RFP 분석·콘텐츠 생성(LLM: Claude/Gemini/Groq), PPTX 렌더링(`TemplateManager` + `pptx_generator` + `chart_generator` + `diagram_generator`).

## ★★★ 제안서 생성 워크플로우 (최우선 규칙)

사용자가 "제안요청서 폴더에 있는 테스트 XX 폴더 내 파일을 분석한 후 제안서를 제작해줘" 라고 요청하면:

### 폴더 구조
```
제안요청서/테스트 XX/    ← RFP 입력 (PDF 문서들)
output/테스트 XX/        ← PPTX 출력 (생성 스크립트 + 결과물)
```

### 실행 단계

**STEP 1: RFP 분석** (제안요청서 폴더 내 PDF 읽기)
- `제안요청서/테스트 XX/` 내 모든 PDF를 분석
- 추출 항목: 프로젝트명, 발주처, 과업 범위, 평가 기준, 예산, 일정, 특이사항
- 프로젝트 유형 판별: marketing_pr / event / it_system / public / consulting

**STEP 2: 콘텐츠 기획** (Impact-8 Phase 구조)
- Phase 0~7 콘텐츠를 RFP 맞춤형으로 설계
- Win Theme 3개 도출
- Action Title (인사이트 기반 문장형 제목) 작성
- KPI + 산출근거 설계

**STEP 3: 생성 스크립트 작성**
- `output/테스트 XX/generate_제안서.py` 스크립트 생성
- **PPTX 생성**: `src/generators/pptx_generator.py` + `TemplateManager` + `chart_generator` / `diagram_generator` 사용 (CLI `main.py generate`가 내부에서 사용)
- 목표 분량: 40~80장 (프로젝트 규모에 따라 조정)

**STEP 4: 실행 및 검증**
- 스크립트 실행하여 PPTX 생성
- 오류 발생 시 즉시 수정 후 재실행
- 최종 파일 경로 안내

### 레이아웃·슬라이드 (현재 구현)

PPTX 생성은 `src/generators/pptx_generator.py`(제목/본문/테이블/2·3단), `chart_generator.py`(차트·타임라인·조직도), `diagram_generator.py`(프로세스 플로우)와 `TemplateManager`(템플릿·디자인 시스템)로 수행됩니다.  
`main.py generate` 명령이 RFP 파싱 → 콘텐츠 생성 → PPTX 렌더링을 한 번에 실행합니다.

### ★★★ 겹침·공백 방지 규칙 (참고)

**1. 요소 간 최소 간격 (인치)**
```
HIGHLIGHT → 다음 요소:  0.75"  (HIGHLIGHT 높이 ~0.65-0.7")
COLS       → 다음 요소:  0.30"
METRIC_CARD → 다음 요소:  0.15"
MT(불릿)   → 다음 요소:  0.20"
```

**2. MT(불릿 텍스트) 높이 — 줄 수에 맞춤**
```
3줄=1.1"  4줄=1.4"  5줄=1.7"  6줄=2.0"  8줄=2.8"
❌ 절대 금지: 줄 수와 무관한 고정 높이 (예: 4줄인데 h=3.2")
```

**3. 한글 텍스트 너비 추정**
```
44pt: 0.61"/자 → CW(~11.8") 내 최대 ~18자
36pt: 0.50"/자 → CW 내 최대 ~23자
→ 44pt 제목이 18자 초과 시 반드시 2줄 분리 (별도 T() 호출)
```

**4. 공백 보완 규칙**
- 콘텐츠 하단 공백 > 0.5" → IMG_PH 또는 HIGHLIGHT 추가
- METRIC_CARD 높이 확대 (비율 기반 배치가 자동 대응)
- 섹션 구분자/표지/마지막 슬라이드의 공백은 의도적 → 수정 불필요

**5. 배경색 충돌 방지**
- slide_next_step 배경: C["dark"] (카드가 C["primary"] 등)
- 카드 색상 = 배경 색상이면 반드시 다른 색상으로 변경

**6. Phase 3 필수 컨셉 장표 (3종)**
1. **Concept Reveal** — 다크 배경, 60pt 대형 컨셉 키워드, 4단계 순환 카드
2. **Strategy Synergy Map** — 3대 Win Theme 연결 구조, 순환 흐름도
3. **Big Idea Reveal** — 36pt 중앙 컨셉 + 3-Step 카드

**7. 시각 요소 필수 포함**
```
| 슬라이드 유형 | 필수 시각 요소 |
|-------------|-------------|
| 시장 분석    | METRIC_CARD 4개 + HIGHLIGHT + IMG_PH |
| 컨셉        | Concept Reveal + Synergy Map |
| 시즌 전략    | 좌우 카드 + IMG_PH (캠페인 비주얼) |
| 이벤트 종합  | TABLE + METRIC_CARD + IMG_PH (현장 사진) |
| 운영 프로세스 | COLS + HIGHLIGHT + IMG_PH (인포그래픽) |
| 커뮤니케이션  | COLS + HIGHLIGHT + IMG_PH (흐름도) |
```

### 기본 사용 패턴 (CLI)

```bash
# 제안서 생성 (RFP → 파싱 → 분석 → 콘텐츠 → PPTX)
python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처"

# RFP 분석만
python main.py analyze input/rfp.pdf
```

Win Theme, Executive Summary, Action Title 등은 콘텐츠 생성(Impact-8) 단계에서 자동 반영됩니다.
- Win Theme: 제안서 전체에 반복되는 핵심 수주 전략 메시지
- Executive Summary: 의사결정권자용 1페이지 핵심 요약
- Next Step: 다음 단계 안내 / Call to Action
- Action Title: 인사이트 기반 슬라이드 제목 (Topic Title → Action Title)

## 역할 분리

### Gemini (콘텐츠 생성)
- RFP 문서 분석 및 핵심 정보 추출
- Phase 0~7 제안서 콘텐츠 생성
- 수주 전략 및 차별화 포인트 도출
- 실제 콘텐츠 예시 생성 (마케팅/PR)

### [회사명] (문서화)
- PPTX 변환 및 Modern 스타일 디자인 적용
- 슬라이드 레이아웃 및 포맷팅
- 차트, 타임라인, 조직도 생성

## 디렉토리 구조

```
├── main.py                 # CLI 엔트리포인트
├── config/
│   ├── prompts/            # Phase별 프롬프트 템플릿
│   │   ├── content_guidelines.txt
│   │   ├── phase0_hook.txt … phase7_investment.txt
│   └── proposal_types.py   # 제안서 유형·가중치
├── src/
│   ├── parsers/            # 문서 파싱 (PDF, DOCX, TXT, PPTX) — get_parser_for_path
│   ├── agents/             # RFP 분석·콘텐츠 생성 (LLM)
│   ├── generators/         # PPTX: template_manager, pptx_generator, chart_generator, diagram_generator
│   ├── orchestrators/      # proposal_orchestrator, pptx_orchestrator
│   └── schemas/            # Pydantic 스키마 (proposal_schema, rfp_schema)
├── templates/              # PPTX 템플릿
├── company_data/           # 회사 정보
├── input/                  # RFP 입력
├── output/                 # PPTX 출력
└── 제안서/                 # 레퍼런스 제안서
    └── reference_proposal.pdf (비공개)
```

## 사용법

```bash
# 의존성 설치
pip install -r requirements.txt

# .env 설정
cp .env.example .env
# GEMINI_API_KEY 설정

# 제안서 생성 (기본: Impact-8 구조)
python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처"

# 프로젝트 유형 지정
python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처" -t marketing_pr

# RFP 분석만 수행
python main.py analyze input/rfp.pdf
```

## 제안서 구조: Impact-8 Framework

실제 수주 성공 제안서 분석을 기반으로 개선된 8-Phase 구조

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 0: HOOK (티저)                         3-10p (5%)   │
│  → 임팩트 있는 오프닝, 핵심 메시지, 비전                      │
├─────────────────────────────────────────────────────────────┤
│  PHASE 1: SUMMARY                             3-5p (5%)    │
│  → Executive Summary (의사결정자용 5분 요약)                 │
├─────────────────────────────────────────────────────────────┤
│  PHASE 2: INSIGHT                             8-15p (10%)  │
│  → 시장 환경 + 문제 정의 + 숨겨진 니즈                       │
├─────────────────────────────────────────────────────────────┤
│  PHASE 3: CONCEPT & STRATEGY                  8-15p (12%)  │
│  → 핵심 컨셉 + 차별화 전략 + 경쟁 우위                       │
├─────────────────────────────────────────────────────────────┤
│  PHASE 4: ACTION PLAN (★핵심)                 30-60p (40%) │
│  → 상세 실행 계획 + 콘텐츠 예시 + 채널별 전략                 │
├─────────────────────────────────────────────────────────────┤
│  PHASE 5: MANAGEMENT                          6-12p (10%)  │
│  → 조직 + 운영 + 품질관리 + 리포팅                          │
├─────────────────────────────────────────────────────────────┤
│  PHASE 6: WHY US                              8-15p (12%)  │
│  → 수행 역량 + 유사 실적 + 레퍼런스                          │
├─────────────────────────────────────────────────────────────┤
│  PHASE 7: INVESTMENT & ROI                    4-8p (6%)    │
│  → 투자 비용 + 정량적 효과 + ROI                            │
└─────────────────────────────────────────────────────────────┘
  총 70-140p (프로젝트 규모에 따라 조정)
```

## 프로젝트 유형별 가중치

| Phase | Marketing/PR | Event | IT/System | Public | Consulting |
|-------|-------------|-------|-----------|--------|------------|
| 0. HOOK | 8% | 6% | 3% | 3% | 5% |
| 1. SUMMARY | 5% | 5% | 8% | 8% | 8% |
| 2. INSIGHT | 12% | 8% | 12% | 15% | 15% |
| 3. CONCEPT | 12% | 10% | 10% | 10% | 12% |
| 4. ACTION | **40%** | **45%** | 35% | 30% | 30% |
| 5. MANAGEMENT | 8% | 10% | 12% | 12% | 10% |
| 6. WHY US | 10% | 10% | 12% | 15% | 12% |
| 7. INVESTMENT | 5% | 6% | 8% | 7% | 8% |

## v3.1 핵심 컴포넌트

### Win Theme (수주 전략 메시지)
제안서 전체에 반복되는 3대 핵심 수주 전략 메시지

```python
WIN_THEMES = {
    "data": "데이터 기반 타겟 마케팅",
    "community": "시민 참여형 브랜드 빌딩",
    "integration": "온-오프라인 통합 시너지",
}
```

- 각 섹션 구분자에 관련 Win Theme 표시
- 슬라이드 내에서 Win Theme 뱃지로 강조
- 일관된 메시지 반복으로 수주 전략 강화

### Action Title (인사이트 기반 제목)
Topic Title에서 Action Title로 전환

| Before (Topic Title) | After (Action Title) |
|---------------------|---------------------|
| 타겟 분석 | MZ세대 2030이 핵심, 하루 SNS 55분 사용 |
| 채널 전략 | 인스타그램 중심, 릴스로 도달률 3배 확보 |
| 예산 계획 | 월 3,000만원으로 팔로워 50만 달성 |

### Executive Summary
의사결정권자용 1페이지 핵심 요약

구성요소:
- 프로젝트 목표 (One Sentence Pitch)
- 3대 Win Theme
- 핵심 KPI (산출 근거 포함)
- Why Us 핵심 차별점

### Next Step (Call to Action)
다음 단계 안내 및 행동 촉구

```
┌─────────────────────────────────────────┐
│  NEXT STEP                              │
│                                         │
│  STEP 1: 제안 설명회 (00월 00일)         │
│  STEP 2: Q&A 및 추가 협의               │
│  STEP 3: 계약 체결                      │
│                                         │
│  Contact: [담당자 정보]                 │
└─────────────────────────────────────────┘
```

### KPI 산출 근거
모든 KPI에 산출 근거 필수 포함

```
목표: 팔로워 +30%
산출 근거: 인플루언서 협업 +10% + 릴스 확대 +12% + 이벤트 +8%
데이터 출처: 유사 프로젝트 평균 성장률 참고
```

### Placeholder 표준화
미완성 콘텐츠 표기 형식 통일: `[대괄호]`

```
✅ [발주처명], [프로젝트명], [담당자 연락처]
❌ OOO, XXX, ___
```

## 디자인 스타일: Modern

실제 수주 성공 제안서를 분석하여 추출한 디자인 시스템

### 컬러 팔레트
- Primary: `#002C5F` (다크 블루)
- Secondary: `#00AAD2` (스카이 블루)
- Teal: `#00A19C` (틸 - Win Theme 뱃지용)
- Accent: `#E63312` (레드)
- Dark BG: `#1A1A1A`
- Light BG: `#F5F5F5` (밝은 배경)

### 타이포그래피
- Font: Pretendard
- 티저 타이틀: 72pt Bold
- 섹션 타이틀: 48pt Bold
- 슬라이드 타이틀: 36pt SemiBold
- 본문: 18pt Regular

### 레이아웃
- 16:9 비율 (1920 x 1080)
- 여백: 상 80px, 하 60px, 좌우 100px
- 섹션 구분자: 다크 배경, 대형 숫자 아웃라인

## 핵심 컴포넌트

### 스키마 (Gemini ↔ [회사명] 인터페이스)
- `src/schemas/proposal_schema.py` - ProposalContent, PhaseContent (v3.1)
  - 새로운 모델: WinTheme, KPIWithBasis, ExecutiveSummary, NextStep, ActionTitle
  - 새로운 SlideType: EXECUTIVE_SUMMARY, NEXT_STEP, DIFFERENTIATION
- `src/schemas/rfp_schema.py` - RFPAnalysis

### 에이전트 (Gemini)
- `src/agents/rfp_analyzer.py` - RFP 분석
- `src/agents/content_generator.py` - 콘텐츠 생성

### 생성기 ([회사명])
- `src/generators/pptx_generator.py` - 슬라이드 생성 (v3.1)
  - 새로운 메서드: add_executive_summary_slide(), add_next_step_slide(), add_section_divider_with_win_theme()
- `src/generators/chart_generator.py` - 차트/다이어그램

### 디자인 설정
- `config/design/design_style.py` - Modern 스타일 정의 (v3.1)
  - 새로운 스타일: WinThemeBadgeStyle, ExecutiveSummaryStyle, NextStepStyle, DifferentiationStyle
  - WIN_THEME_TEMPLATES: 프로젝트 유형별 Win Theme 템플릿

### 콘텐츠 가이드라인
- `config/prompts/content_guidelines.txt` - Action Title, Win Theme, KPI 산출 근거 작성 가이드

## 마케팅/PR 특화 기능

### 콘텐츠 예시 생성
- 실제 포스팅 예시 (비주얼 설명, 카피)
- 해시태그 전략
- 캠페인 상세 기획

### 채널별 전략
- Instagram: 피드, 스토리, 릴스
- YouTube: 롱폼, 숏폼, 커뮤니티
- Facebook, X, TikTok, Blog

### 캠페인 기획
- 캠페인 컨셉 및 목표
- 실행 계획
- 예상 성과

## 레퍼런스

- 실제 수주 성공 제안서 (200p+) — 구조 분석 레퍼런스
  - 구조: INTRO(13p) + CONCEPT(31p) + STRATEGY(14p) + ACTION PLAN(101p) + MANAGEMENT(16p) + CREDENTIALS(44p)
  - 핵심: ACTION PLAN이 전체의 46% 차지
  - 특징: 실제 콘텐츠 예시, AI 캠페인, 숏폼-롱폼 연계 전략
