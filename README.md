# Proposal Agent — AI 제안서 자동 생성 에이전트 v4.0

RFP(제안요청서) PDF/DOCX/TXT/PPTX를 입력하면 **Impact-8 구조의 PPTX 제안서**를 자동 생성하는 AI 에이전트 시스템

## 핵심 특징

- **Impact-8 Framework**: 실제 수주 성공 제안서 분석 기반 8-Phase 구조 (Phase 0 HOOK ~ Phase 7 INVESTMENT & ROI)
- **다중 LLM 지원**: `.env`의 `LLM_PROVIDER`로 **Claude / Gemini / Groq** 중 선택
- **RFP Chunking**: 섹션 우선순위 기반 청킹으로 긴 RFP(평가기준·요구사항 우선) 완전 분석 (기존 25,000자 → 40,000자)
- **슬라이드 품질 자동 스코어링**: Action Title 준수·구체성·플레이스홀더 남용을 규칙 기반으로 자동 채점
- **Cross-Phase Context**: Phase 간 핵심 결론을 다음 Phase에 전달해 내러티브 일관성 확보
- **Phase Checkpoint**: 각 Phase 생성 후 자동 저장 → API 실패 시 재시작 불필요
- **Industry Stats DB**: 업종별 검증 통계 주입으로 수치 구체성 향상
- **회사 프로필 CLI**: `setup-company` 명령으로 회사 실적·역량 입력 → Phase 6(WHY US) 품질 향상
- **Modern 스타일 PPTX**: TemplateManager(폰트 폴백 포함) + python-pptx 기반 렌더링

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
# (최초 1회) 회사 프로필 설정 — Phase 6 WHY US 품질 향상
python main.py setup-company

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
    ├─ RFP Chunking: 섹션별 우선순위 청킹 (평가기준·요구사항 우선 포함)
    ├─ 프로젝트명·발주처·핵심요구사항·평가기준 추출
    ├─ Pain Point / Hidden Needs / Win Theme 후보 전략 분석
    └─ 제안서 유형 자동 판별
    │
    ▼
STEP 3: 콘텐츠 생성 (동일 LLM × 8 Phase)
    ├─ Cross-Phase Context: 이전 Phase 결론 → 다음 Phase 프롬프트 주입
    ├─ Industry Stats DB: 업종별 검증 통계 자동 주입
    ├─ Negative Prompts: 플레이스홀더·막연한 표현 절대 금지 명시
    ├─ Phase Checkpoint: 각 Phase 완료 후 output/_checkpoints/ 저장
    └─ 슬라이드 품질 자동 스코어링 (Action Title·구체성·플레이스홀더 채점)
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
| 6 | WHY US | 수행역량 (회사 프로필 자동 반영) |
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
├── main.py                     # CLI 엔트리포인트 (generate, analyze, setup-company, types, info, templates)
├── AGENT_GUIDE.md              # 에이전트 가이드
├── .env.example                # 환경 변수 예시 (복사 후 .env로 사용)
├── config/
│   ├── settings.py             # API 키·LLM 선택·경로·v4.0 고도화 옵션
│   ├── proposal_types.py       # 제안서 유형 6종·가중치
│   └── prompts/                # Phase별 프롬프트
├── src/
│   ├── parsers/                # PDF, DOCX, TXT, PPTX 파싱 + RFPChunker
│   ├── agents/                 # base_agent, rfp_analyzer (청킹 연동), content_generator (v4.0)
│   ├── data/                   # company_profiler, industry_stats (업종별 통계 DB)
│   ├── quality/                # slide_scorer (규칙 기반 슬라이드 품질 채점)
│   ├── schemas/                # proposal_schema, rfp_schema (Pydantic)
│   ├── generators/             # template_manager (폰트 폴백), pptx_generator, chart_generator, diagram_generator
│   ├── orchestrators/          # proposal_orchestrator, pptx_orchestrator
│   └── utils/                  # logger, path_utils
├── tests/                      # pytest
├── templates/                  # PPTX 템플릿 (.gitignore 대상)
├── company_data/               # 회사 프로필 JSON (setup-company로 생성)
├── input/                      # RFP 입력
└── output/                     # 생성된 PPTX + _checkpoints/ (Phase 체크포인트)
```

## 기술 스택

| 카테고리 | 기술 |
|---------|------|
| AI | Claude (Anthropic) / Gemini (Google) / Groq (.env LLM_PROVIDER로 선택) |
| 문서 파싱 | pypdf, pdfplumber, python-docx, python-pptx |
| PPTX 생성 | python-pptx, TemplateManager 디자인 시스템 (폰트 폴백 포함) |
| 데이터 | Pydantic v2, JSON |
| CLI | Typer, Rich |

## 템플릿·폰트/디자인 가이드

- **템플릿 미지정** (`-T`/`--template` 생략): 빈 프레젠테이션 + 기본 디자인 시스템으로 생성 (권장)
- **템플릿 지정** (`-T guide_template` 등): 해당 PPTX의 테마(색상·폰트)를 동적 추출해 적용
- **폰트 폴백**: 템플릿 폰트가 시스템에 없으면 자동으로 맑은 고딕으로 대체 (Pretendard, Noto Sans KR 등)

## 가이드 문서

- [에이전트 가이드](AGENT_GUIDE.md) — AI/코드 어시스턴트용
- [실행 가이드](docs/실행_가이드.md) — 설치·설정·실행
- [설치 및 사용 가이드](docs/INSTALL_AND_USAGE.md) — 단계별 설치·사용법
- [에이전트 구축·시스템 구조](docs/입찰제안서_에이전트_가이드.md) — 아키텍처
- [상세 사용 가이드](docs/제안서_에이전트_사용_가이드.md) — 커스터마이징

## 버전

- **v4.0** (2026-03-04): RFP Chunking, Industry Stats DB, Slide Quality Scorer, Cross-Phase Context, Phase Checkpoint, Negative Prompts, setup-company CLI, 폰트 폴백
- **v3.0**: Impact-8 Framework, 다중 LLM, TemplateManager + pptx/chart/diagram generator
