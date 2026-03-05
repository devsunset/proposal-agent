"""
수동 모드 브라우저 자동화: request 파일 내용을 Gemini/ChatGPT 웹에 전송하고 응답을 response 파일에 저장.

사용: python main.py manual-step --site gemini
     python main.py manual-step --site chatgpt

실행 전: playwright install chromium
"""

import time
from pathlib import Path
from typing import Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger("browser_automation")

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


def _run_gemini_flow(
    system_prompt: str,
    user_message: str,
    response_path: Path,
    *,
    headless: bool = False,
    timeout_ms: int = 300_000,
    login_signal_path: Optional[Path] = None,
    browser_channel: Optional[str] = None,
    user_data_dir: Optional[Path] = None,
) -> None:
    """Playwright로 Gemini 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://gemini.google.com/app"

    with sync_playwright() as p:
        browser = None
        if user_data_dir is not None:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless,
                channel=browser_channel,
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        else:
            browser = p.chromium.launch(headless=headless, channel=browser_channel)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        page = context.new_page()
        page.set_default_timeout(min(timeout_ms, 60_000))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                # Gemini/ChatGPT는 지속적으로 네트워크가 발생해 networkidle이 자주 타임아웃됨 → 실패해도 진행
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass

            if login_signal_path is not None:
                _wait_for_login_signal(login_signal_path, timeout_sec=timeout_ms // 1000)

            # 프롬프트 입력란 (Gemini 웹 UI: placeholder 또는 role)
            input_selector = 'textarea[placeholder*="물어보기"], textarea[placeholder*="Gemini"], [contenteditable="true"][aria-label*="입력"], [role="textbox"]'
            input_el = page.wait_for_selector(input_selector, timeout=15_000)
            input_el.click()
            input_el.fill("")
            page.keyboard.type(combined, delay=10)

            # 전송 버튼
            send_btn = page.wait_for_selector(
                'button[aria-label*="전송"], button[aria-label*="Send"], button[data-tooltip*="전송"], [data-icon="send"], button:has(svg)',
                timeout=5_000,
            )
            send_btn.click()

            # 응답 영역 대기 (마지막 모델 메시지)
            page.wait_for_selector(
                '[data-message-author="model"], [class*="model"], [class*="response"], article',
                timeout=timeout_ms,
            )
            page.wait_for_timeout(3_000)

            # 응답 텍스트 수집 (가능한 선택자 여러 개 시도)
            response_text = ""
            for sel in [
                '[data-message-author="model"]',
                '[class*="markdown"]',
                'article',
                '[class*="response"] div',
            ]:
                els = page.query_selector_all(sel)
                if els:
                    for el in reversed(els):
                        t = el.inner_text().strip()
                        if len(t) > len(response_text) and len(t) > 50:
                            response_text = t
                            break
                if response_text:
                    break

            if not response_text:
                response_text = page.evaluate(
                    """() => {
                    const sel = document.querySelector('[data-message-author="model"]') || document.querySelector('article');
                    return sel ? sel.innerText : document.body.innerText;
                }"""
                )

            response_path.write_text(response_text.strip(), encoding="utf-8")
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
    browser_channel: Optional[str] = None,
    user_data_dir: Optional[Path] = None,
) -> None:
    """Playwright로 ChatGPT 웹에서 프롬프트 전송 후 응답 텍스트를 response_path에 저장."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    combined = _combined_prompt(system_prompt, user_message)
    url = "https://chat.openai.com/"

    with sync_playwright() as p:
        browser = None
        if user_data_dir is not None:
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=headless,
                channel=browser_channel,
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        else:
            browser = p.chromium.launch(headless=headless, channel=browser_channel)
            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                locale="ko-KR",
            )
        page = context.new_page()
        page.set_default_timeout(min(timeout_ms, 60_000))

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except PlaywrightTimeoutError:
                pass

            if login_signal_path is not None:
                _wait_for_login_signal(login_signal_path, timeout_sec=timeout_ms // 1000)

            # ChatGPT 입력란
            input_selector = 'textarea[placeholder*="Message"], textarea[placeholder*="메시지"], #prompt-textarea, [contenteditable="true"]'
            input_el = page.wait_for_selector(input_selector, timeout=15_000)
            input_el.click()
            input_el.fill("")
            page.keyboard.type(combined, delay=10)

            # 전송 버튼
            send_btn = page.wait_for_selector(
                'button[data-testid="send-button"], button[aria-label*="Send"], button:has(svg[data-icon="send"])',
                timeout=5_000,
            )
            send_btn.click()

            # 응답 대기
            page.wait_for_selector(
                '[data-testid="conversation-turn"], [class*="result"], [class*="response"]',
                timeout=timeout_ms,
            )
            page.wait_for_timeout(3_000)

            response_text = ""
            for sel in [
                '[data-testid="conversation-turn"]:last-of-type',
                '[class*="markdown"]',
                '[class*="result"]',
            ]:
                el = page.query_selector(sel)
                if el:
                    t = el.inner_text().strip()
                    if len(t) > len(response_text) and len(t) > 50:
                        response_text = t
                if response_text:
                    break

            if not response_text:
                response_text = page.evaluate(
                    """() => {
                    const turns = document.querySelectorAll('[data-testid="conversation-turn"]');
                    const last = turns[turns.length - 1];
                    return last ? last.innerText : document.body.innerText;
                }"""
                )

            response_path.write_text(response_text.strip(), encoding="utf-8")
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
    browser_channel: Optional[str] = None,
    user_data_dir: Optional[Path] = None,
) -> Path:
    """
    현재 단계 request 파일을 읽어 Gemini 또는 ChatGPT 웹에 전송하고, 응답을 response 파일에 저장.

    Args:
        run_dir: 수동 모드 run 폴더 (manual_req_res/run_YYYYMMDD_HHMMSS)
        step: 단계 번호 (1~9)
        site: "gemini" | "chatgpt"
        headless: True면 브라우저 창 숨김
        timeout_sec: 응답 대기 최대 초
        wait_for_login: True면 사이트 열린 뒤 로그인 완료 신호(.manual_step_login_done) 대기 후 전송

    Returns:
        저장된 response 파일 경로
    """
    from .manual_orchestrator import _step_request_file_name, _step_response_file_name

    run_dir = Path(run_dir)
    request_path = run_dir / _step_request_file_name(step)
    response_path = run_dir / _step_response_file_name(step)

    if not request_path.exists():
        raise FileNotFoundError(f"요청 파일이 없습니다: {request_path}")

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
            browser_channel=browser_channel,
            user_data_dir=user_data_dir,
        )
    elif site_lower == "chatgpt":
        _run_chatgpt_flow(
            system_prompt,
            user_message,
            response_path,
            headless=headless,
            timeout_ms=timeout_ms,
            login_signal_path=login_signal_path,
            browser_channel=browser_channel,
            user_data_dir=user_data_dir,
        )
    else:
        raise ValueError(f"지원하지 않는 사이트입니다: {site}. gemini 또는 chatgpt 를 지정하세요.")

    return response_path
