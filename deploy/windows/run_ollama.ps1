# Ollama 서버 실행(작업 스케줄러 RAG-Ollama 가 부팅 시 호출). 2026-11-20 학교 PC에서 추가·확인.
# 왜 필요한가: Ollama 설치 프로그램은 '사용자 로그인 때' 트레이 앱으로만 서버를 띄운다. 로그인 없이 부팅만 된 상태(S4U 작업)에서도
# 엔진이 답을 만들려면 서버를 따로 띄워야 한다. 모델 위치(OLLAMA_MODELS)는 C: 여유가 적어 D: 에 둔다(README 1절).
param([string]$Root = 'D:\lolypoly\rag', [string]$Models = '')
$ErrorActionPreference = 'Stop'
# 설치 위치: README 1절의 /DIR=D:\lolypoly\rag\ollama, 아니면 Ollama 기본 위치(사용자 폴더)
$exe = @((Join-Path $Root 'ollama\ollama.exe'), (Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe')) |
    Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) { throw "ollama.exe 없음: $Root\ollama 또는 $env:LOCALAPPDATA\Programs\Ollama" }
if (-not $Models) { $Models = Join-Path $Root 'ollama-models' }
$env:OLLAMA_MODELS = $Models
$env:OLLAMA_HOST = '127.0.0.1:11434'          # 이 PC 안에서만
$env:OLLAMA_KEEP_ALIVE = '-1m'                 # 적재한 모델을 내리지 않음(warm_model.ps1 주석: 다시 적재하면 8초 상한에 걸림)
. (Join-Path $PSScriptRoot 'logutil.ps1')
$log = Join-Path $Root 'logs\ollama.log'
if ((Test-Path $log) -and (Get-Item $log).Length -gt 5MB) { Move-Item $log "$log.old" -Force }
# 이미 다른 Ollama(예: 로그인 후 트레이 앱)가 11434 를 쓰고 있으면 그대로 두고 끝낸다(같은 모델 폴더를 쓰면 동작은 같음)
try { Invoke-RestMethod -TimeoutSec 3 'http://127.0.0.1:11434/api/version' | Out-Null; "$(Get-Date -Format s) 이미 실행 중 — 건너뜀" | Out-Log $log; exit 0 } catch { }
$ErrorActionPreference = 'Continue'           # stderr 줄이 NativeCommandError 로 멈추지 않게(run_api.ps1 주석 참고)
& $exe serve 2>&1 | Out-Log $log
exit $LASTEXITCODE
