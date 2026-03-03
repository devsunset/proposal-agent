"""출력 경로·파일명 보안 유틸 (경로 이탈·특수문자·길이 제한)"""

import re
from pathlib import Path
from typing import Optional

# 허용 문자만 남기고 최대 길이
SAFE_FILENAME_MAX_LEN = 100


def safe_filename(name: str, max_len: int = SAFE_FILENAME_MAX_LEN) -> str:
    """
    파일명으로 사용할 수 있도록 허용 문자만 남기고 길이 제한.

    - 허용: 영숫자, 공백, 하이픈, 언더스코어, 마침표
    - 공백은 언더스코어로, 슬래시는 하이픈으로 치환
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
    output_dir 이하에만 생성되도록 안전한 경로 생성.

    Args:
        output_dir: 출력 디렉터리
        base_name: 파일명 베이스 (safe_filename 적용됨)
        suffix: 파일명 접미사 (예: _content)
        extension: 확장자 (예: .pptx, .json)

    Returns:
        output_dir 내의 Path. 상대 경로 검증으로 경로 이탈 방지.
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
