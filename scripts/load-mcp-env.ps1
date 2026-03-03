# .env.mcp 파일 존재 확인
if (!(Test-Path ".env.mcp")) {
    Write-Host ".env.mcp 파일이 없습니다."
    exit
}

# 한 줄씩 읽어서 환경변수 등록
Get-Content .env.mcp | ForEach-Object {
    if ($_ -match "^\s*#") { return }     # 주석 무시
    if ($_ -match "^\s*$") { return }     # 빈 줄 무시

    $name, $value = $_ -split "=", 2
    [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
}

Write-Host "MCP 환경변수 로딩 완료"

# Cursor 실행
cursor .

# 보안 설정
# Set-ExecutionPolicy -Scope CurrentUser RemoteSigned