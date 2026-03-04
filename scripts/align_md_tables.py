#!/usr/bin/env python3
"""
Markdown 파일 내 테이블의 셀 너비를 맞춰 오른쪽 끝이 정렬되도록 함.
연속된 | 로 시작하는 줄을 테이블로 인식하고, 열별 최대 너비로 패딩.
"""
import re
import sys
from pathlib import Path


def cell_len(s: str) -> int:
    """한글 등 전각 문자는 2, ASCII는 1로 계산 (선택). 여기서는 1로 통일."""
    return len(s)


def parse_table(lines: list[str]) -> tuple[list[list[str]], int]:
    """연속된 테이블 행 파싱. (rows, end_index) 반환."""
    rows = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped.startswith("|") or "|" not in stripped[1:]:
            break
        parts = stripped.split("|")
        # | a | b | -> parts[0]='', parts[1]=' a ', parts[2]=' b ', parts[3]='' -> cells = parts[1:-1]
        cells = [p.strip() for p in parts[1:-1]]
        if not cells:
            break
        rows.append(cells)
        i += 1
    return rows, i


def align_table(rows: list[list[str]]) -> list[str]:
    """행 리스트를 열 너비 맞춘 마크다운 테이블로 변환."""
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    # 열별 최대 너비
    widths = [0] * ncols
    for row in rows:
        for j, cell in enumerate(row):
            if j < ncols:
                widths[j] = max(widths[j], cell_len(cell))
    # 구분자 행: 두 번째 행이 --- 형태인지 확인
    out = []
    for i, row in enumerate(rows):
        padded = []
        for j in range(ncols):
            cell = row[j] if j < len(row) else ""
            w = widths[j]
            padded.append(cell + " " * (w - cell_len(cell)))
        if i == 1 and re.match(r"^[\s\-:]+$", "".join(padded).replace(" ", "")):
            # separator line: align column width
            sep = "|"
            for j in range(ncols):
                sep += " " + "-" * max(3, widths[j]) + " |"
            out.append(sep)
        else:
            out.append("| " + " | ".join(padded) + " |")
    return out


def process_file(path: Path) -> bool:
    """파일 내 모든 테이블 정렬. 변경 시 True."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = []
    i = 0
    changed = False
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and "|" in line:
            rows, consumed = parse_table(lines[i:])
            if len(rows) >= 2:
                aligned = align_table(rows)
                if aligned != [lines[i + k] for k in range(consumed)]:
                    changed = True
                new_lines.extend(aligned)
                i += consumed
                continue
        new_lines.append(line)
        i += 1
    if changed:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    return changed


def main():
    docs = Path(__file__).resolve().parent.parent / "docs"
    if not docs.exists():
        print("docs folder not found")
        sys.exit(1)
    md_files = list(docs.glob("**/*.md"))
    for path in sorted(md_files):
        if process_file(path):
            print(f"Updated: {path}")
    print("Done.")


if __name__ == "__main__":
    main()
