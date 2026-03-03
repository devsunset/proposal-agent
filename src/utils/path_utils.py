"""
출력 경로·파일명 보안 유틸

파일명에 허용 문자만 남기고 길이를 제한하며, 출력 경로가 지정 디렉터리 이하에만
생성되도록 경로 이탈을 방지합니다.
"""

import re
from pathlib import Path
from typing import Optional

SAFE_FILENAME_MAX_LEN = 100


def safe_filename(name: str, max_len: int = SAFE_FILENAME_MAX_LEN) -> str:
    """
    파일명으로 사용 가능한 안전한 문자열로 정규화.

    허용: 영숫자, 공백, 하이픈, 언더스코어, 마침표. 공백→언더스코어, 슬래시→하이픈 치환 후
    max_len으로 자릅니다. 비어 있으면 "output" 반환.

    Args:
        name: 원본 이름 (예: 프로젝트명)
        max_len: 최대 길이 (기본 100)

    Returns:
        안전한 파일명 문자열
    """
    if not name or not isinstance(name, str):
        return "output"
    s = name.replace(" ", "_").replace("/", "-")
    s = re.sub(r"[^\w\s\-.]", "", s)
    s = re.sub(r"\s+", "_", s).strip("._- ") or "output"
    return s[:max_len]


def safe_output_path(
    output_dir: Path,
    base_name: str,
    suffix: str = "",
    extension: str = "",
) -> Path:
    """
    output_dir 이하에만 위치하도록 안전한 출력 경로 생성.

    base_name에 safe_filename을 적용하고, resolve() 후 relative_to()로
    output_dir 이외로 나가는 경로는 사용하지 않도록 보정합니다.

    Args:
        output_dir: 출력 디렉터리
        base_name: 파일명 베이스 (자동으로 safe_filename 적용)
        suffix: 접미사 (예: _content, _20240301)
        extension: 확장자 (예: .pptx, .json)

    Returns:
        output_dir 내의 절대 Path
    """
    output_dir = Path(output_dir).resolve()
    safe_base = safe_filename(base_name)
    name = f"{safe_base}{suffix}{extension}"
    candidate = (output_dir / name).resolve()
    try:
        candidate.relative_to(output_dir)
    except ValueError:
        # 경로 이탈 시 output_dir 기준 이름만 사용
        candidate = output_dir / safe_filename(name)
        candidate = candidate.resolve()
    return candidate
