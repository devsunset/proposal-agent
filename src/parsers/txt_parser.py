"""
TXT 문서 파서

UTF-8 우선, 실패 시 CP949/CP1252 등으로 텍스트를 읽고, 번호/장 패턴으로 섹션을 구성합니다.
테이블은 지원하지 않으며 빈 목록을 반환합니다.
"""

from pathlib import Path
from typing import Any, Dict, List

from .base_parser import BaseParser
from ..utils.logger import get_logger

logger = get_logger("txt_parser")


class TXTParser(BaseParser):
    """
    TXT(플레인 텍스트) 문서 전용 파서.

    지원 확장자: .txt
    인코딩: utf-8, utf-8-sig, cp949, euc-kr, cp1252 순으로 시도.
    """

    @property
    def supported_extensions(self) -> List[str]:
        return [".txt"]

    def parse(self, file_path: Path) -> Dict[str, Any]:
        """
        TXT를 파싱하여 raw_text, tables(빈 목록), sections, metadata 반환.

        Args:
            file_path: TXT 파일 경로

        Returns:
            RFP 분석용 동일 포맷 딕셔너리
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
        """여러 인코딩을 순서대로 시도해 전체 텍스트 추출. 실패 시 UTF-8 + errors=replace."""
        encodings = ["utf-8", "utf-8-sig", "cp949", "euc-kr", "cp1252"]
        for enc in encodings:
            try:
                return file_path.read_text(encoding=enc)
            except (UnicodeDecodeError, LookupError):
                continue
        logger.warning("텍스트 인코딩 추측 실패, UTF-8로 시도 후 치환")
        return file_path.read_text(encoding="utf-8", errors="replace")

    def extract_tables(self, file_path: Path) -> List[Dict[str, Any]]:
        """TXT에는 테이블 구조가 없으므로 항상 빈 목록 반환."""
        return []

    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        """'제1장', '1.', '가.', '1)' 등 패턴으로 섹션 헤더를 찾아 title/content/level로 묶음."""
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
