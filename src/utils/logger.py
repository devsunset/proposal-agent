"""로깅 설정"""

import os
import sys
from typing import Optional

from loguru import logger

# 단계별 로그 구분자 (main/오케스트레이터에서 동일 문자열 사용)
LOG_SEPARATOR = "----------------------------------------------"


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
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=level,
        colorize=True,
    )


def get_logger(name: str = "proposal"):
    """로거 인스턴스 반환"""
    return logger.bind(name=name)


# main.py 진입점에서만 setup_logger() 호출 (load_dotenv 이후 LOG_LEVEL 적용). 여기서는 호출하지 않음.
