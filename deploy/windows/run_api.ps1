# 엔진 API 실행(작업 스케줄러가 호출). 2026-11-20 학교 PC(Windows 11, PowerShell 5.1)에서 확인.
param([string]$Root = 'D:\lolypoly\rag')
$ErrorActionPreference = 'Stop'
$app = Join-Path $Root 'chatbot'
Set-Location $app
. (Join-Path $app 'deploy\windows\env.ps1') $app
. (Join-Path $app 'deploy\windows\logutil.ps1')
[Console]::OutputEncoding = [Text.Encoding]::UTF8; $env:PYTHONUTF8 = '1'; $env:TZ = 'Asia/Seoul'
$env:PYTHONPATH = "$app\src;$app"
$log = Join-Path $Root 'logs\api.log'
if ((Test-Path $log) -and (Get-Item $log).Length -gt 5MB) { Move-Item $log "$log.old" -Force }
# Windows PowerShell 5.1: 'Stop' 상태에서 2>&1 로 받으면 uvicorn 이 stderr 에 쓰는 첫 줄("INFO: Started server process")이
# NativeCommandError 로 바뀌어 스크립트가 곧바로 멈춘다(2026-11-20 학교 PC에서 재현). 여기부터는 'Continue' 로 둔다.
$ErrorActionPreference = 'Continue'
# 실시간 모델을 미리 적재해 둔다(warm_model.ps1 주석 참고). 실패해도 API 는 띄운다(그동안 질문은 원문 발췌로 답함)
& (Join-Path $app 'deploy\windows\warm_model.ps1') -Model $env:OLLAMA_MODEL 2>&1 | Out-Log $log
& (Join-Path $Root 'env\python.exe') -m uvicorn ragcore.api:app --host 127.0.0.1 --port 8088 2>&1 | Out-Log $log
exit $LASTEXITCODE
