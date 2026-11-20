# 엔진 API 실행(작업 스케줄러가 호출). **Windows 미검증.**
param([string]$Root = 'D:\lolypoly\rag')
$ErrorActionPreference = 'Stop'
$app = Join-Path $Root 'chatbot'
Set-Location $app
. (Join-Path $app 'deploy\windows\env.ps1') $app
[Console]::OutputEncoding = [Text.Encoding]::UTF8; $env:PYTHONUTF8 = '1'; $env:TZ = 'Asia/Seoul'
$env:PYTHONPATH = "$app\src;$app"
$log = Join-Path $Root 'logs\api.log'
if ((Test-Path $log) -and (Get-Item $log).Length -gt 5MB) { Move-Item $log "$log.old" -Force }
& (Join-Path $Root 'env\python.exe') -m uvicorn ragcore.api:app --host 127.0.0.1 --port 8088 2>&1 |
    Out-String -Stream | Add-Content -Encoding UTF8 $log
