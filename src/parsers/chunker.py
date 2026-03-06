"""
RFP 청킹 모듈 (RFP Chunker)

장문 RFP를 의미 단위로 분할하여 LLM 컨텍스트 한계를 극복합니다.
평가 기준·요구사항 등 고우선순위 섹션을 우선 포함해 RFP의 핵심 내용이
분석에서 누락되지 않도록 합니다.

현재 문제: rfp_analyzer.py가 raw_text를 25,000자로 절단
→ 실제 공공 RFP(50~200페이지)의 후반부 평가 기준, 세부 과업이 누락됨

개선 목표: max_chars=40,000자로 확대 + 중요 섹션 우선 포함
"""

import json
import re
from typing import Dict, List, Optional


# 우선순위가 높은 키워드 (평가·요구사항·기술·산출물·선정 등 — RFP 핵심 전부 포함)
PRIORITY_HIGH_KEYWORDS = [
    "평가 기준", "평가기준", "평가 항목", "평가항목", "배점", "점수", "심사",
    "요구사항", "요구 사항", "요구기술", "기술 요구", "기능 요구", "비기능 요구",
    "과업 범위", "과업내용", "과업 내용", "수행 내용", "업무 내용", "세부 과업",
    "산출물", "납품물", "선정 기준", "심사 기준", "제안 요청", "제안요청",
    "계약 조건", "계약조건", "제안서 작성", "제안서 작성",
]

PRIORITY_MEDIUM_KEYWORDS = [
    "일정", "기간", "추진 일정", "수행 기간", "예산", "금액", "사업비", "예산편성",
    "제출", "자격", "입찰", "참가자격", "수행 능력", "실적", "경력",
]

# 섹션 헤딩 패턴 (한국 공공 문서 형식)
_HEADING_PATTERNS = [
    # 제1장, 제2장 ...
    re.compile(r"^(제\s*\d+\s*장[^\n]{0,50})$", re.MULTILINE),
    # 1. 2. 3. (숫자 + 점)
    re.compile(r"^(\d{1,2}\.\s{1,3}[가-힣A-Za-z][^\n]{2,60})$", re.MULTILINE),
    # 가. 나. 다. ...
    re.compile(r"^([가나다라마바사아자차카타파하]\.\s{1,3}[^\n]{2,50})$", re.MULTILINE),
    # I. II. III. ...
    re.compile(r"^((?:I{1,3}|IV|V|VI{0,3}|IX|X)\.\s{1,3}[^\n]{2,50})$", re.MULTILINE),
    # ■ □ ▶ ● 기호로 시작하는 헤딩
    re.compile(r"^([■□▶●◆★☆]\s{1,3}[^\n]{2,50})$", re.MULTILINE),
]


class RFPChunker:
    """
    장문 RFP를 의미 단위로 분할하고 우선순위를 부여합니다.

    전략:
    1. Section-aware Chunking: 헤딩 기반으로 섹션 분할
    2. Priority Scoring: 평가 기준·요구사항 등 핵심 섹션에 높은 우선순위
    3. Budget-aware Selection: max_chars 이내에서 고우선순위 섹션 우선 선택
    """

    def chunk(self, raw_text: str) -> List[Dict]:
        """
        RFP 텍스트를 섹션 단위로 분할하고 우선순위 부여.

        Returns:
            [{"section": "헤딩", "text": "섹션 본문", "priority": "high|medium|low", "char_count": int}]
        """
        if not raw_text:
            return []

        sections = self._split_by_headings(raw_text)
        return self._score_sections(sections)

    def build_analysis_context(
        self,
        raw_text: str,
        tables: Optional[List] = None,
        max_chars: int = 40000,
    ) -> str:
        """
        LLM 분석에 전달할 최적 컨텍스트 구성.

        우선순위:
        1. high 섹션: 전문 포함
        2. medium 섹션: 첫 2,000자만
        3. low 섹션: 첫 500자만 (예산 내 남은 공간에 한해)
        4. 테이블: 중요 섹션 뒤에 압축해서 포함

        Args:
            raw_text: RFP 원문
            tables: 테이블 데이터 리스트 (선택)
            max_chars: 최대 컨텍스트 문자 수 (기본 40,000)

        Returns:
            LLM에 전달할 컨텍스트 문자열
        """
        chunks = self.chunk(raw_text)
        if not chunks:
            return raw_text[:max_chars]

        parts: List[str] = []
        used_chars = 0

        # 1단계: high 우선순위 섹션 전문 포함
        for chunk in chunks:
            if chunk["priority"] != "high":
                continue
            text = chunk["text"]
            if used_chars + len(text) <= max_chars:
                header = f"\n\n### {chunk['section']}\n" if chunk["section"] else "\n\n"
                parts.append(header + text)
                used_chars += len(header) + len(text)

        # 2단계: medium 우선순위 섹션 (앞 3,000자)
        for chunk in chunks:
            if chunk["priority"] != "medium":
                continue
            text = chunk["text"][:3000]
            if used_chars + len(text) + 100 > max_chars:
                break
            header = f"\n\n### {chunk['section']}\n" if chunk["section"] else "\n\n"
            parts.append(header + text)
            used_chars += len(header) + len(text)

        # 3단계: low 우선순위 섹션 (앞 800자, 공간 있을 때만)
        for chunk in chunks:
            if chunk["priority"] != "low":
                continue
            text = chunk["text"][:800]
            if used_chars + len(text) + 100 > max_chars:
                break
            header = f"\n\n### {chunk['section']}\n" if chunk["section"] else "\n\n"
            parts.append(header + text)
            used_chars += len(header) + len(text)

        # 4단계: 테이블 (남은 공간에, 최대 15개·개당 1000자까지 — raw_text에 이미 포함되어 있으면 보조)
        if tables and used_chars < max_chars - 500:
            tables_text = "\n\n## 테이블 데이터(구조화)\n"
            for t in tables[:15]:
                try:
                    t_str = json.dumps(t, ensure_ascii=False)[:1000]
                    if used_chars + len(t_str) + 100 > max_chars:
                        break
                    tables_text += t_str + "\n"
                    used_chars += len(t_str)
                except Exception:
                    pass
            parts.append(tables_text)

        result = "".join(parts).strip()

        # 청킹 결과가 너무 짧으면 단순 절단으로 폴백
        if len(result) < 1000:
            return raw_text[:max_chars]

        return result

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _split_by_headings(self, text: str) -> List[Dict]:
        """헤딩 패턴으로 텍스트를 섹션 단위 분할."""
        # 모든 헤딩 위치 수집
        heading_positions: List[tuple] = []  # (start, end, heading_text)
        for pattern in _HEADING_PATTERNS:
            for m in pattern.finditer(text):
                heading_positions.append((m.start(), m.end(), m.group(1).strip()))

        if not heading_positions:
            # 헤딩을 못 찾으면 4,000자 단위 고정 분할
            return self._fixed_chunk(text, chunk_size=4000)

        # 위치순 정렬 + 중복 제거 (가장 이른 패턴 우선)
        heading_positions.sort(key=lambda x: x[0])
        deduped: List[tuple] = []
        last_end = -1
        for start, end, heading in heading_positions:
            if start >= last_end:
                deduped.append((start, end, heading))
                last_end = end

        # 섹션 본문 분리
        sections: List[Dict] = []
        for i, (start, end, heading) in enumerate(deduped):
            body_start = end
            body_end = deduped[i + 1][0] if i + 1 < len(deduped) else len(text)
            body = text[body_start:body_end].strip()
            if body:
                sections.append({
                    "section": heading,
                    "text": body,
                    "priority": "low",
                    "char_count": len(body),
                })

        # 첫 헤딩 이전 텍스트 (서문 등)
        if deduped and deduped[0][0] > 0:
            preamble = text[: deduped[0][0]].strip()
            if preamble:
                sections.insert(0, {
                    "section": "서문",
                    "text": preamble,
                    "priority": "low",
                    "char_count": len(preamble),
                })

        return sections

    def _fixed_chunk(self, text: str, chunk_size: int = 4000) -> List[Dict]:
        """헤딩 없을 때 고정 크기 분할."""
        sections = []
        for i in range(0, len(text), chunk_size):
            chunk_text = text[i: i + chunk_size]
            sections.append({
                "section": f"섹션 {i // chunk_size + 1}",
                "text": chunk_text,
                "priority": "low",
                "char_count": len(chunk_text),
            })
        return sections

    def _score_sections(self, sections: List[Dict]) -> List[Dict]:
        """섹션 우선순위 계산."""
        for section in sections:
            combined = (section["section"] + " " + section["text"]).lower()
            high = any(kw in combined for kw in PRIORITY_HIGH_KEYWORDS)
            medium = any(kw in combined for kw in PRIORITY_MEDIUM_KEYWORDS)
            if high:
                section["priority"] = "high"
            elif medium:
                section["priority"] = "medium"
            else:
                section["priority"] = "low"
        return sections
