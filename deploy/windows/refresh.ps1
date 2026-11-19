# 매일 갱신(작업 스케줄러가 호출): 롤리폴리 공개 데이터 내보내기 → 엔진 적재 → 자주 묻는 질문 답 미리 만들기.
# 롤리폴리 수집이 일부 실패해도 내보내기는 한다(실패한 종류는 엔진이 마지막 성공 데이터를 유지). **Windows 미검증.**
param([string]$Root = 'D:\lolypoly\rag', [string]$LolypolyApp = 'D:\lolypoly\app')
$ErrorActionPreference = 'Continue'
$app = Join-Path $Root 'chatbot'
$py = Join-Path $Root 'env\python.exe'
$log = Join-Path $Root 'logs\refresh.log'
$export = Join-Path $Root 'lolypoly-export.json'
[Console]::OutputEncoding = [Text.Encoding]::UTF8; $env:PYTHONUTF8 = '1'; $env:TZ = 'Asia/Seoul'
function Step($name, [scriptblock]$body) {
    "$(Get-Date -Format s) $name 시작" | Add-Content -Encoding UTF8 $log
    & $body 2>&1 | Out-String -Stream | Add-Content -Encoding UTF8 $log
    "$(Get-Date -Format s) $name 종료 코드 $LASTEXITCODE" | Add-Content -Encoding UTF8 $log
    return $LASTEXITCODE
}
# 1) 롤리폴리(자기 venv) 에서 허용 필드만 내보내기
$c1 = Step 'export_rag' { Push-Location $LolypolyApp; & (Join-Path $LolypolyApp '.venv\Scripts\python.exe') manage.py export_rag --out $export; Pop-Location }
if ($c1 -ne 0) { exit $c1 }
# 2) 엔진 적재(멱등) → 3) 미리 만든 답(자료가 바뀐 프로젝트만 다시 만들어짐)
Set-Location $app; $env:PYTHONPATH = "$app\src;$app"; $env:RAG_LOLYPOLY_EXPORT = $export
$c2 = Step 'ingest' { & $py -m ragcore.cli ingest }
if ($c2 -ne 0) { exit $c2 }
$c3 = Step 'warm' { & $py -m ragcore.cli warm }
exit $c3
