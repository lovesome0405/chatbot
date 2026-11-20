# 매일 갱신(작업 스케줄러가 호출): 롤리폴리 공개 데이터 내보내기 → 엔진 적재 → 자주 묻는 질문 답 미리 만들기.
# 롤리폴리 수집이 일부 실패해도 내보내기는 한다(실패한 종류는 엔진이 마지막 성공 데이터를 유지). 2026-11-20 학교 PC에서 실행·확인.
param([string]$Root = 'D:\lolypoly\rag', [string]$LolypolyApp = 'D:\lolypoly\app')
$ErrorActionPreference = 'Continue'
$app = Join-Path $Root 'chatbot'
$py = Join-Path $Root 'env\python.exe'
$log = Join-Path $Root 'logs\refresh.log'
$export = Join-Path $Root 'lolypoly-export.json'
[Console]::OutputEncoding = [Text.Encoding]::UTF8; $env:PYTHONUTF8 = '1'; $env:TZ = 'Asia/Seoul'
. (Join-Path $app 'deploy\windows\logutil.ps1')     # Out-Log: 도는 중에도 로그를 읽을 수 있게(logutil.ps1 주석)
function Step($name, [scriptblock]$body) {
    "$(Get-Date -Format s) $name 시작" | Out-Log $log
    $global:LASTEXITCODE = -1     # 프로그램을 아예 못 띄운 경우 이전 단계의 0 이 남아 성공으로 보이지 않게
    # stderr 줄을 PowerShell 5.1 오류 장식(위치·CategoryInfo) 없이 그대로 기록(run_api.ps1 주석 참고)
    & $body 2>&1 | Out-Log $log
    "$(Get-Date -Format s) $name 종료 코드 $LASTEXITCODE" | Out-Log $log
    return $LASTEXITCODE
}
# 1) 롤리폴리(자기 venv) 에서 허용 필드만 내보내기
$c1 = Step 'export_rag' { Push-Location $LolypolyApp; & (Join-Path $LolypolyApp '.venv\Scripts\python.exe') manage.py export_rag --out $export; Pop-Location }
if ($c1 -ne 0) { exit $c1 }
# 2) 엔진 적재(멱등) → 3) 미리 만든 답(자료가 바뀐 프로젝트만 다시 만들어짐)
. (Join-Path $app 'deploy\windows\env.ps1') $app
Set-Location $app; $env:PYTHONPATH = "$app\src;$app"; $env:RAG_LOLYPOLY_EXPORT = $export
$c2 = Step 'ingest' { & $py -m ragcore.cli ingest }
if ($c2 -ne 0) { exit $c2 }
# warm 은 큰 모델(RAG_WARM_MODEL)을 쓴다. 상주(-1m)시키지 않고 5분 뒤 내려가게 한다(그래픽 메모리 6GB)
$env:OLLAMA_KEEP_ALIVE = '5m'
$c3 = Step 'warm' { & $py -m ragcore.cli warm }
Remove-Item Env:OLLAMA_KEEP_ALIVE
# 4) 큰 모델을 내리고 실시간 모델을 다시 데운다(밀려났으면 다음 질문이 8초에서 끊기는 적재 반복에 빠진다 — warm_model.ps1 주석)
$wm = if ($env:RAG_WARM_MODEL) { @($env:RAG_WARM_MODEL) } else { @() }
$c4 = Step 'warm_model' { & (Join-Path $app 'deploy\windows\warm_model.ps1') -Model $env:OLLAMA_MODEL -Unload $wm }
if ($c3 -ne 0) { exit $c3 }
exit $c4
