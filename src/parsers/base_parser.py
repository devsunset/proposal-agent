"""
문서 파서 추상 클래스

PDF/DOCX/TXT/PPTX 등 다양한 RFP 문서 형식을 공통 인터페이스로 파싱하기 위한
추상 베이스 클래스. parse()는 raw_text, tables, sections, metadata를 반환합니다.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List


class BaseParser(ABC):
    """
    문서 파서 추상 클래스.

    서브클래스는 supported_extensions, parse(), extract_text(), extract_tables()를 구현해야 합니다.
    """

    @abstractmethod
    def parse(self, file_path: Path) -> Dict[str, Any]:
        """
        문서를 파싱하여 RFP 분석·콘텐츠 생성에서 사용하는 구조화 데이터 반환.

        Args:
            file_path: 파싱할 파일 경로

        Returns:
            raw_text: 전체 추출 텍스트
            tables: 테이블 목록 (각 항목: headers, rows 등)
            sections: 헤딩 기반 섹션 목록
            metadata: 제목, 작성자 등
        """
        pass

    @abstractmethod
    def extract_text(self, file_path: Path) -> str:
        """파일에서 전체 텍스트만 추출. 파서별로 구현."""
        pass

    @abstractmethod
    def extract_tables(self, file_path: Path) -> List[Dict[str, Any]]:
        """파일에서 테이블 구조만 추출. 파서별로 구현."""
        pass

    def is_supported(self, file_path: Path) -> bool:
        """해당 파일 확장자가 이 파서에서 지원되는지 여부."""
        return file_path.suffix.lower() in self.supported_extensions

    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """지원하는 파일 확장자 목록 (예: ['.pdf'], ['.docx', '.doc'])."""
        pass
