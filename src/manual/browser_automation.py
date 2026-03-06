"""
수동 모드 브라우저 자동화: 사람이 하던 '요청 복사 → 붙여넣기 → 응답 복사'만 자동화합니다.

- request 파일 내용을 읽어 → Gemini/ChatGPT 웹 입력란에 붙여넣기 → 전송 → 응답 수신 → response 파일에 저장
- 1~9단계의 요청/응답 생성·파일 저장·다음 단계 진행 등 나머지 흐름은 기존 manual 오케스트레이션 그대로 사용

사용: python main.py manual-step --site gemini
     python main.py manual-run --site gemini

실행 전: playwright install chromium
"""

import time
from pathlib import Path
from typing import Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger("browser_automation")


def _step_log(step: str, message: str, step_label: Optional[str] = None) -> None:
    """단계별 진행 상황을 콘솔과 로그에 출력. step_label이 있으면 'Step k/9' 등 단계 정보를 앞에 붙임."""
    prefix = f"[{step_label}] " if step_label else ""
    line = f"  {prefix}{step} {message}"
    logger.info("%s", line)
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


# 로그인 완료 신호 파일 (manual-step이 대기, login 명령이 생성)
LOGIN_SIGNAL_FILENAME = ".manual_step_login_done"

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
        print("\n" + "=" * 60, flush=True)
        print("  [로그인 확인] 브라우저에서 로그인을 완료한 뒤, 이 터미널에서 Enter를 누르세요.", flush=True)
        print("=" * 60, flush=True)
        input("  Enter를 누르면 계속 진행합니다: ")
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(1)


# fill()로 한 번에 넣은 뒤 전송 전 대기(ms). UI가 반영·전송 버튼 활성화 시간
_AFTER_FILL_DELAY_MS = 1000

# 스트리밍 응답 완료 감지: 이 간격(초)마다 길이 체크, 연속 N회 동일하면 완료
_RESPONSE_STABLE_INTERVAL_SEC = 1.2
_RESPONSE_STABLE_COUNT = 2  # 연속 N회 길이 동일 시 완료
_MIN_RESPONSE_LEN = 50
# 응답 영역 등장 후 최소 대기(ms). 곧바로 길이 폴링 시작
_RESPONSE_POLL_START_MS = 600


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


def _find_send_button_gemini(page):
    """Gemini 전송 버튼을 여러 선택자/방법으로 시도. 찾으면 Locator 반환, 못 찾으면 None."""
    # 1) getByRole
    for name in ["Send", "전송", "submit", "Submit", "Send message"]:
        try:
            btn = page.get_by_role("button", name=name)
            btn.wait_for(state="visible", timeout=3000)
            page.wait_for_timeout(300)
            return btn
        except Exception:
            continue
    # 2) 단일 선택자씩 시도
    for selector in [
        'button[aria-label*="Send"]',
        'button[aria-label*="전송"]',
        'button[aria-label*="send"]',
        'button[data-tooltip*="Send"]',
        'button[data-tooltip*="전송"]',
        '[data-icon="send"]',
        'button:has([data-icon="send"])',
        '[aria-label="Send"]',
        'button.send',
        'button[type="submit"]',
        'div[role="button"]:has(svg)',
        'button:has(svg)',
        'form button[type="submit"]',
        'button[data-id="send"]',
        '[class*="send"] button',
        'button[class*="send"]',
    ]:
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=1500)
            page.wait_for_timeout(300)
            return el
        except Exception:
            continue
    return None


def _find_send_button_chatgpt(page):
    """ChatGPT 전송 버튼을 여러 선택자로 시도. 찾으면 Locator 반환, 못 찾으면 None."""
    # 1) data-testid (ChatGPT 공식)
    for selector in [
        'button[data-testid="send-button"]',
        '[data-testid="send-button"]',
        'button[aria-label*="Send"]',
        'button[aria-label*="전송"]',
        'button[aria-label="Send"]',
    ]:
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=3000)
            page.wait_for_timeout(300)
            return el
        except Exception:
            continue
    # 2) getByRole
    for name in ["Send", "전송", "Submit", "submit"]:
        try:
            btn = page.get_by_role("button", name=name)
            btn.wait_for(state="visible", timeout=2000)
            page.wait_for_timeout(300)
            return btn
        except Exception:
            continue
    # 3) 기타
    for selector in [
        'button:has(svg[data-icon="send"])',
        'button:has(svg)',
        'form button[type="submit"]',
        '[class*="send"]',
    ]:
        try:
            el = page.locator(selector).first
            el.wait_for(state="visible", timeout=1500)
            page.wait_for_timeout(300)
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
) -> None:
    """응답 영역이 보이면 곧바로 폴링해, 새 응답(baseline 초과)이 나온 뒤 길이가 안정될 때까지 대기."""
    first_sel = response_selectors[0] if response_selectors else ""
    sel_for_wait = last_message_selector or first_sel
    page.wait_for_selector(first_sel, timeout=timeout_ms)
    initial_wait_ms = min_after_first_ms if min_after_first_ms is not None else _RESPONSE_POLL_START_MS
    page.wait_for_timeout(initial_wait_ms)

    deadline = time.time() + (timeout_ms / 1000.0)
    # 1) 새 응답이 나올 때까지 짧은 간격으로 폴링 (고정 긴 대기 없음)
    while time.time() < deadline:
        try:
            length = _get_last_response_length(page, sel_for_wait) if sel_for_wait else 0
        except Exception:
            length = 0
        if length > baseline_len and length >= _MIN_RESPONSE_LEN:
            break
        time.sleep(0.4)
    else:
        return

    # 2) 길이 안정(스트리밍 종료) 체크: 연속 N회 동일하면 완료
    prev_len = -1
    stable = 0
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        try:
            length = _get_last_response_length(page, sel_for_wait) if sel_for_wait else 0
        except Exception:
            length = 0
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
) -> None:
    """Playwright로 Gemini 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://gemini.google.com/app"

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
            baseline_len = _get_last_response_length(page, gemini_last_sel)
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

        finally:
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
) -> None:
    """Playwright로 ChatGPT 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://chat.openai.com/"

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
            )

            # 마지막 assistant 턴만 사용(이전 대화와 구분)
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

        finally:
            try:
                context.close()
            finally:
                if browser is not None:
                    browser.close()


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
        )
    else:
        raise ValueError(f"지원하지 않는 사이트입니다: {site}. gemini 또는 chatgpt 를 지정하세요.")

    return response_path
