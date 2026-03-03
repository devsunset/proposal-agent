@echo off

for /f "tokens=1,2 delims==" %%a in (.env.mcp) do (
    set %%a=%%b
)

echo MCP 환경변수 로딩 완료
cursor .