"""
수동 모드 브라우저 자동화: 사람이 하던 '요청 복사 → 붙여넣기 → 응답 복사'만 자동화합니다.

- request 파일 내용을 읽어 → Gemini/ChatGPT 웹 입력란에 붙여넣기 → 전송 → 응답 수신 → response 파일에 저장
- 1~9단계의 요청/응답 생성·파일 저장·다음 단계 진행 등 나머지 흐름은 기존 manual 오케스트레이션 그대로 사용

사용: python main.py manual-run --site gemini  (또는 --site chatgpt)

실행 전: playwright install chromium
"""

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
# 새 응답 대기 최대 시간(초). 이후에도 감지 안 되면 무조건 다음 단계 진행
_RESPONSE_NEW_WAIT_MAX_SEC = 5
# 응답 영역 selector 최초 대기(ms). 여기서 막히지 않도록 짧게
_RESPONSE_FIRST_SELECTOR_TIMEOUT_MS = 4_000


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
    stability_deadline = time.time() + (1.5 if forced_break else (timeout_ms / 1000.0))
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
):
    """Playwright로 Gemini 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장.
    existing_page가 있으면 해당 페이지 재사용(close_on_exit 무시).
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://gemini.google.com/app"

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

        gemini_last_sel = '[data-message-author="model"]'
        baseline_len = _get_last_response_length_multi(
            page, ['[data-message-author="model"]', "article", '[class*="model"]', '[class*="response"]']
        )
        baseline_count = _get_response_block_count(page, gemini_last_sel)
        _step_log("(7/9)", "전송 버튼 찾는 중...", step_label=step_label)
        send_btn = _find_send_button_gemini(page)
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
            ['[data-message-author="model"]', '[class*="model"]', '[class*="response"]', "article"],
            timeout_ms,
            last_message_selector=gemini_last_sel,
            baseline_len=baseline_len,
            baseline_count=baseline_count,
        )

        # 응답 텍스트 수집: 마지막 model 메시지만 사용(이전 대화와 구분)
        response_text = page.evaluate(
            """() => {
                const els = document.querySelectorAll('[data-message-author="model"]');
                const last = els[els.length - 1];
                if (last) return (last.innerText || '').trim();
                const art = document.querySelector('article');
                return art ? art.innerText.trim() : '';
            }"""
        )
        if not (response_text and len(response_text) >= _MIN_RESPONSE_LEN):
            response_text = page.evaluate("() => document.body.innerText || ''").strip()

        response_path.write_text((response_text or "").strip(), encoding="utf-8")
        _step_log("(9/9)", f"응답 수집·저장 완료: {len(response_text)}자 → {response_path}", step_label=step_label)
        logger.info("Gemini 응답 저장: {} ({}자)", response_path, len(response_text))

    if existing_page is not None:
        existing_page.set_default_timeout(min(timeout_ms, 60_000))
        _do_step(existing_page, goto=False)
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
) -> None:
    """Playwright로 ChatGPT 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장.
    existing_page가 있으면 해당 페이지 재사용(close_on_exit 무시).
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://chat.openai.com/"

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
        baseline_len = _get_last_response_length(page, chatgpt_last_sel)
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
            ['[data-testid="conversation-turn"]', '[class*="result"]', '[class*="response"]'],
            timeout_ms,
            last_message_selector=chatgpt_last_sel,
            baseline_len=baseline_len,
            baseline_count=baseline_count,
        )

        response_text = page.evaluate(
            """() => {
                const turns = document.querySelectorAll('[data-testid="conversation-turn"]');
                const last = turns[turns.length - 1];
                if (last) return (last.innerText || '').trim();
                return '';
            }"""
        )
        if not (response_text and len(response_text) >= _MIN_RESPONSE_LEN):
            response_text = page.evaluate("() => document.body.innerText || ''").strip()

        response_path.write_text((response_text or "").strip(), encoding="utf-8")
        _step_log("(9/9)", f"응답 수집·저장 완료: {len(response_text)}자 → {response_path}", step_label=step_label)
        logger.info("ChatGPT 응답 저장: {} ({}자)", response_path, len(response_text))

    if existing_page is not None:
        existing_page.set_default_timeout(min(timeout_ms, 60_000))
        _do_step(existing_page, goto=False)
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
        )
    else:
        raise ValueError(f"지원하지 않는 사이트입니다: {site}. gemini 또는 chatgpt 를 지정하세요.")

    return response_path
