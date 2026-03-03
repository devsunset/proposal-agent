"""
PDF 문서 파서

pypdf로 텍스트·메타데이터·페이지 수를 추출하고, pdfplumber로 테이블을 추출합니다.
RFP가 PDF로 제공될 때 사용됩니다.
"""

from pathlib import Path
from typing import Any, Dict, List

import pypdf
import pdfplumber

from .base_parser import BaseParser
from ..utils.logger import get_logger

logger = get_logger("pdf_parser")


class PDFParser(BaseParser):
    """
    PDF 문서 전용 파서.

    지원 확장자: .pdf
    텍스트: pypdf, 테이블: pdfplumber
    """

    @property
    def supported_extensions(self) -> List[str]:
        return [".pdf"]

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """
        PDF를 파싱하여 raw_text, tables, page_count, metadata, sections 반환.

        Args:
            file_path: PDF 파일 경로

        Returns:
            BaseParser 규격 + page_count, 섹션(휴리스틱 기반)
        """
        logger.info(f"PDF 파싱 시작: {file_path}")

        result = {
            "raw_text": self.extract_text(file_path),
            "tables": self.extract_tables(file_path),
            "page_count": self._get_page_count(file_path),
            "metadata": self._extract_metadata(file_path),
            "sections": self._extract_sections(file_path),
        }

        logger.info(
            f"PDF 파싱 완료: {len(result['raw_text'])} 문자, "
            f"{len(result['tables'])} 테이블"
        )

        return result

    def extract_text(self, file_path: Path) -> str:
        """pypdf로 페이지별 텍스트 추출. 페이지 구분은 '--- 페이지 N ---' 형식으로 삽입."""
        try:
            reader = pypdf.PdfReader(file_path)
            text_parts = []

            for i, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- 페이지 {i + 1} ---\n{page_text}")

            return "\n\n".join(text_parts)
        except Exception as e:
            logger.error("PDF 텍스트 추출 실패: %s: %s", type(e).__name__, str(e)[:200])
            raise

    def extract_tables(self, file_path: Path) -> List[Dict[str, Any]]:
        """pdfplumber로 페이지별 테이블 추출. 각 테이블은 page, headers, rows 포함."""
        tables = []

        try:
            with pdfplumber.open(file_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    page_tables = page.extract_tables()

                    for j, table in enumerate(page_tables):
                        if table and len(table) > 1:
                            # 첫 번째 행을 헤더로 처리
                            headers = [
                                str(cell).strip() if cell else ""
                                for cell in table[0]
                            ]
                            rows = [
                                [str(cell).strip() if cell else "" for cell in row]
                                for row in table[1:]
                            ]

                            tables.append(
                                {
                                    "page": i + 1,
                                    "table_index": j,
                                    "headers": headers,
                                    "rows": rows,
                                    "raw_data": table,
                                }
                            )
        except Exception as e:
            logger.error(f"테이블 추출 실패: {e}")

        return tables

    def _get_page_count(self, file_path: Path) -> int:
        """페이지 수 반환"""
        try:
            reader = pypdf.PdfReader(file_path)
            return len(reader.pages)
        except Exception:
            return 0

    def _extract_metadata(self, file_path: Path) -> Dict[str, Any]:
        """메타데이터 추출"""
        try:
            reader = pypdf.PdfReader(file_path)
            if reader.metadata:
                return {
                    "title": reader.metadata.get("/Title", ""),
                    "author": reader.metadata.get("/Author", ""),
                    "subject": reader.metadata.get("/Subject", ""),
                    "creator": reader.metadata.get("/Creator", ""),
                    "creation_date": str(reader.metadata.get("/CreationDate", "")),
                }
        except Exception as e:
            logger.warning(f"메타데이터 추출 실패: {e}")

        return {}

    def _extract_sections(self, file_path: Path) -> List[Dict[str, Any]]:
        """텍스트에서 '제1장', '1.', '가.' 등 패턴으로 섹션 헤더를 찾아 섹션 목록 구성."""
        sections = []
        text = self.extract_text(file_path)

        if not text:
            return sections

        lines = text.split("\n")
        current_section = {"title": "시작", "content": [], "level": 0}

        section_patterns = [
            "제1장",
            "제2장",
            "제3장",
            "제4장",
            "제5장",
            "1.",
            "2.",
            "3.",
            "4.",
            "5.",
            "I.",
            "II.",
            "III.",
            "IV.",
            "V.",
            "가.",
            "나.",
            "다.",
            "라.",
            "1)",
            "2)",
            "3)",
        ]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            is_section_header = False
            for pattern in section_patterns:
                if line.startswith(pattern) and len(line) < 100:
                    is_section_header = True
                    break

            if is_section_header:
                if current_section["content"]:
                    sections.append(current_section)
                current_section = {"title": line, "content": [], "level": 1}
            else:
                current_section["content"].append(line)

        if current_section["content"]:
            sections.append(current_section)

        return sections
