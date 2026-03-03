"""TXT 파서 단위 테스트 (고정 샘플로 parse 결과 검증)"""

import pytest
from pathlib import Path

from src.parsers.txt_parser import TXTParser


def test_txt_parser_parse_returns_expected_keys(tmp_path):
    """parse() 결과에 raw_text, tables, sections, metadata 키 존재"""
    f = tmp_path / "sample.txt"
    f.write_text("프로젝트 개요\n테스트 내용", encoding="utf-8")
    parser = TXTParser()
    result = parser.parse(f)
    assert "raw_text" in result
    assert "tables" in result
    assert "sections" in result
    assert "metadata" in result
    assert "프로젝트" in result["raw_text"] or "테스트" in result["raw_text"]


def test_txt_parser_extract_text_utf8(tmp_path):
    """UTF-8 텍스트 추출"""
    f = tmp_path / "utf8.txt"
    content = "제안서 RFP 분석"
    f.write_text(content, encoding="utf-8")
    parser = TXTParser()
    assert parser.extract_text(f) == content
