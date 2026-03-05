@echo off
setlocal
REM 스크립트 기준 프로젝트 루트로 이동 (.env.mcp 위치)
cd /d "%~dp0.."

if not exist ".env.mcp" (
    echo 오류: .env.mcp 파일이 없습니다.
    exit /b 1
)

REM # 으로 시작하는 줄 제외, KEY=VALUE 형태 (값에 = 포함 가능)
for /f "eol=# tokens=1,* delims==" %%a in (.env.mcp) do (
    set "%%a=%%b"
)

echo MCP 환경변수 로딩 완료
cursor .
endlocal
