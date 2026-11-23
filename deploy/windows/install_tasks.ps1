# 엔진 작업 등록(학교 PC). 여러 번 실행해도 안전(같은 이름은 덮어씀). 2026-11-23 학교 PC 관리자 PowerShell에서 등록·확인(일반 권한은 0x80070005).
# 사용: powershell -ExecutionPolicy Bypass -File deploy\windows\install_tasks.ps1 [-RunAs <계정>] [-Root D:\lolypoly\rag]
# 롤리폴리 install.ps1 과 같은 방식(S4U: 비밀번호 저장 없이, 로그인하지 않아도 이 계정으로 실행).
param([string]$RunAs = "$env:USERDOMAIN\$env:USERNAME", [string]$Root = 'D:\lolypoly\rag')
$ErrorActionPreference = 'Stop'
$env_ = Join-Path $Root 'env'
$py = Join-Path $env_ 'python.exe'
$app = Join-Path $Root 'chatbot'
$ps = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
foreach ($p in $py, (Join-Path $app '.env'), (Join-Path $Root 'pgdata')) { if (-not (Test-Path $p)) { throw "없음: $p" } }
New-Item -ItemType Directory -Force (Join-Path $Root 'logs') | Out-Null
$principal = New-ScheduledTaskPrincipal -UserId $RunAs -LogonType S4U -RunLevel Limited
$always = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

# 1) DB
$pgctl = Join-Path $env_ 'Library\bin\pg_ctl.exe'
$db = New-ScheduledTaskAction -Execute $pgctl `
    -Argument "-D `"$Root\pgdata`" -o `"-p 54329 -c listen_addresses=127.0.0.1`" -l `"$Root\logs\pg.log`" start"
Register-ScheduledTask -TaskName 'RAG-DB' -Action $db -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $principal `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries) -Force | Out-Null

# 1-2) Ollama 서버(로그인 없이 부팅만 된 상태에서도 답을 만들도록). 설치 프로그램의 트레이 앱은 로그인 때만 뜬다.
$ollama = New-ScheduledTaskAction -Execute $ps -WorkingDirectory $Root `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$app\deploy\windows\run_ollama.ps1`" -Root `"$Root`""
Register-ScheduledTask -TaskName 'RAG-Ollama' -Action $ollama -Trigger (New-ScheduledTaskTrigger -AtStartup) -Principal $principal `
    -Settings $always -Force | Out-Null

# 2) API (127.0.0.1 에만 바인딩. 공개는 터널 규칙으로 /v1/public/chat 만)
$api = New-ScheduledTaskAction -Execute $ps -WorkingDirectory $app `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$app\deploy\windows\run_api.ps1`" -Root `"$Root`""
$t = New-ScheduledTaskTrigger -AtStartup; $t.Delay = 'PT1M'          # DB 가 먼저 뜨도록 1분 뒤
Register-ScheduledTask -TaskName 'RAG-API' -Action $api -Trigger $t -Principal $principal -Settings $always -Force | Out-Null

# 3) 매일 갱신: 롤리폴리 수집(06:10~06:40) 뒤
$refresh = New-ScheduledTaskAction -Execute $ps -WorkingDirectory $app `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$app\deploy\windows\refresh.ps1`" -Root `"$Root`""
$jobSet = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 10) -ExecutionTimeLimit (New-TimeSpan -Hours 1) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'RAG-Refresh' -Action $refresh -Trigger (New-ScheduledTaskTrigger -Daily -At '07:10') `
    -Principal $principal -Settings $jobSet -Force | Out-Null

Start-ScheduledTask -TaskName 'RAG-DB'; Start-ScheduledTask -TaskName 'RAG-Ollama'; Start-Sleep 5; Start-ScheduledTask -TaskName 'RAG-API'
Get-ScheduledTask -TaskName 'RAG-*' | Select-Object TaskName, State | Format-Table -AutoSize
