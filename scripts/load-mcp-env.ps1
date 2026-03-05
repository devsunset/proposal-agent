# 프로젝트 루트 기준 .env.mcp 로드 (스크립트 위치와 무관하게 동작)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$EnvFile = Join-Path $ProjectRoot ".env.mcp"

if (!(Test-Path $EnvFile)) {
    Write-Host "오류: .env.mcp 파일이 없습니다. (찾은 경로: $EnvFile)"
    exit 1
}

# 한 줄씩 읽어서 환경변수 등록 (주석/빈 줄 제외, Process 스코프)
Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
    $line = $_.TrimEnd("`r")
    if ($line -match "^\s*#") { return }
    if ($line -match "^\s*$") { return }

    $parts = $line -split "=", 2
    $name = $parts[0].Trim()
    if ([string]::IsNullOrEmpty($name)) { return }

    $value = if ($parts.Length -gt 1) { $parts[1].Trim() } else { "" }
    # 값 앞뒤 따옴표 제거 (선택)
    if ($value.Length -ge 2 -and $value[0] -eq '"' -and $value[-1] -eq '"') {
        $value = $value.Substring(1, $value.Length - 2)
    }
    [System.Environment]::SetEnvironmentVariable($name, $value, "Process")
}

Write-Host "MCP 환경변수 로딩 완료 (프로젝트 루트: $ProjectRoot)"
Set-Location $ProjectRoot
cursor .
