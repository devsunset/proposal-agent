# Trim advance.md: remove implemented sections, keep unimplemented only.
# Run from repo root: python scripts/trim_advance.py

from pathlib import Path

path = Path(__file__).parent.parent / "advance.md"
lines = path.read_text(encoding="utf-8").splitlines()

# Ranges to REMOVE (1-based, inclusive). After first edit, line numbers shift.
# We do removals from end to start so indices don't shift.
remove_ranges = [
    (28, 221),   # ### 1.1 콘텐츠 빈약 ... through ### 2.1 (핵심 개선 포인트 끝)
    (402, 426),  # ### 3.4 네거티브 프롬프트 강화 (Negative Instructions)
    (427, 469),  # ### 3.5 프롬프트 버전 관리 시스템
    (570, 608),  # ### 4.3 Phase 간 컨텍스트 전달
    (611, 707),  # ### 5.1 산업 통계 데이터베이스
    (708, 787),  # ### 5.2 회사 프로필 자동 구조화 + CLI 명령 추가
    (878, 991),  # ### 6.1 슬라이드 품질 스코어링 엔진 (전체 코드 블록)
    (1254, 1323), # ### 7.3 폰트 의존성 해소
]

# Convert to 0-based and sort by start descending
to_remove = sorted([(s - 1, e - 1) for s, e in remove_ranges], key=lambda x: -x[0])

result = []
i = 0
while i < len(lines):
    skip = False
    for start, end in to_remove:
        if start <= i <= end:
            i = end + 1
            skip = True
            break
    if not skip:
        result.append(lines[i])
        i += 1

path.write_text("\n".join(result) + "\n", encoding="utf-8")
print("Removed implemented sections. Line count:", len(lines), "->", len(result))
