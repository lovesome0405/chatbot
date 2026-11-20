# 로그 쓰기 도우미(run_api.ps1·run_ollama.ps1·refresh.ps1 가 점-소싱). 2026-11-20 학교 PC에서 추가.
# 왜: 파이프라인 끝의 Add-Content 는 파이프라인이 끝날 때까지 파일을 독점으로 열어, API 가 도는 동안 api.log 를
#     메모장·Get-Content 로도 읽을 수 없었다("다른 프로세스에서 사용 중"). 읽기 공유(ReadWrite)로 열고 줄마다 바로 쓴다.
# 사용: <명령> 2>&1 | Out-Log $log     — stderr 줄은 "$_" 로 PowerShell 5.1 오류 장식(위치·CategoryInfo) 없이 기록
function Out-Log {
    param([Parameter(Mandatory)][string]$Path, [Parameter(ValueFromPipeline)]$Line)
    begin {
        $fs = [IO.File]::Open($Path, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::ReadWrite)
        $w = New-Object IO.StreamWriter($fs, (New-Object Text.UTF8Encoding($false)))
        $w.AutoFlush = $true
    }
    process { $w.WriteLine("$Line") }
    end { $w.Dispose() }
}
