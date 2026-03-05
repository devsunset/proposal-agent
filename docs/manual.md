# 수동 모드 (Manual Mode) 설계 및 구현

> 현재 프로젝트 구현 기준 문서. 실행 가이드는 [1.INSTALL_AND_USAGE.md](1.INSTALL_AND_USAGE.md) 수동 모드 절 참고.

---

## 개요

LLM API를 직접 호출하는 대신, 각 단계별 프롬프트를 파일로 저장하고
사용자가 Gemini(또는 다른 LLM)에서 직접 질의·응답을 수작업으로 진행하는 **수동 모드**.

- **과금·속도 제한 없이** 무료 Gemini(Google AI Studio)를 활용 가능
- 9단계 (RFP 분석 1회 + Phase 0~7 생성 8회) 수작업 진행
- 각 단계마다 질의용 파일 생성 → 사용자 응답 붙여넣기 → `continue` 명령으로 다음 단계 진행

---

## 폴더/파일 구조

**파일명 규칙:** `{Step번호}_step_{Phase명}_request.txt` / `{Step번호}_step_{Phase명}_response.txt`  
(Step 1은 Phase 명칭으로 `RFPAnalyzer`, Step 2~9는 `HOOK`, `SUMMARY`, `INSIGHT`, `CONCEPT`, `ACTION_PLAN`, `MANAGEMENT`, `WHY_US`, `INVESTMENT` 사용)

```
proposal-agent/
├── manual/                                    # 수동 모드 작업 폴더 (자동 생성)
│   ├── state.json                             # 현재 진행 상태 (시스템 관리)
│   ├── 1_step_RFPAnalyzer_request.txt         # Step 1: RFP 분석 질의 프롬프트
│   ├── 1_step_RFPAnalyzer_response.txt        # Step 1: 사용자가 Gemini 응답 붙여넣기
│   ├── 2_step_HOOK_request.txt                # Step 2: Phase 0 (HOOK)
│   ├── 2_step_HOOK_response.txt
│   ├── 3_step_SUMMARY_request.txt             # Step 3: Phase 1 (SUMMARY)
│   ├── 3_step_SUMMARY_response.txt
│   ├── 4_step_INSIGHT_request.txt ~ 9_step_INVESTMENT_request.txt
│   └── 4_step_INSIGHT_response.txt ~ 9_step_INVESTMENT_response.txt
│
├── src/
│   └── manual/                     # 수동 모드 모듈
│       ├── __init__.py             # ManualOrchestrator, _step_*_file_name export
│       └── manual_orchestrator.py  # ManualOrchestrator, STEP_FILE_LABELS
│
└── main.py                         # CLI: --manual, continue, status
```

---

## 단계별 매핑

| Step | 내용                    | 요청 파일                         | 응답 파일                          |
| ---- | ----------------------- | --------------------------------- | ---------------------------------- |
| 1    | RFP 분석 (RFPAnalyzer)  | `1_step_RFPAnalyzer_request.txt`  | `1_step_RFPAnalyzer_response.txt` |
| 2    | Phase 0: HOOK (티저)    | `2_step_HOOK_request.txt`        | `2_step_HOOK_response.txt`        |
| 3    | Phase 1: SUMMARY        | `3_step_SUMMARY_request.txt`     | `3_step_SUMMARY_response.txt`     |
| 4    | Phase 2: INSIGHT        | `4_step_INSIGHT_request.txt`     | `4_step_INSIGHT_response.txt`     |
| 5    | Phase 3: CONCEPT        | `5_step_CONCEPT_request.txt`     | `5_step_CONCEPT_response.txt`     |
| 6    | Phase 4: ACTION PLAN    | `6_step_ACTION_PLAN_request.txt` | `6_step_ACTION_PLAN_response.txt` |
| 7    | Phase 5: MANAGEMENT     | `7_step_MANAGEMENT_request.txt`  | `7_step_MANAGEMENT_response.txt`  |
| 8    | Phase 6: WHY US         | `8_step_WHY_US_request.txt`      | `8_step_WHY_US_response.txt`      |
| 9    | Phase 7: INVESTMENT     | `9_step_INVESTMENT_request.txt`  | `9_step_INVESTMENT_response.txt`  |

---

## CLI 명령

### 시작: 수동 모드로 제안서 생성 시작

```bash
python main.py generate input/rfp.pdf --manual
# 단축 옵션: -m
# 옵션 동일 사용 가능: -n, -c, -t, -d, -o, -T
python main.py generate input/rfp.pdf --manual -n "프로젝트명" -c "발주처"
```

### 진행: 응답 처리 및 다음 단계 생성

```bash
python main.py continue
# 작업 폴더 변경 시: python main.py continue --manual-dir my_manual
```

### 상태 확인

```bash
python main.py status
# 작업 폴더 변경 시: python main.py status --manual-dir my_manual
```

---

## 사용 흐름

```
1. python main.py generate input/rfp.pdf --manual
   → RFP 파싱 (LLM 없음)
   → manual/1_step_RFPAnalyzer_request.txt 생성
   → manual/state.json 초기화

2. [사용자] manual/1_step_RFPAnalyzer_request.txt 열기
   → [시스템 프롬프트]와 [사용자 메시지]를 Gemini(Google AI Studio)에 입력
   → Gemini 응답(JSON) 복사 → manual/1_step_RFPAnalyzer_response.txt 에 붙여넣기

3. python main.py continue
   → 1_step_RFPAnalyzer_response.txt 파싱 → state에 RFPAnalysis 저장
   → manual/2_step_HOOK_request.txt 생성 (Phase 0 HOOK)

4. [사용자] manual/2_step_HOOK_request.txt 로 Gemini 질의
   → manual/2_step_HOOK_response.txt 에 응답 붙여넣기

5. python main.py continue
   → Step 2~9 반복 (매 단계 해당 Phase명 응답 파일 저장 후 continue)

6. 마지막 continue (Step 9 처리 후)
   → 모든 데이터 수집 완료
   → output/ 폴더에 PPTX 자동 생성
```

---

## 요청 파일 형식 (N_step_{Phase명}_request.txt)

요청 파일명 예: `1_step_RFPAnalyzer_request.txt`, `2_step_HOOK_request.txt`, `3_step_SUMMARY_request.txt` 등.

```
=====================================
제안서 자동 생성 에이전트 - 수동 모드
Step N/9: [단계 설명]
=====================================

[사용법]
1. 아래 [시스템 프롬프트]와 [사용자 메시지]를 Gemini에 입력하세요.
   추천: Google AI Studio (https://aistudio.google.com/)
   - [시스템 프롬프트] → "System Instructions" 란에 입력
   - [사용자 메시지]  → 메인 입력란에 입력

2. Gemini 응답(JSON 전체)을 복사하여 해당 단계 응답 파일에 붙여넣으세요:
   → manual/N_step_{Phase명}_response.txt  (예: manual/1_step_RFPAnalyzer_response.txt)

3. 다음 명령 실행:
   python main.py continue

=====================================
[시스템 프롬프트 (System Instructions)]
=====================================
[system prompt 내용]

=====================================
[사용자 메시지 (User Message)]
=====================================
[user message 내용]
```

---

## 상태 파일 (manual/state.json)

```json
{
  "version": 1,
  "rfp_path": "input/rfp.pdf",
  "project_name": "프로젝트명",
  "client_name": "발주처명",
  "proposal_type": "marketing_pr",
  "company_data_path": "company_data/company_profile.json",
  "company_data": {},
  "output_dir": "output",
  "template": null,
  "current_step": 3,
  "total_steps": 9,
  "rfp_analysis": { ... },
  "phase_contents": {
    "0": { "type": "teaser", "data": { ... } },
    "1": { "type": "phase", "data": { ... } }
  },
  "win_themes": [ ... ],
  "cross_phase_summaries": [ ... ],
  "started_at": "2026-03-04T12:00:00.000000"
}
```

---

## 구현 내용

### 1. `src/manual/__init__.py`

- `ManualOrchestrator`, `_step_request_file_name`, `_step_response_file_name` export.  
  단계별 요청/응답 파일명은 `{step}_step_{Phase명}_request.txt` / `_response.txt` 규칙 (STEP_FILE_LABELS 참고).

### 2. `src/manual/manual_orchestrator.py`

**파일명 라벨:** `STEP_FILE_LABELS` = { 1: "RFPAnalyzer", 2: "HOOK", 3: "SUMMARY", 4: "INSIGHT", 5: "CONCEPT", 6: "ACTION_PLAN", 7: "MANAGEMENT", 8: "WHY_US", 9: "INVESTMENT" }  
**헬퍼:** `_step_request_file_name(step)`, `_step_response_file_name(step)` → 위 규칙의 파일명 반환.

**주요 클래스: `ManualOrchestrator`**

```python
class ManualOrchestrator:
    def __init__(self, manual_dir: Path = Path("manual"))

    def start(rfp_path, project_name, client_name, proposal_type=None,
              company_data_path=None, output_dir=Path("output"), template=None)  # generate --manual
    def continue_step() -> bool   # continue 명령 (완료 시 True, PPTX 생성됨)
    def get_status() -> dict      # status 명령

    # Private helpers
    def _parse_rfp(rfp_path) -> dict
    def _build_rfp_analysis_prompt(parsed_rfp) -> (str, str)
    def _build_phase0_prompt(rfp_analysis, state) -> (str, str)
    def _build_phase_prompt(phase_num, rfp_analysis, state) -> (str, str)
    def _write_request_file(step, system_prompt, user_message)
    def _extract_json(text) -> dict
    def _normalize_keys(data, aliases) -> dict
    def _process_step1(json_data, state)      # Step 1 응답 → RFPAnalysis 저장
    def _process_phase_step(step, phase_num, json_data, state) -> bool
    def _parse_teaser(json_data, state) -> TeaserContent
    def _generate_pptx(state) -> bool
    def _build_proposal_content(state) -> ProposalContent
    def _save_state(state) / _load_state() -> dict
```

**핵심 전략:**

- Settings를 임시로 `gemini` + `gemini_api_key="manual_mode_no_api_call"` 로 패치한 뒤  
  `ContentGenerator(api_key="manual_mode_no_api_call")`, `RFPAnalyzer(...)` 인스턴스 생성 (LLM 호출 없이 프롬프트/파싱만 사용).
- `_load_prompt()`, `_build_phase_user_message()`, `_parse_slides()` 등 기존 메서드 재활용.
- LLM을 호출하는 부분만 파일 I/O(요청 파일 생성·응답 파일 읽기)로 대체.

### 3. `main.py`

**추가/변경 내용:**

- `generate` 명령에 `--manual` / `-m` 옵션 추가. 사용 시 `_run_manual_generate()` 호출.
- `continue` 명령 추가: `ManualOrchestrator(manual_dir).continue_step()` 호출. `--manual-dir` 옵션 지원.
- `status` 명령 추가: `ManualOrchestrator(manual_dir).get_status()` 출력. `--manual-dir` 옵션 지원.

---

## 기존 코드 재활용 전략

| 기존 클래스/메서드                          | 재활용 방식                                   |
| ------------------------------------------ | --------------------------------------------- |
| `src/parsers/` (get_parser_for_path 등)    | RFP 파싱                                      |
| `ContentGenerator._load_prompt()`          | Phase 시스템 프롬프트 로드                     |
| `ContentGenerator._build_phase_user_message()` | Phase 1~7 사용자 메시지 빌드              |
| `ContentGenerator._parse_slides()`         | 응답 JSON에서 슬라이드 파싱                    |
| `ContentGenerator._extract_win_themes()`   | Phase 1 응답에서 Win Theme 추출               |
| `ContentGenerator._extract_phase_summary()`| Cross-Phase Context용 결론 추출               |
| `ContentGenerator._build_win_theme_models()`| win_themes → WinTheme 모델 변환               |
| `ContentGenerator._extract_key_messages()` | one_sentence_pitch, slogan 등 추출           |
| `RFPAnalyzer._load_prompt()`, `_get_default_system_prompt()` | RFP 분석 시스템 프롬프트 |
| `RFPAnalyzer._extract_json()` (BaseAgent 상속) | 응답 텍스트에서 JSON 추출                 |
| `RFPAnalyzer._normalize_json_keys()`       | 키 정규화 (_normalize_keys에서 사용)          |
| `PPTXOrchestrator.execute()`               | 최종 PPTX 생성                                |
| `config/prompts/*.txt`                     | 모든 프롬프트 파일 그대로 사용                 |

---

## 변경하지 않는 파일

- `src/agents/base_agent.py` — 변경 없음
- `src/agents/rfp_analyzer.py` — 변경 없음
- `src/agents/content_generator.py` — 변경 없음
- `src/orchestrators/proposal_orchestrator.py` — 변경 없음
- `src/orchestrators/pptx_orchestrator.py` — 변경 없음
- `config/prompts/*.txt` — 변경 없음
- `src/parsers/` — 변경 없음
- `src/schemas/` — 변경 없음
