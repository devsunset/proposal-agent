"""
문서 파싱 모듈 — 확장자별 파서 선택 통합

PDF, DOCX, TXT, PPTX 확장자에 따라 적절한 파서 인스턴스를 반환하는
get_parser_for_path()를 제공합니다. main/ProposalOrchestrator에서는 이 함수만 사용하면
파서 추가·변경 시 한 곳만 수정하면 됩니다.
"""

from pathlib import Path
from typing import Union

from .pdf_parser import PDFParser
from .docx_parser import DOCXParser
from .txt_parser import TXTParser
from .pptx_parser import PPTXParser

__all__ = [
    "PDFParser",
    "DOCXParser",
    "TXTParser",
    "PPTXParser",
    "get_parser_for_path",
]


def get_parser_for_path(path: Union[Path, str]) -> Union[PDFParser, DOCXParser, TXTParser, PPTXParser]:
    """
    파일 경로 확장자에 맞는 파서 인스턴스 반환.

    Args:
        path: RFP 문서 파일 경로 (Path 또는 str)

    Returns:
        PDFParser | DOCXParser | TXTParser | PPTXParser

    Raises:
        ValueError: 지원하지 않는 확장자일 때
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return PDFParser()
    if suffix in (".docx", ".doc"):
        return DOCXParser()
    if suffix == ".txt":
        return TXTParser()
    if suffix == ".pptx":
        return PPTXParser()
    raise ValueError(
        f"지원하지 않는 형식: {suffix}. 지원: .pdf, .docx, .doc, .txt, .pptx"
    )
