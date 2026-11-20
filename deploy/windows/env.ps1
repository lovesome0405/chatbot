# .env(KEY=VALUE, '#'로 시작하는 줄은 주석)를 현재 PowerShell 프로세스 환경변수로 읽는다. **Windows 미검증.**
# 사용: . (Join-Path $app 'deploy\windows\env.ps1') $app   — 엔진은 .env 를 스스로 읽지 않으므로 실행 전에 꼭 부른다.
param([string]$App)
$envFile = Join-Path $App '.env'
if (-not (Test-Path $envFile)) { throw "없음: $envFile" }
foreach ($line in Get-Content -Encoding UTF8 $envFile) {
    $t = $line.Trim()
    if (-not $t -or $t.StartsWith('#') -or -not $t.Contains('=')) { continue }
    $i = $t.IndexOf('=')
    $k = $t.Substring(0, $i).Trim(); $v = $t.Substring($i + 1).Trim().Trim('"')
    Set-Item -Path "Env:$k" -Value $v
}
