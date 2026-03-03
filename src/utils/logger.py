"""로깅 설정"""

import os
import sys
from typing import Optional

from loguru import logger

# 단계별 로그 구분자 (main/오케스트레이터에서 동일 문자열 사용)
LOG_SEPARATOR = "----------------------------------------------"

# Step(대단계) 구분용 — 한눈에 Step 1/2 구분
STEP_SEPARATOR = "══════════════════════════════════════════════════════════"

# Phase(소단계) 구분용 — Step 내부 Phase 표시
PHASE_SEPARATOR = "  ──────────────────────────────────────────"


def log_stage(stage_name: Optional[str] = None) -> None:
    """단계 구분선 및 단계명 로그 (가독성용)"""
    _log = logger.bind(name="stage")
    _log.info(LOG_SEPARATOR)
    if stage_name:
        _log.info(f"  {stage_name}")
        _log.info(LOG_SEPARATOR)


def setup_logger(level: Optional[str] = None) -> None:
    """로거 설정. level이 없으면 config.settings(LOG_LEVEL) 사용 (기본 INFO)."""
    if level is None:
        from config.settings import get_settings
        level = get_settings().log_level
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
    logger.add(
        _sink_newline_first,
        format=fmt,
        level=level,
        colorize=True,
    )


def get_logger(name: str = "proposal"):
    """로거 인스턴스 반환"""
    return logger.bind(name=name)


# main.py 진입점에서만 setup_logger() 호출 (load_dotenv 이후 LOG_LEVEL 적용). 여기서는 호출하지 않음.
