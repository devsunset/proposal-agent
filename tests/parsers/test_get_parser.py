"""get_parser_for_path 확장자별 파서 반환 및 미지원 확장자 ValueError 검증"""

import pytest
from pathlib import Path

from src.parsers import get_parser_for_path
from src.parsers.pdf_parser import PDFParser
from src.parsers.docx_parser import DOCXParser
from src.parsers.txt_parser import TXTParser
from src.parsers.pptx_parser import PPTXParser


def test_get_parser_pdf():
    assert isinstance(get_parser_for_path(Path("a.pdf")), PDFParser)
    assert isinstance(get_parser_for_path("b.PDF"), PDFParser)


def test_get_parser_docx():
    assert isinstance(get_parser_for_path(Path("a.docx")), DOCXParser)
    assert isinstance(get_parser_for_path(Path("b.doc")), DOCXParser)


def test_get_parser_txt():
    assert isinstance(get_parser_for_path(Path("a.txt")), TXTParser)


def test_get_parser_pptx():
    assert isinstance(get_parser_for_path(Path("a.pptx")), PPTXParser)


def test_get_parser_unsupported_raises():
    with pytest.raises(ValueError) as exc_info:
        get_parser_for_path(Path("a.xyz"))
    assert "지원하지 않는 형식" in str(exc_info.value)
    assert ".pdf" in str(exc_info.value) or "pdf" in str(exc_info.value)
