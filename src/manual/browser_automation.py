"""
수동 모드 브라우저 자동화: 사람이 하던 '요청 복사 → 붙여넣기 → 응답 복사'만 자동화합니다.

- request 파일 내용을 읽어 → Gemini/ChatGPT 웹 입력란에 붙여넣기 → 전송 → 응답 수신 → response 파일에 저장
- 1~9단계의 요청/응답 생성·파일 저장·다음 단계 진행 등 나머지 흐름은 기존 manual 오케스트레이션 그대로 사용

사용: python main.py manual-run --site gemini  (또는 --site chatgpt)

실행 전: playwright install chromium
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger("browser_automation")


def _step_log(step: str, message: str, step_label: Optional[str] = None) -> None:
    """단계별 진행 상황을 한 줄만 출력 (시간 포함). step_label이 있으면 'Step k/9' 등 단계 정보를 앞에 붙임."""
    ts = datetime.now().strftime("%H:%M:%S")
    prefix = f"[{step_label}] " if step_label else ""
    line = f"{ts}  {prefix}{step} {message}"
    try:
        print(line, flush=True)
    except Exception:
        pass

# request 파일 구분자 (manual_orchestrator._write_request_file 형식과 일치)
SYSTEM_MARKER = "[시스템 프롬프트 (System Instructions)]"
USER_MARKER = "[사용자 메시지 (User Message)]"


def parse_request_file(request_path: Path) -> Tuple[str, str]:
    """
    N_step_*_request.txt 파일에서 [시스템 프롬프트]와 [사용자 메시지] 추출.

    Returns:
        (system_prompt, user_message)
    """
    text = request_path.read_text(encoding="utf-8")

    if USER_MARKER not in text:
        raise ValueError(f"요청 파일에 '{USER_MARKER}' 구간이 없습니다: {request_path}")

    before_user, _, after_user = text.partition(USER_MARKER)
    user_part = after_user.strip()
    if "=====================================" in user_part:
        user_message = user_part.split("=====================================", 1)[-1].strip()
    else:
        user_message = user_part.strip()

    if SYSTEM_MARKER not in before_user:
        raise ValueError(f"요청 파일에 '{SYSTEM_MARKER}' 구간이 없습니다: {request_path}")

    sys_part = before_user.split(SYSTEM_MARKER, 1)[-1].strip()
    if "=====================================" in sys_part:
        system_prompt = sys_part.split("=====================================")[0].strip()
    else:
        system_prompt = sys_part.strip()

    return system_prompt, user_message


def _extract_last_json_from_response(full_text: str) -> str:
    """캡처된 응답(요청+템플릿+실제 LLM 응답 혼합)에서 실제 LLM 응답 JSON만 추출.
    마지막 ```json 블록 또는 마지막 균형 잡힌 { } 블록을 반환. 없거나 너무 짧으면 원문 반환.
    """
    def _looks_like_prompt_schema(s: str) -> bool:
        """
        프롬프트에 포함된 '예시 JSON/스키마'를 응답으로 오인 저장하는 경우가 잦아 방어.
        - slide_type에 파이프(|)로 옵션 나열
        - '슬라이드 제목 (★ ...)' 등 설명 문구
        - '프로젝트명', '발주처명' 같은 플레이스홀더 값
        """
        t = (s or "").strip()
        if not t:
            return False
        # 강한 시그널: 옵션 나열/설명 문구
        schema_markers = (
            "section_divider|content|two_column",
            "slide_type\": \"section_divider|content",
            "슬라이드 제목 (★",
            "헤더1",
            "데이터1",
            "--- [시스템 지시] ---",
            "--- [사용자 메시지] ---",
            "위 내용을 분석하여 다음 JSON 형식으로",
            "중요: 응답은 반드시 유효한 JSON만 포함",
        )
        if any(m in t for m in schema_markers):
            return True
        # 약한 시그널: 값 자체가 '프로젝트명/발주처명' 같은 템플릿
        if "\"project_name\"" in t and ("\"프로젝트명\"" in t or "프로젝트명 미확인" in t):
            return True
        # 옵션 나열형 파이프(|)가 과도하면 스키마일 확률이 높음
        if t.count("|") >= 6:
            return True
        return False

    if not (full_text or "").strip():
        return full_text or ""
    text = full_text.strip()
    candidates: list = []
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)\s*```", text):
        block = (m.group(1) or "").strip()
        if len(block) > 20:
            candidates.append((m.start(), block))
    i = 0
    while i < len(text):
        if text[i] == "{":
            start = i
            depth = 0
            for j, c in enumerate(text[i:], i):
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        block = text[start : j + 1].strip()
                        if len(block) > 20:
                            candidates.append((start, block))
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1
    if not candidates:
        return text
    # 일반적으로 마지막 블록이 실제 LLM 응답이지만, 프롬프트 예시 JSON이 잡힐 때가 있어 역순으로 검증
    for _, cand in reversed(candidates):
        if _looks_like_prompt_schema(cand):
            continue
        try:
            parsed = json.loads(cand)
            if isinstance(parsed, (dict, list)):
                return cand
        except Exception:
            continue
        return cand
    # 전부 스키마처럼 보이면 마지막 후보 반환(기존 동작)
    _, last_content = candidates[-1]
    return last_content


def _combined_prompt(system_prompt: str, user_message: str) -> str:
    """웹 UI가 단일 입력만 지원할 때 사용할 통합 프롬프트."""
    return (
        "다음 [시스템 지시]를 반드시 따르고, [사용자 메시지]에 대해 JSON 등 요청 형식으로만 답하세요.\n\n"
        "--- [시스템 지시] ---\n"
        f"{system_prompt}\n\n"
        "--- [사용자 메시지] ---\n"
        f"{user_message}"
    )


# 로그인 완료 신호 파일 (manual-run이 대기, login 명령이 생성)
LOGIN_SIGNAL_FILENAME = ".manual_run_login_done"

# 자동화 탐지 완화용 브라우저 인자 (Google/OpenAI 등이 봇으로 차단하는 것 완화)
_BROWSER_ARGS = ["--disable-blink-features=AutomationControlled"]
_IGNORE_DEFAULT_ARGS = ["--enable-automation"]


def _wait_for_login_signal(signal_path: Path, timeout_sec: int = 300) -> None:
    """signal_path 파일이 생성될 때까지 대기 (최대 timeout_sec). 생성 후 파일 삭제."""
    for _ in range(max(1, timeout_sec // 2)):
        if signal_path.exists():
            try:
                signal_path.unlink(missing_ok=True)
            except Exception:
                pass
            return
        time.sleep(2)
    raise TimeoutError(f"로그인 완료 신호 대기 시간({timeout_sec}초)을 초과했습니다. python main.py login 을 실행했는지 확인하세요.")


def _wait_for_login_stdin() -> None:
    """같은 터미널에서 로그인 완료 후 Enter 입력을 기다림."""
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        print("\n" + "=" * 60, flush=True)
        print(f"{ts}  [로그인 확인] 브라우저에서 로그인을 완료한 뒤, 이 터미널에서 Enter를 누르세요.", flush=True)
        print("=" * 60, flush=True)
        input("  Enter를 누르면 계속 진행합니다: ")
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(1)


# fill()로 한 번에 넣은 뒤 전송 전 대기(ms). UI가 반영·전송 버튼 활성화 시간
_AFTER_FILL_DELAY_MS = 1000

# 스트리밍 응답 완료 감지: 이 간격(초)마다 길이 체크, 연속 N회 동일하면 완료
_RESPONSE_STABLE_INTERVAL_SEC = 0.5
_RESPONSE_STABLE_COUNT = 2  # 연속 2회 길이 동일 시 완료 (0.5s×2 = 1초)
_MIN_RESPONSE_LEN = 50
# 응답 영역 등장 후 최소 대기(ms). 곧바로 길이 폴링 시작
_RESPONSE_POLL_START_MS = 300
# 진행 로그 출력 간격(초). 응답 대기 중 "N자 수신, 완료 대기" 출력
_RESPONSE_PROGRESS_LOG_INTERVAL_SEC = 5
# 새 응답 대기 최대 시간(초). 너무 짧으면 이전 단계 응답을 재저장할 수 있어 여유를 둠
_RESPONSE_NEW_WAIT_MAX_SEC = 20
# 스트리밍 안정화(길이 동일) 최대 대기 시간(초). UI가 계속 리렌더링되면 무한 대기처럼 보일 수 있어 상한을 둠
_RESPONSE_STABILITY_MAX_SEC = 20
# 응답 영역 selector 최초 대기(ms). 여기서 막히지 않도록 짧게
_RESPONSE_FIRST_SELECTOR_TIMEOUT_MS = 4_000

# 전송 후 JSON 파싱 기반 완료 판정(고정 대기 + 폴링)
_JSON_FIRST_WAIT_MS = 15_000
_JSON_RECHECK_INTERVAL_MS = 5_000
# 90초는 너무 길어 상한을 둠(전송 후 총 대기)
_JSON_MAX_WAIT_MS = 45_000


def _parse_step_number(step_label: Optional[str]) -> Optional[int]:
    """step_label(예: 'Step 2/9 | Phase 0: ...')에서 step 번호 추출."""
    if not step_label:
        return None
    m = re.search(r"\bStep\s+(\d+)\s*/\s*9\b", step_label)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _json_looks_like_previous_step(obj: object, step_num: Optional[int]) -> bool:
    """
    자동 수집이 실패하면 이전 단계(특히 Step1) 응답을 다시 저장하는 경우가 있음.
    - Step2~9에서 'project_info/requirements_analysis'만 있고 'slides'가 없으면 Step1 응답일 확률이 높음
    - Step2(HOOK)에서 teaser 핵심키(main_slogan/slides)가 없으면 실패 가능성
    """
    if step_num is None:
        return False
    if not isinstance(obj, dict):
        return False
    has_slides = isinstance(obj.get("slides"), list)
    has_project_info = isinstance(obj.get("project_info"), dict)
    has_req_analysis = isinstance(obj.get("requirements_analysis"), (dict, list))
    has_teaser = ("main_slogan" in obj) or ("sub_message" in obj) or has_slides

    if step_num == 1:
        return False
    if step_num == 2:
        # teaser 단계인데 teaser 키가 없고 Step1 구조만 있으면 실패
        return (not has_teaser) and (has_project_info or has_req_analysis)
    # Step3~9: slides가 필수에 가깝다. 없고 Step1 구조만 있으면 실패
    return (not has_slides) and (has_project_info or has_req_analysis)


def _json_matches_step_expectation(obj: object, step_num: Optional[int]) -> bool:
    """단계별로 기대하는 응답 형태인지 간단 검증 (자동 수집 실패 조기 탐지용)."""
    if step_num is None:
        # 라벨 파싱 실패 시에는 보수적으로 통과
        return True
    if not isinstance(obj, dict):
        return False
    if step_num == 1:
        # Step1: RFP 분석. project_name 또는 project_info 중 하나는 있어야 함
        return bool(obj.get("project_name") or isinstance(obj.get("project_info"), dict))
    if step_num == 2:
        # Step2: HOOK/Teaser. main_slogan 또는 slides(티저 슬라이드) 필요
        slides = obj.get("slides")
        return bool(obj.get("main_slogan") or (isinstance(slides, list) and len(slides) > 0))
    # Step3~9: slides 리스트가 사실상 필수
    slides = obj.get("slides")
    return isinstance(slides, list) and len(slides) > 0


def _get_last_response_length(page, selector: str) -> int:
    """마지막 응답 블록(selector로 매칭)의 텍스트 길이. 없으면 0."""
    try:
        return page.evaluate(
            """(selector) => {
                const els = document.querySelectorAll(selector);
                const last = els[els.length - 1];
                return last ? (last.innerText || '').length : 0;
            }""",
            selector,
        )
    except Exception:
        return 0


def _get_last_response_length_multi(page, selectors: list) -> int:
    """여러 선택자로 마지막 응답 블록 길이 시도, 최대값 반환 (Gemini/ChatGPT UI 차이 대응)."""
    out = 0
    for sel in selectors:
        try:
            n = page.evaluate(
                """(selector) => {
                    const els = document.querySelectorAll(selector);
                    const last = els[els.length - 1];
                    return last ? (last.innerText || '').length : 0;
                }""",
                sel,
            )
            if n > out:
                out = n
        except Exception:
            continue
    return out


def _get_response_block_count(page, selector: str) -> int:
    """응답 블록(selector) 개수. 새 턴이 추가됐는지 판단할 때 사용."""
    try:
        return page.evaluate(
            """(selector) => document.querySelectorAll(selector).length""",
            selector,
        )
    except Exception:
        return 0


# 전송 버튼 찾기: 시도당 타임아웃(ms). 짧게 해서 빠르게 시도 후 Enter 폴백
_SEND_BUTTON_TRY_MS = 600
_SEND_BUTTON_WAIT_AFTER_MS = 80


def _find_send_button_gemini(page):
    """Gemini 전송 버튼을 여러 선택자로 빠르게 시도. 찾으면 Locator 반환, 못 찾으면 None(Enter 폴백)."""
    # 1) getByRole (가장 흔한 케이스)
    for name in ["Send", "전송", "Send message", "submit", "Submit"]:
        try:
            btn = page.get_by_role("button", name=name)
            btn.wait_for(state="visible", timeout=_SEND_BUTTON_TRY_MS)
            page.wait_for_timeout(_SEND_BUTTON_WAIT_AFTER_MS)
            return btn
        except Exception:
            continue
    # 2) 단일 선택자 (타임아웃 짧게)
    for selector in [
        'button[aria-label*="Send"]',
        'button[aria-label*="전송"]',
        '[data-icon="send"]',
        'button:has([data-icon="send"])',
        'button[type="submit"]',
        'button:has(svg)',
    ]:
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=_SEND_BUTTON_TRY_MS)
            page.wait_for_timeout(_SEND_BUTTON_WAIT_AFTER_MS)
            return el
        except Exception:
            continue
    return None


def _find_send_button_chatgpt(page):
    """ChatGPT 전송 버튼을 여러 선택자로 빠르게 시도. 찾으면 Locator 반환, 못 찾으면 None(Enter 폴백)."""
    # 1) data-testid (ChatGPT 공식, 가장 먼저)
    for selector in [
        'button[data-testid="send-button"]',
        '[data-testid="send-button"]',
        'button[aria-label*="Send"]',
        'button[aria-label="Send"]',
    ]:
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=_SEND_BUTTON_TRY_MS)
            page.wait_for_timeout(_SEND_BUTTON_WAIT_AFTER_MS)
            return el
        except Exception:
            continue
    # 2) getByRole
    for name in ["Send", "전송", "Submit", "submit"]:
        try:
            btn = page.get_by_role("button", name=name)
            btn.wait_for(state="visible", timeout=_SEND_BUTTON_TRY_MS)
            page.wait_for_timeout(_SEND_BUTTON_WAIT_AFTER_MS)
            return btn
        except Exception:
            continue
    # 3) 기타
    for selector in ['button:has(svg)', 'form button[type="submit"]']:
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=_SEND_BUTTON_TRY_MS)
            page.wait_for_timeout(_SEND_BUTTON_WAIT_AFTER_MS)
            return el
        except Exception:
            continue
    return None


def _wait_for_response_stable(
    page,
    response_selectors: list,
    timeout_ms: int,
    min_after_first_ms: Optional[int] = None,
    last_message_selector: Optional[str] = None,
    baseline_len: int = 0,
    baseline_count: int = 0,
    step_num: Optional[int] = None,
) -> None:
    """응답 영역이 보이면 폴링해, 새 응답이 나온 뒤 길이가 안정되면 완료로 간주하고 다음 단계 진행."""
    first_sel = response_selectors[0] if response_selectors else ""
    sel_for_wait = last_message_selector or first_sel
    length_selectors = [s for s in [sel_for_wait, first_sel] + response_selectors if s]
    length_selectors = list(dict.fromkeys(length_selectors))

    def _current_length() -> int:
        return _get_last_response_length_multi(page, length_selectors) if len(length_selectors) > 1 else (
            _get_last_response_length(page, sel_for_wait) if sel_for_wait else 0
        )

    def _current_count() -> int:
        return _get_response_block_count(page, sel_for_wait) if sel_for_wait else 0

    # 응답 영역이 없어도 오래 막히지 않도록 짧은 타임아웃만 사용 (실패 시 바로 폴링 루프로)
    first_wait_ms = min(_RESPONSE_FIRST_SELECTOR_TIMEOUT_MS, timeout_ms)
    try:
        page.wait_for_selector(first_sel, timeout=first_wait_ms)
    except Exception:
        pass
    initial_wait_ms = min_after_first_ms if min_after_first_ms is not None else _RESPONSE_POLL_START_MS
    page.wait_for_timeout(initial_wait_ms)

    deadline = time.time() + (timeout_ms / 1000.0)
    new_response_deadline = time.time() + _RESPONSE_NEW_WAIT_MAX_SEC
    last_progress_log = 0.0
    # 1) 새 응답이 나올 때까지 폴링 (최대 10초 후 무조건 다음 단계로)
    while time.time() < deadline:
        try:
            length = _current_length()
            count = _current_count()
        except Exception:
            length, count = 0, 0
        now = time.time()
        if now - last_progress_log >= _RESPONSE_PROGRESS_LOG_INTERVAL_SEC:
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"{ts}  [응답 대기] {length}자 (블록 {count}개), 새 응답 감지 대기 중...", flush=True)
            except Exception:
                pass
            last_progress_log = now
        # 새 응답 도착: 길이 증가 또는 블록 개수 증가
        if length > baseline_len and length >= _MIN_RESPONSE_LEN:
            break
        if baseline_count >= 0 and count > baseline_count and length >= 10:
            break
        # 최대 대기(10초) 초과 시 무조건 다음 단계로 진행 (감지 실패 시에도 멈추지 않음)
        if now >= new_response_deadline:
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"{ts}  [응답 대기] {_RESPONSE_NEW_WAIT_MAX_SEC}초 경과, 다음 단계로 진행합니다.", flush=True)
            except Exception:
                pass
            break
        time.sleep(0.4)
    else:
        return

    # 2) 길이 안정(스트리밍 종료) 체크: 연속 N회 동일하면 완료. 10초 타임아웃으로 들어왔으면 짧게만 대기
    prev_len = -1
    stable = 0
    forced_break = length < _MIN_RESPONSE_LEN
    stability_deadline = time.time() + (1.5 if forced_break else min(_RESPONSE_STABILITY_MAX_SEC, (timeout_ms / 1000.0)))
    while time.time() < stability_deadline:
        try:
            length = _current_length()
        except Exception:
            length = 0
        now = time.time()
        if now - last_progress_log >= _RESPONSE_PROGRESS_LOG_INTERVAL_SEC:
            try:
                ts = datetime.now().strftime("%H:%M:%S")
                print(f"{ts}  [응답 대기] {length}자 수신 중, 스트리밍 완료 시 자동 진행...", flush=True)
            except Exception:
                pass
            last_progress_log = now
        # 길이 안정화가 안 되더라도, 마지막 메시지에서 JSON 파싱이 성공하면 완료로 간주
        if step_num is not None and sel_for_wait:
            try:
                latest_text = page.evaluate(
                    """(selector) => {
                        const els = document.querySelectorAll(selector);
                        const last = els[els.length - 1];
                        return last ? ((last.innerText || '')).trim() : '';
                    }""",
                    sel_for_wait,
                )
                cand = _extract_last_json_from_response(latest_text or "")
                if cand and cand.strip().startswith("{"):
                    try:
                        parsed = json.loads(cand)
                    except Exception:
                        parsed = None
                    if parsed is not None and _json_matches_step_expectation(parsed, step_num):
                        return
            except Exception:
                pass
        if length >= _MIN_RESPONSE_LEN and length == prev_len:
            stable += 1
            if stable >= _RESPONSE_STABLE_COUNT:
                return
        else:
            stable = 0
        prev_len = length
        time.sleep(_RESPONSE_STABLE_INTERVAL_SEC)


def _run_gemini_flow(
    system_prompt: str,
    user_message: str,
    response_path: Path,
    *,
    headless: bool = False,
    timeout_ms: int = 300_000,
    login_signal_path: Optional[Path] = None,
    login_via_stdin: bool = True,
    browser_channel: Optional[str] = None,
    user_data_dir: Optional[Path] = None,
    step_label: Optional[str] = None,
    existing_page=None,
    close_on_exit: bool = True,
    first_step_goto: bool = False,
    screenshot_path: Optional[Path] = None,
):
    """Playwright로 Gemini 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장.
    existing_page가 있으면 해당 페이지 재사용(close_on_exit 무시).
    first_step_goto=True면 재사용 시에도 한 번 URL로 이동(브라우저가 blank로 열린 경우 대비).
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://gemini.google.com/app"
    step_num = _parse_step_number(step_label)

    def _do_step(page, goto: bool) -> None:
        if goto:
            _step_log("(2/9)", f"페이지 로드 중: {url}", step_label=step_label)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass

        if login_signal_path is not None:
            if login_via_stdin:
                _step_log("(3/9)", "로그인 완료 후 이 터미널에서 Enter 대기 중...", step_label=step_label)
                _wait_for_login_stdin()
            else:
                _step_log("(3/9)", "로그인 신호 파일 대기 중 (다른 터미널에서 python main.py login)...", step_label=step_label)
                _wait_for_login_signal(login_signal_path, timeout_sec=timeout_ms // 1000)
        else:
            _step_log("(3/9)", "로그인 대기 생략 (wait_for_login=False).", step_label=step_label)

        _step_log("(4/9)", "프롬프트 입력란 찾는 중...", step_label=step_label)
        input_selector = 'textarea[placeholder*="물어보기"], textarea[placeholder*="Gemini"], [contenteditable="true"][aria-label*="입력"], [role="textbox"]'
        input_el = page.wait_for_selector(input_selector, timeout=15_000)
        input_el.click()
        _step_log("(5/9)", f"프롬프트 한 번에 입력 중 ({len(combined)}자)...", step_label=step_label)
        input_el.fill(combined)
        _step_log("(6/9)", f"전송 전 대기 ({_AFTER_FILL_DELAY_MS}ms)...", step_label=step_label)
        page.wait_for_timeout(_AFTER_FILL_DELAY_MS)

        # Gemini UI는 코드블록(code-container)로 JSON을 렌더링하는 경우가 많아 이를 우선 감지
        gemini_code_sel = 'code[data-test-id="code-content"], code.code-container, .code-container'
        gemini_last_sel = gemini_code_sel

        _gemini_collect_script = """() => {
            const skipPrompt = (txt) => {
                if (!txt) return true;
                const t = txt;
                return (
                    t.indexOf('--- [시스템 지시] ---') >= 0 ||
                    t.indexOf('--- [사용자 메시지] ---') >= 0 ||
                    t.indexOf('중요: 응답은 반드시 유효한 JSON만 포함') >= 0 ||
                    t.indexOf('위 내용을 분석하여 다음 JSON 형식으로') >= 0 ||
                    t.indexOf('section_divider|content|two_column') >= 0 ||
                    t.indexOf('슬라이드 제목 (★') >= 0
                );
            };
            const textOf = (el) => { try { return el ? ((el.innerText || el.textContent || '')).trim() : ''; } catch(e) { return ''; } };
            const qsaLastText = (root, s) => {
                try {
                    const els = root.querySelectorAll(s);
                    const last = els[els.length - 1];
                    return textOf(last);
                } catch(e) { return ''; }
            };
            const getRoots = () => {
                // Gemini는 chat-app(web component) 아래 Shadow DOM에 렌더될 수 있어 함께 스캔
                const roots = [document];
                try {
                    const app = document.querySelector('chat-app');
                    if (app && app.shadowRoot) roots.push(app.shadowRoot);
                } catch(e) {}
                return roots;
            };
            const roots = getRoots();
            const selAllLast = (s) => {
                let out = '';
                for (let i = 0; i < roots.length; i++) {
                    const t = qsaLastText(roots[i], s);
                    if (t) out = t;
                }
                return (out || '').trim();
            };
            const sel = (s) => { 
                for (let i = 0; i < roots.length; i++) {
                    try { 
                        const el = roots[i].querySelector(s);
                        const t = textOf(el);
                        if (t) return t;
                    } catch(e) {}
                }
                return '';
            };

            // 0) 가장 우선: 코드 블록(하이라이트된 JSON)
            let t = selAllLast('code[data-test-id="code-content"]') || selAllLast('code.code-container') || selAllLast('.code-container');
            if (t && t.length >= 40 && t.indexOf('{') >= 0 && !skipPrompt(t)) return t;

            // 1) 모델(author=model) 마지막 메시지
            t = selAllLast('[data-message-author="model"]');
            if (t && t.length >= 50 && !skipPrompt(t)) return t;

            // 2) 모델 메시지 전체에서 마지막 "유의미" 텍스트
            try {
                const els = document.querySelectorAll('[data-message-author="model"]');
                for (let i = els.length - 1; i >= 0; i--) {
                    const txt = ((els[i].innerText || '')).trim();
                    if (txt && txt.length >= 50 && !skipPrompt(txt)) return txt;
                }
            } catch(e) {}

            // 3) 마지막에 가까운 메시지/응답 컨테이너 후보
            t = selAllLast('[class*="model"]') || selAllLast('[class*="response"]') || selAllLast('[class*="message"]');
            if (t && t.length >= 50 && !skipPrompt(t)) return t;

            // 4) fallback
            t = sel('article') || sel('[role="main"]') || sel('main');
            if (t && t.length >= 50 && !skipPrompt(t)) return t;
            return (document.body.innerText || '').trim();
        }"""

        baseline_text = ""
        baseline_json = ""
        try:
            baseline_text = page.evaluate(_gemini_collect_script) or ""
            baseline_json = _extract_last_json_from_response(baseline_text) if baseline_text else ""
        except Exception:
            baseline_text = ""
            baseline_json = ""

        _step_log("(7/9)", "전송 버튼 찾는 중...", step_label=step_label)
        send_btn = _find_send_button_gemini(page)
        if send_btn:
            send_btn.click()
        else:
            _step_log("(7/9)", "전송 버튼 대신 Enter 키로 전송 시도...", step_label=step_label)
            input_el.click()
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")

        _step_log("(8/9)", f"전송 후 기본 대기({_JSON_FIRST_WAIT_MS // 1000}초)...", step_label=step_label)
        page.wait_for_timeout(_JSON_FIRST_WAIT_MS)

        # 전송 후부터는 code-content(JSON 코드블록) 파싱 성공을 완료 기준으로 사용
        # 실패 시 5초 단위로 재체크 (최대 _JSON_MAX_WAIT_MS)
        start = time.time()
        to_save = ""
        parsed = None
        while True:
            try:
                response_text = page.evaluate(_gemini_collect_script) or ""
            except Exception:
                response_text = ""

            # 요청/템플릿/UI가 섞여 있으면 실제 LLM 응답 JSON만 추출해 저장
            to_save = _extract_last_json_from_response(response_text or "")
            if not to_save.strip():
                to_save = (response_text or "").strip()

            try:
                parsed = json.loads(to_save) if to_save.strip().startswith("{") else None
            except Exception:
                parsed = None

            ok = False
            if parsed is not None:
                ok = (
                    (not baseline_json or to_save.strip() != baseline_json.strip())
                    and (not _json_looks_like_previous_step(parsed, step_num))
                    and _json_matches_step_expectation(parsed, step_num)
                )

            if ok:
                break

            elapsed_ms = int((time.time() - start) * 1000)
            if elapsed_ms >= min(_JSON_MAX_WAIT_MS, timeout_ms):
                raise RuntimeError(
                    f"Gemini 응답 수집 실패: JSON 파싱/검증이 완료되지 않았습니다. step={step_num} response={response_path}"
                )
            _step_log("(8b/9)", f"JSON 파싱 실패/미완료 → {_JSON_RECHECK_INTERVAL_MS // 1000}초 후 재체크", step_label=step_label)
            page.wait_for_timeout(_JSON_RECHECK_INTERVAL_MS)

        # Step2~9에서 새 응답 감지가 실패하면 Step1 응답을 재저장할 수 있어, JSON 구조로 1회 재검증/재수집
        # (위 루프에서 이미 검증 완료했으므로, 여기서는 안전망만 유지)
        if _json_looks_like_previous_step(parsed, step_num) or (parsed is not None and not _json_matches_step_expectation(parsed, step_num)):
            logger.warning("Gemini 응답이 이전 단계 응답으로 보입니다. 5초 후 재수집합니다. step=%s", step_num)
            page.wait_for_timeout(5000)
            response_text = page.evaluate(_gemini_collect_script)
            if not (response_text and len(response_text) >= _MIN_RESPONSE_LEN):
                response_text = page.evaluate("() => document.body.innerText || ''").strip()
            to_save = _extract_last_json_from_response(response_text or "")
            if not to_save.strip():
                to_save = (response_text or "").strip()
            try:
                parsed = json.loads(to_save) if to_save.strip().startswith("{") else None
            except Exception:
                parsed = None
            if _json_looks_like_previous_step(parsed, step_num) or (parsed is not None and not _json_matches_step_expectation(parsed, step_num)):
                # 자동 실행이 계속 진행되면 response 파일이 전부 같은 값으로 덮이는 문제가 발생하므로 강제 중단
                raise RuntimeError(
                    f"Gemini 응답 수집 실패: Step {step_num}에서 새 응답을 감지하지 못했습니다. "
                    f"이전 단계 응답이 반복 저장되는 상태입니다. response={response_path}"
                )

        if not to_save.strip().startswith("{") and '"project_name"' not in to_save and '"slides"' not in to_save:
            logger.warning("Gemini 응답에서 JSON을 찾지 못함. 대화 영역 선택자가 맞지 않을 수 있음. 수집 길이: %s", len(to_save))
        response_path.write_text(to_save, encoding="utf-8")
        _step_log("(9/9)", f"응답 수집·저장 완료: {len(to_save)}자 → {response_path}", step_label=step_label)
        logger.info("Gemini 응답 저장: {} ({}자)", response_path, len(to_save))

    if existing_page is not None:
        existing_page.set_default_timeout(min(timeout_ms, 60_000))
        try:
            _do_step(existing_page, goto=first_step_goto)
        except Exception:
            if screenshot_path is not None:
                try:
                    existing_page.screenshot(path=str(screenshot_path), full_page=True)
                    logger.warning("자동화 실패 스크린샷 저장: {}", screenshot_path)
                except Exception:
                    pass
            raise
        return

    _step_log("(1/9)", "브라우저 시작 중 (Gemini)...", step_label=step_label)
    with sync_playwright() as p:
        browser = None
        if user_data_dir is not None:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless,
                channel=browser_channel,
                args=_BROWSER_ARGS,
                ignore_default_args=_IGNORE_DEFAULT_ARGS,
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        else:
            browser = p.chromium.launch(
                headless=headless,
                channel=browser_channel,
                args=_BROWSER_ARGS,
                ignore_default_args=_IGNORE_DEFAULT_ARGS,
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        page = context.new_page()
        page.set_default_timeout(min(timeout_ms, 60_000))
        try:
            _do_step(page, goto=True)
        except Exception:
            if screenshot_path is not None:
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    logger.warning("자동화 실패 스크린샷 저장: {}", screenshot_path)
                except Exception:
                    pass
            raise
        finally:
            if close_on_exit:
                try:
                    context.close()
                finally:
                    if browser is not None:
                        browser.close()


def _run_chatgpt_flow(
    system_prompt: str,
    user_message: str,
    response_path: Path,
    *,
    headless: bool = False,
    timeout_ms: int = 300_000,
    login_signal_path: Optional[Path] = None,
    login_via_stdin: bool = True,
    browser_channel: Optional[str] = None,
    user_data_dir: Optional[Path] = None,
    step_label: Optional[str] = None,
    existing_page=None,
    close_on_exit: bool = True,
    first_step_goto: bool = False,
    screenshot_path: Optional[Path] = None,
) -> None:
    """Playwright로 ChatGPT 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장.
    existing_page가 있으면 해당 페이지 재사용(close_on_exit 무시).
    first_step_goto=True면 재사용 시에도 한 번 URL로 이동(브라우저가 blank로 열린 경우 대비).
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://chat.openai.com/"
    step_num = _parse_step_number(step_label)

    def _do_step(page, goto: bool) -> None:
        if goto:
            _step_log("(2/9)", f"페이지 로드 중: {url}", step_label=step_label)
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass

        if login_signal_path is not None:
            if login_via_stdin:
                _step_log("(3/9)", "로그인 완료 후 이 터미널에서 Enter 대기 중...", step_label=step_label)
                _wait_for_login_stdin()
            else:
                _step_log("(3/9)", "로그인 신호 파일 대기 중 (다른 터미널에서 python main.py login)...", step_label=step_label)
                _wait_for_login_signal(login_signal_path, timeout_sec=timeout_ms // 1000)
        else:
            _step_log("(3/9)", "로그인 대기 생략 (wait_for_login=False).", step_label=step_label)

        _step_log("(4/9)", "프롬프트 입력란 찾는 중...", step_label=step_label)
        input_el = None
        for input_selector in [
            "#prompt-textarea",
            'textarea[data-id="root"]',
            'textarea[placeholder*="Message"]',
            'textarea[placeholder*="메시지"]',
            'textarea[placeholder*="message"]',
            '[contenteditable="true"][data-id="root"]',
            'form textarea',
        ]:
            try:
                input_el = page.locator(input_selector).first
                input_el.wait_for(state="visible", timeout=3000)
                break
            except Exception:
                continue
        if input_el is None:
            raise RuntimeError("ChatGPT 입력란을 찾지 못했습니다. 웹 UI가 변경되었을 수 있습니다.")
        input_el.click()
        _step_log("(5/9)", f"프롬프트 한 번에 입력 중 ({len(combined)}자)...", step_label=step_label)
        input_el.fill(combined)
        _step_log("(6/9)", f"전송 전 대기 ({_AFTER_FILL_DELAY_MS}ms)...", step_label=step_label)
        page.wait_for_timeout(_AFTER_FILL_DELAY_MS)

        chatgpt_last_sel = '[data-testid="conversation-turn"]'
        assistant_sel = '[data-message-author-role="assistant"]'
        baseline_len = _get_last_response_length_multi(page, [assistant_sel, chatgpt_last_sel])
        baseline_count = _get_response_block_count(page, assistant_sel)
        if baseline_count <= 0:
            baseline_count = _get_response_block_count(page, chatgpt_last_sel)
        _step_log("(7/9)", "전송 버튼 찾는 중...", step_label=step_label)
        send_btn = _find_send_button_chatgpt(page)
        if send_btn:
            send_btn.click()
        else:
            _step_log("(7/9)", "전송 버튼 대신 Enter 키로 전송 시도...", step_label=step_label)
            input_el.click()
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")

        _step_log("(8/9)", "응답 수신 대기 중 (스트리밍 완료까지)...", step_label=step_label)
        _wait_for_response_stable(
            page,
            [assistant_sel, '[data-testid="conversation-turn"]', '[class*="result"]', '[class*="response"]'],
            timeout_ms,
            last_message_selector=assistant_sel,
            baseline_len=baseline_len,
            baseline_count=baseline_count,
            step_num=step_num,
        )

        response_text = page.evaluate(
            """() => {
                // assistant turn 우선
                const assistant = document.querySelectorAll('[data-message-author-role="assistant"]');
                const lastAssistant = assistant[assistant.length - 1];
                if (lastAssistant) {
                    const t = (lastAssistant.innerText || '').trim();
                    if (t) return t;
                }
                // 기존 fallback: 마지막 conversation-turn
                const turns = document.querySelectorAll('[data-testid="conversation-turn"]');
                const last = turns[turns.length - 1];
                if (last) return (last.innerText || '').trim();
                return '';
            }"""
        )
        if not (response_text and len(response_text) >= _MIN_RESPONSE_LEN):
            response_text = page.evaluate("() => document.body.innerText || ''").strip()

        # 요청/UI가 섞여 있으면 실제 LLM 응답 JSON만 추출해 저장
        to_save = _extract_last_json_from_response(response_text or "")
        if not to_save.strip():
            to_save = (response_text or "").strip()

        # Step2~9에서 이전 단계(특히 Step1) 응답을 재저장했는지 1회 재검증/재수집
        try:
            parsed = json.loads(to_save) if to_save.strip().startswith("{") else None
        except Exception:
            parsed = None
        if _json_looks_like_previous_step(parsed, step_num) or (parsed is not None and not _json_matches_step_expectation(parsed, step_num)):
            logger.warning("ChatGPT 응답이 이전 단계 응답으로 보입니다. 5초 후 재수집합니다. step=%s", step_num)
            page.wait_for_timeout(5000)
            response_text = page.evaluate(
                """() => {
                    const assistant = document.querySelectorAll('[data-message-author-role="assistant"]');
                    const lastAssistant = assistant[assistant.length - 1];
                    if (lastAssistant) {
                        const t = (lastAssistant.innerText || '').trim();
                        if (t) return t;
                    }
                    const turns = document.querySelectorAll('[data-testid="conversation-turn"]');
                    const last = turns[turns.length - 1];
                    if (last) return (last.innerText || '').trim();
                    return '';
                }"""
            )
            if not (response_text and len(response_text) >= _MIN_RESPONSE_LEN):
                response_text = page.evaluate("() => document.body.innerText || ''").strip()
            to_save = _extract_last_json_from_response(response_text or "")
            if not to_save.strip():
                to_save = (response_text or "").strip()
            try:
                parsed = json.loads(to_save) if to_save.strip().startswith("{") else None
            except Exception:
                parsed = None
            if _json_looks_like_previous_step(parsed, step_num) or (parsed is not None and not _json_matches_step_expectation(parsed, step_num)):
                raise RuntimeError(
                    f"ChatGPT 응답 수집 실패: Step {step_num}에서 새 응답을 감지하지 못했습니다. "
                    f"이전 단계 응답이 반복 저장되는 상태입니다. response={response_path}"
                )
        response_path.write_text(to_save, encoding="utf-8")
        _step_log("(9/9)", f"응답 수집·저장 완료: {len(to_save)}자 → {response_path}", step_label=step_label)
        logger.info("ChatGPT 응답 저장: {} ({}자)", response_path, len(to_save))

    if existing_page is not None:
        existing_page.set_default_timeout(min(timeout_ms, 60_000))
        try:
            _do_step(existing_page, goto=first_step_goto)
        except Exception:
            if screenshot_path is not None:
                try:
                    existing_page.screenshot(path=str(screenshot_path), full_page=True)
                    logger.warning("자동화 실패 스크린샷 저장: {}", screenshot_path)
                except Exception:
                    pass
            raise
        return

    _step_log("(1/9)", "브라우저 시작 중 (ChatGPT)...", step_label=step_label)
    with sync_playwright() as p:
        browser = None
        if user_data_dir is not None:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless,
                channel=browser_channel,
                args=_BROWSER_ARGS,
                ignore_default_args=_IGNORE_DEFAULT_ARGS,
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        else:
            browser = p.chromium.launch(
                headless=headless,
                channel=browser_channel,
                args=_BROWSER_ARGS,
                ignore_default_args=_IGNORE_DEFAULT_ARGS,
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        page = context.new_page()
        page.set_default_timeout(min(timeout_ms, 60_000))
        try:
            _do_step(page, goto=True)
        except Exception:
            if screenshot_path is not None:
                try:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    logger.warning("자동화 실패 스크린샷 저장: {}", screenshot_path)
                except Exception:
                    pass
            raise
        finally:
            if close_on_exit:
                try:
                    context.close()
                finally:
                    if browser is not None:
                        browser.close()


def launch_manual_browser(
    playwright_instance,
    site: str,
    *,
    headless: bool = False,
    browser_channel: Optional[str] = None,
    user_data_dir: Optional[Path] = None,
):
    """한 브라우저 세션을 띄우고 (context, page, browser_or_none) 반환. manual-run에서 1~9단계 재사용용."""
    p = playwright_instance
    browser = None
    site_clean = (site or "").strip().lower()
    if user_data_dir is not None:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=headless,
            channel=browser_channel,
            args=_BROWSER_ARGS,
            ignore_default_args=_IGNORE_DEFAULT_ARGS,
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
    else:
        browser = p.chromium.launch(
            headless=headless,
            channel=browser_channel,
            args=_BROWSER_ARGS,
            ignore_default_args=_IGNORE_DEFAULT_ARGS,
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            locale="ko-KR",
        )
    page = context.new_page()
    return (context, page, browser)


def run_automation(
    run_dir: Path,
    step: int,
    site: str,
    *,
    headless: bool = False,
    timeout_sec: int = 300,
    wait_for_login: bool = True,
    login_via_stdin: bool = True,
    browser_channel: Optional[str] = None,
    user_data_dir: Optional[Path] = None,
    step_label: Optional[str] = None,
    reuse_session: Optional[tuple] = None,
) -> Path:
    """
    사람이 하던 '요청 복사·붙여넣기·응답 복사'만 자동화: request 파일 → 웹에 붙여넣기·전송 → 응답을 response 파일에 저장.

    Args:
        run_dir: 수동 모드 run 폴더 (manual_req_res/run_YYYYMMDD_HHMMSS)
        step: 단계 번호 (1~9)
        site: "gemini" | "chatgpt"
        headless: True면 브라우저 창 숨김
        timeout_sec: 응답 대기 최대 초
        wait_for_login: True면 사이트 열린 뒤 로그인 완료 대기 후 전송
        login_via_stdin: True면 같은 터미널에서 Enter로 로그인 완료 확인, False면 파일 신호 대기

    Returns:
        저장된 response 파일 경로
    """
    from .manual_orchestrator import (
        STEP_DESCRIPTIONS,
        _step_request_file_name,
        _step_response_file_name,
    )

    run_dir = Path(run_dir)
    request_path = run_dir / _step_request_file_name(step)
    response_path = run_dir / _step_response_file_name(step)

    if not request_path.exists():
        raise FileNotFoundError(f"요청 파일이 없습니다: {request_path}")

    # Step + Phase 단계별 로그용 라벨 (예: "Step 1/9 | RFP 분석", "Step 2/9 | Phase 0: HOOK (티저)")
    phase_desc = STEP_DESCRIPTIONS.get(step, "")
    effective_step_label = f"{step_label} | {phase_desc}" if (step_label and phase_desc) else step_label

    if effective_step_label:
        _step_log("준비", f"request 파일 로드 완료 → 브라우저 자동화 시작 ({site})", step_label=effective_step_label)
    system_prompt, user_message = parse_request_file(request_path)
    timeout_ms = timeout_sec * 1000

    login_signal_path: Optional[Path] = None
    if wait_for_login:
        login_signal_path = run_dir.parent / LOGIN_SIGNAL_FILENAME
        if login_signal_path.exists():
            login_signal_path.unlink(missing_ok=True)

    site_lower = site.strip().lower()
    existing_page = reuse_session[1] if reuse_session and len(reuse_session) >= 2 else None
    close_on_exit = existing_page is None
    first_step_goto = existing_page is not None and step == 1
    screenshot_path = run_dir / f"{step}_step_automation_error.png"

    try:
        if site_lower == "gemini":
            _run_gemini_flow(
                system_prompt,
                user_message,
                response_path,
                headless=headless,
                timeout_ms=timeout_ms,
                login_signal_path=login_signal_path,
                login_via_stdin=login_via_stdin,
                browser_channel=browser_channel,
                user_data_dir=user_data_dir,
                step_label=effective_step_label,
                existing_page=existing_page,
                close_on_exit=close_on_exit,
                first_step_goto=first_step_goto,
                screenshot_path=screenshot_path,
            )
        elif site_lower == "chatgpt":
            _run_chatgpt_flow(
                system_prompt,
                user_message,
                response_path,
                headless=headless,
                timeout_ms=timeout_ms,
                login_signal_path=login_signal_path,
                login_via_stdin=login_via_stdin,
                browser_channel=browser_channel,
                user_data_dir=user_data_dir,
                step_label=effective_step_label,
                existing_page=existing_page,
                close_on_exit=close_on_exit,
                first_step_goto=first_step_goto,
                screenshot_path=screenshot_path,
            )
        else:
            raise ValueError(f"지원하지 않는 사이트입니다: {site}. gemini 또는 chatgpt 를 지정하세요.")
    except Exception as e:
        # 실패 시점 화면을 남겨 원인 추적 가능하게 (manual-run은 보통 reuse_session 사용)
        if existing_page is not None:
            try:
                existing_page.screenshot(path=str(screenshot_path), full_page=True)
                logger.warning("자동화 실패 스크린샷 저장: {}", screenshot_path)
            except Exception:
                pass
        raise

    return response_path
