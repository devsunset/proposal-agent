"""출력 경로·파일명 보안 유틸 테스트"""

import pytest
from pathlib import Path

from src.utils.path_utils import safe_filename, safe_output_path


def test_safe_filename_basic():
    assert safe_filename("지능형제조혁신") == "지능형제조혁신"
    assert safe_filename("Project Name") == "Project_Name"
    assert safe_filename("a/b") == "a-b"


def test_safe_filename_strips_bad_chars():
    # 허용 문자만 남김 (영숫자, _, -, ., 공백→_)
    out = safe_filename("hello<>world")
    assert ">" not in out and "<" not in out


def test_safe_filename_max_len():
    long_name = "a" * 150
    assert len(safe_filename(long_name, max_len=100)) == 100


def test_safe_filename_empty():
    assert safe_filename("") == "output"
    assert safe_filename("   ") != ""


def test_safe_output_path_under_dir(tmp_path):
    out = safe_output_path(tmp_path, "프로젝트명", suffix="_제안서", extension=".pptx")
    assert out.suffix == ".pptx"
    assert out.parent == tmp_path.resolve()
    assert out.resolve().relative_to(tmp_path.resolve())


def test_safe_output_path_no_escape(tmp_path):
    # base_name에 .. 등 있어도 output_dir 이하로만 생성
    out = safe_output_path(tmp_path, "normal_name", suffix="", extension=".json")
    assert tmp_path.resolve() in out.resolve().parents or out.resolve() == tmp_path.resolve()
