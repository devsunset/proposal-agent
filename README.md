# Proposal Agent — AI 제안서 자동 생성 에이전트

RFP(제안요청서) PDF/DOCX/TXT/PPTX를 입력하면 **Impact-8 구조의 PPTX 제안서**를 자동 생성하는 AI 에이전트 시스템

## 핵심 특징

- **Impact-8 Framework**: 실제 수주 성공 제안서 분석 기반 8-Phase 구조 (Phase 0 HOOK ~ Phase 7 INVESTMENT & ROI)
- **다중 LLM 지원**: .env의 `LLM_PROVIDER`로 **Claude / Gemini / Groq** 중 선택
- **Win Theme 전달**: Phase 1에서 확정한 Win Theme이 전체 제안서에 일관 반영
- **Modern 스타일 PPTX**: TemplateManager 디자인 시스템 + python-pptx 기반 렌더링 (pptx_generator, chart_generator, diagram_generator)

## 빠른 시작

### ① AI 코드 어시스턴트 방식 (권장)

```bash
pip install -r requirements.txt
```

AI 코드 어시스턴트(Cursor 등)에게 자연어로 요청:

```
"input 폴더의 RFP를 분석한 후 제안서를 제작해줘"
```

### ② CLI 방식

```bash
pip install -r requirements.txt

# .env 설정 (루트에 .env.example 복사 후 값 입력)
cp .env.example .env
# LLM_PROVIDER=gemini | claude | groq 및 해당 *_API_KEY 설정
```

```bash
# 제안서 생성 (RFP: PDF/DOCX/TXT/PPTX)
python main.py generate input/sample.txt -n "프로젝트명" -c "발주처명"

# 제안서 유형 지정
python main.py generate input/rfp.pdf -n "프로젝트명" -c "발주처" -t marketing_pr

# RFP 분석만 수행
python main.py analyze input/rfp.pdf
```

## 파이프라인

```
RFP (PDF/DOCX/TXT/PPTX)
    │
    ▼
STEP 1: 문서 파싱 (확장자별 파서)
    │
    ▼
STEP 2: RFP 분석 (LLM: Claude / Gemini / Groq)
    ├─ 프로젝트명·발주처 추출
    ├─ 핵심 요구사항·평가 기준
    └─ 제안서 유형 자동 판별
    │
    ▼
STEP 3: 콘텐츠 생성 (동일 LLM × 8 Phase)
    ├─ Phase 0: HOOK (티저)
    ├─ Phase 1~7: SUMMARY, INSIGHT, CONCEPT, ACTION PLAN, MANAGEMENT, WHY US, INVESTMENT & ROI
    └─ Win Theme·KPI·슬라이드 구조
    │
    ▼
STEP 4: PPTX 렌더링 (TemplateManager + pptx_generator + chart/diagram_generator)
    └─ output/프로젝트명_YYYYMMDDHHmmssfff.pptx
```

## Impact-8 Framework

| Phase | 이름 | 설명 |
|-------|------|------|
| 0 | HOOK | 임팩트 있는 오프닝 |
| 1 | SUMMARY | 5분 핵심 요약 + Win Theme |
| 2 | INSIGHT | 시장/문제 분석 |
| 3 | CONCEPT & STRATEGY | 전략/차별화 |
| 4 | ACTION PLAN | 상세 실행계획 (★핵심, 40% 비중) |
| 5 | MANAGEMENT | 운영/품질 |
| 6 | WHY US | 수행역량 |
| 7 | INVESTMENT & ROI | 비용/효과 |

## 프로젝트 유형

| 유형 (`-t`) | 설명 |
|-------------|------|
| marketing_pr | 마케팅/PR/소셜미디어 |
| event | 이벤트/행사 |
| it_system | IT/시스템 |
| public | 공공/입찰 |
| consulting | 컨설팅 |
| general | 일반 (미지정 시 자동 판별) |

## 디렉토리 구조

```
├── main.py                     # CLI 엔트리포인트 (generate, analyze, types, info, templates)
├── AGENT_GUIDE.md              # 에이전트 가이드 (.env LLM_PROVIDER에 따른 동적 적용)
├── .env.example                # 환경 변수 예시 (복사 후 .env로 사용)
├── config/
│   ├── settings.py             # API 키·LLM 선택·경로·재시도/토큰 설정
│   ├── proposal_types.py       # 제안서 유형 6종·가중치 (get_type_display_name)
│   └── prompts/                # Phase별 프롬프트 (phase0_hook ~ phase7_investment)
├── src/
│   ├── parsers/                # PDF, DOCX, TXT, PPTX 파싱 (get_parser_for_path)
│   ├── agents/                 # base_agent, rfp_analyzer, content_generator
│   ├── schemas/                # proposal_schema, rfp_schema (Pydantic)
│   ├── generators/             # template_manager, pptx_generator, chart_generator, diagram_generator
│   ├── orchestrators/          # proposal_orchestrator, pptx_orchestrator
│   └── utils/                  # logger, path_utils (safe_filename, safe_output_path)
├── tests/                      # pytest (parsers, path_utils, settings, template_manager 등)
├── templates/                  # PPTX 템플릿 (지정한 파일 또는 'guide' 포함 .pptx 자동 선택, 테마로 디자인 규칙 적용)
├── company_data/               # 회사 정보 JSON (기본: company_profile.json)
├── input/                      # RFP 입력
├── output/                     # 생성된 PPTX (프로젝트명_YYYYMMDDHHmmssfff.pptx)
└── docs/                       # 가이드 문서
```

## 기술 스택

| 카테고리 | 기술 |
|---------|------|
| AI | Claude (Anthropic) / Gemini (Google) / Groq (.env LLM_PROVIDER로 선택) |
| 문서 파싱 | pypdf, pdfplumber, python-docx, python-pptx |
| PPTX 생성 | python-pptx, TemplateManager 디자인 시스템 |
| 데이터 | Pydantic v2, JSON |
| CLI | Typer, Rich |

## 템플릿·폰트/디자인 가이드

- **템플릿 미지정** (`-T`/`--template` 생략): 템플릿 파일 없이 **빈 프레젠테이션 + 기본 디자인 시스템**으로 제안서를 생성합니다(권장).
- **템플릿 지정** (`-T guide_template` 등): `templates/guide_template.pptx`가 있으면 해당 파일 사용. 없으면 `templates/` 내 이름에 '가이드' 또는 'guide'가 포함된 .pptx를 자동 선택. 둘 다 없으면 빈 프레젠테이션 + 기본 디자인.
- **레이아웃·테마**: 선택된 PPTX의 슬라이드 레이아웃과 테마(색상·폰트)를 동적으로 추출해 적용합니다.

## 가이드 문서

- [에이전트 가이드](AGENT_GUIDE.md) — AI/코드 어시스턴트용 (.env LLM_PROVIDER 동적 적용)
- [실행 가이드](docs/실행_가이드.md) — 설치·설정·실행 (Claude/Gemini/Groq)
- [설치 및 사용 가이드](docs/INSTALL_AND_USAGE.md) — 단계별 설치·사용법
- [에이전트 구축·시스템 구조](docs/입찰제안서_에이전트_가이드.md) — 아키텍처 및 설계
- [상세 사용 가이드](docs/제안서_에이전트_사용_가이드.md) — 고급 사용·커스터마이징
- [기술 문서](docs/PROPOSAL_AGENT_GUIDE.md) — API·스키마 레퍼런스

## 버전

- **v3.0**: Impact-8 Framework, 다중 LLM(Claude/Gemini/Groq), TemplateManager + pptx/chart/diagram generator, get_parser_for_path, safe_output_path, pytest 테스트
- 출력 파일명: `프로젝트명_YYYYMMDDHHmmssfff.pptx` (타임스탬프 접미사로 유일 보장)
