"""TemplateManager 단위 테스트 (load_template, get_layout_index)"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.generators.template_manager import TemplateManager


@pytest.fixture
def mock_settings(tmp_path):
    """templates_dir을 tmp_path로 설정"""
    with patch("src.generators.template_manager.get_settings") as m:
        s = MagicMock()
        s.templates_dir = tmp_path
        m.return_value = s
        yield s


def test_load_template_creates_blank_when_no_file(mock_settings):
    """템플릿 파일이 없으면 빈 프레젠테이션 반환"""
    mgr = TemplateManager(mock_settings.templates_dir)
    prs = mgr.load_template("nonexistent")
    assert prs is not None
    assert len(prs.slides) == 0


def test_get_layout_index_returns_default():
    """get_layout_index: 레이아웃 이름에 따른 인덱스 (기본 1)"""
    with patch("src.generators.template_manager.get_settings") as m:
        m.return_value.templates_dir = Path("/tmp")
    mgr = TemplateManager(Path("/tmp"))
    assert mgr.get_layout_index("content") in (0, 1, 2, 3, 4, 5, 6)
    assert mgr.get_layout_index("unknown_name") == 1  # default
