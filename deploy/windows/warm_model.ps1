# Ollama 모델을 미리 적재하고 한 번 실행해 둔다(run_api.ps1·refresh.ps1 가 부른다). 2026-11-20 학교 PC에서 추가.
# 왜 필요한가(학교 PC 실측): 모델 적재 + 첫 실행 준비에 20~45초가 걸리는데(D: 는 HDD, GPU 첫 실행), 엔진은 생성을 8초에서 끊는다.
# 끊긴 요청은 Ollama 의 적재까지 취소시켜 다음 질문도 처음부터 적재 → 또 8초에서 끊김이 반복되고, 모든 생성이 원문 발췌/보류로 끝났다
# (63문항 중 생성 26회 전부 시간 초과). 시간 상한 없이 한 번 적재·실행해 두고 keep_alive 를 무기한(-1m)으로 두면 26회 모두 2.3초 안에 끝났다.
param([string]$Model = $env:OLLAMA_MODEL, [string]$Url = 'http://127.0.0.1:11434', [string[]]$Unload = @(),
      [string]$KeepAlive = '-1m', [int]$WaitSec = 300)
$ErrorActionPreference = 'Stop'
if (-not $Model) { $Model = 'qwen2.5:1.5b' }
$deadline = (Get-Date).AddSeconds($WaitSec)
while ($true) {      # 부팅 직후에는 Ollama 가 아직 안 떴을 수 있다
    try { Invoke-RestMethod -TimeoutSec 3 "$Url/api/version" | Out-Null; break }
    catch { if ((Get-Date) -gt $deadline) { "$(Get-Date -Format s) warm_model: Ollama 응답 없음($Url)"; exit 1 }; Start-Sleep 5 }
}
foreach ($m in $Unload) {     # 그래픽 메모리(6GB)를 비운다: 밤 작업용 큰 모델이 실시간 모델을 밀어내지 않게
    try { Invoke-RestMethod -Method Post -TimeoutSec 60 "$Url/api/generate" -ContentType 'application/json' `
            -Body (@{ model = $m; keep_alive = 0 } | ConvertTo-Json) | Out-Null; "$(Get-Date -Format s) warm_model: $m 내림" }
    catch { "$(Get-Date -Format s) warm_model: $m 내리기 실패(무시): $($_.Exception.Message)" }
}
# 엔진과 같은 경로(/api/chat, JSON 형식)로 짧게 한 번 실행해 GPU 첫 실행 준비까지 끝낸다
$body = @{ model = $Model; stream = $false; format = 'json'; keep_alive = $KeepAlive; options = @{ num_predict = 8 }
           messages = @(@{ role = 'user'; content = 'Reply with {"ok": true}' }) } | ConvertTo-Json -Depth 5
$s = Get-Date
try { Invoke-RestMethod -Method Post -TimeoutSec $WaitSec "$Url/api/chat" -ContentType 'application/json' -Body $body | Out-Null }
catch { "$(Get-Date -Format s) warm_model: $Model 실패: $($_.Exception.Message)"; exit 1 }
"$(Get-Date -Format s) warm_model: $Model 적재·실행 {0:N1}초, keep_alive=$KeepAlive" -f ((Get-Date) - $s).TotalSeconds
exit 0
