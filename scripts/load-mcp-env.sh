#!/bin/bash
# 프로젝트 루트 기준 .env.mcp 로드 (스크립트 위치와 무관하게 동작)
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env.mcp"

if [ ! -f "$ENV_FILE" ]; then
    echo "오류: .env.mcp 파일이 없습니다. (찾은 경로: $ENV_FILE)"
    exit 1
fi

# 한 줄씩 읽어서 export (주석/빈 줄 제외, 값에 = 포함 가능)
while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue
    name="${line%%=*}"
    value="${line#*=}"
    name="${name#"${name%%[![:space:]]*}"}"
    name="${name%"${name##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    export "$name=$value"
done < "$ENV_FILE"

echo "MCP 환경변수 로딩 완료 (프로젝트 루트: $PROJECT_ROOT)"
cd "$PROJECT_ROOT"
cursor .
