"""
로깅 설정 모듈

loguru 기반 로거 설정. LOG_LEVEL 환경 변수(또는 config.settings)로 레벨 제어.
Rich Progress와 함께 사용할 때 stderr에 매 로그 앞 줄바꿈을 넣어 Progress 라인과 겹치지 않게 합니다.

중복 로그 방지: 기본 핸들러(id=0) 및 기존 핸들러를 모두 제거한 뒤, 앱 전용 핸들러 하나만 등록합니다.
setup_logger()는 앱 진입점(main.py)에서 한 번만 호출하는 것을 권장합니다.
"""

import os
import sys
from typing import Optional

from loguru import logger

# 단계별 로그 구분자 (main/오케스트레이터에서 동일 문자열 사용)
LOG_SEPARATOR = "----------------------------------------------"
STEP_SEPARATOR = "══════════════════════════════════════════════════════════"
PHASE_SEPARATOR = "  ──────────────────────────────────────────"

# 앱에서 등록한 핸들러 ID (중복 등록 방지용)
_app_handler_id: Optional[int] = None


def log_stage(stage_name: Optional[str] = None) -> None:
    """단계 구분선 및 단계명 로그 출력 (가독성용)."""
    _log = logger.bind(name="stage")
    _log.info(LOG_SEPARATOR)
    if stage_name:
        _log.info(f"  {stage_name}")
        _log.info(LOG_SEPARATOR)


def setup_logger(level: Optional[str] = None) -> None:
    """
    loguru 로거 설정. 기존 핸들러 전부 제거 후 stderr에 포맷·레벨 적용.
    이미 설정된 경우 기존 앱 핸들러만 제거하고 새로 하나 등록해, 항상 핸들러가 하나만 있도록 합니다.

    Args:
        level: DEBUG | INFO | WARNING | ERROR. None이면 config.settings.log_level 사용 (기본 INFO).
    """
    global _app_handler_id
    if level is None:
        from config.settings import get_settings
        level = get_settings().log_level

    # 1) loguru 기본 핸들러(id=0) 명시 제거 (남아 있으면 동일 로그가 두 번 출력됨)
    try:
        logger.remove(0)
    except ValueError:
        pass
    # 2) 이전에 등록한 앱 핸들러가 있으면 제거
    if _app_handler_id is not None:
        try:
            logger.remove(_app_handler_id)
        except (ValueError, TypeError):
            pass
        _app_handler_id = None
    # 3) 그 외 모든 핸들러 제거 (다른 모듈/테스트에서 추가했을 수 있음)
    logger.remove()

    fmt = "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
    # Rich Progress와 같은 터미널에 쓸 때, 로그가 Progress 라이브 라인(\\n 없음) 뒤에 붙지 않도록 매 로그 앞에 줄바꿈
    def _sink_newline_first(message):
        try:
            if sys.stderr.isatty():
                sys.stderr.write("\n")
        except Exception:
            pass
        sys.stderr.write(message)
        sys.stderr.flush()

    _app_handler_id = logger.add(
        _sink_newline_first,
        format=fmt,
        level=level,
        colorize=True,
    )


def get_logger(name: str = "proposal"):
    """
    name이 바인딩된 로거 인스턴스 반환 (모듈별 구분용).

    Args:
        name: 로거 이름 (예: "rfp_analyzer", "content_generator")

    Returns:
        loguru logger with name binding
    """
    return logger.bind(name=name)


# main.py 진입점에서만 setup_logger() 호출 (load_dotenv 이후 LOG_LEVEL 적용). 여기서는 호출하지 않음.
