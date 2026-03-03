"""TXT 문서 파서"""

from pathlib import Path
from typing import Any, Dict, List

from .base_parser import BaseParser
from ..utils.logger import get_logger

logger = get_logger("txt_parser")


class TXTParser(BaseParser):
    """TXT 문서 파서 (UTF-8 등 텍스트 파일)"""

    @property
    def supported_extensions(self) -> List[str]:
        return [".txt"]

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """
        TXT를 파싱하여 구조화된 데이터 반환 (RFP 분석용 동일 포맷)

        Args:
            file_path: TXT 파일 경로

        Returns:
            파싱된 데이터 딕셔너리 (raw_text, tables, sections, metadata)
        """
        logger.info(f"TXT 파싱 시작: {file_path}")

        raw_text = self.extract_text(file_path)
        tables = self.extract_tables(file_path)
        sections = self._extract_sections(raw_text)

        result = {
            "raw_text": raw_text,
            "tables": tables,
            "sections": sections,
            "metadata": {"source": "txt", "path": str(file_path)},
        }

        logger.info(f"TXT 파싱 완료: {len(raw_text)} 문자")

        return result

    def extract_text(self, file_path: Path) -> str:
        """전체 텍스트 추출 (UTF-8 우선, fallback CP949/CP1252)"""
        encodings = ["utf-8", "utf-8-sig", "cp949", "euc-kr", "cp1252"]
        for enc in encodings:
            try:
                return file_path.read_text(encoding=enc)
            except (UnicodeDecodeError, LookupError):
                continue
        logger.warning("텍스트 인코딩 추측 실패, UTF-8로 시도 후 치환")
        return file_path.read_text(encoding="utf-8", errors="replace")

    def extract_tables(self, file_path: Path) -> List[Dict[str, Any]]:
        """TXT에는 테이블 구조가 없으므로 빈 목록 반환"""
        return []

    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        """줄 단위로 구분하여 섹션처럼 묶기 (휴리스틱)"""
        sections = []
        if not text.strip():
            return sections
        lines = text.splitlines()
        current = {"title": "", "content": [], "level": 0}
        for line in lines:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            # 번호/장 패턴으로 섹션 헤더 추정
            if any(line_stripped.startswith(p) for p in ("제1장", "제2장", "1.", "2.", "가.", "나.", "1)", "2)")):
                if current["content"] or current["title"]:
                    sections.append(current)
                current = {"title": line_stripped, "content": [], "level": 1}
            else:
                current["content"].append(line_stripped)
        if current["content"] or current["title"]:
            sections.append(current)
        return sections
