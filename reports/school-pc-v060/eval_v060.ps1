# 학교 PC v0.6.0 측정 (rag_eval 전용). 운영 DB(rag)는 건드리지 않는다.
#  -Code : 실행할 코드 폴더(main = D:\lolypoly\rag\chatbot, 수정본 = D:\lolypoly\rag\chatbot-v060fix)
#  .env 는 항상 운영 폴더의 것을 읽고 DATABASE_URL 만 rag_eval 로 덮어쓴다.
param([ValidateSet('base','new','model4b')][string]$Stage = 'base',
      [string]$Out = 'D:\lolypoly\rag\chatbot\reports\school-pc-v060',
      [string]$Code = 'D:\lolypoly\rag\chatbot', [string]$Tag = '')
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$prod = 'D:\lolypoly\rag\chatbot'
. "$prod\deploy\windows\env.ps1" $prod
$app = $Code; Set-Location $app
$env:PYTHONPATH = "$app\src;$app"; $env:PYTHONUTF8 = '1'; $env:TZ = 'Asia/Seoul'
$env:DATABASE_URL = 'postgresql://rag@127.0.0.1:54329/rag_eval'
$env:RAG_E5_MODEL_DIR = "$prod\models\multilingual-e5-small"   # .env 의 상대 경로는 worktree 에 없다
$env:RAG_LOLYPOLY_EXPORT = "$app\data\lolypoly\export.json"
Remove-Item Env:RAG_LOLYPOLY_SCHOOL_INFO -ErrorAction SilentlyContinue
$py = 'D:\lolypoly\rag\env\python.exe'
$ollama = 'D:\lolypoly\rag\ollama\ollama.exe'
$warm = "$prod\deploy\windows\warm_model.ps1"
New-Item -ItemType Directory -Force $Out | Out-Null
"code=$app commit=$(git -C $app rev-parse --short HEAD) tag=$Tag"
function T($label, [scriptblock]$b) { $s = Get-Date; & $b; "{0} {1}: {2:N1}s exit={3}" -f (Get-Date -Format s), $label, ((Get-Date) - $s).TotalSeconds, $LASTEXITCODE }
function Ingest($label) { T $label { & $py -m ragcore.cli ingest --reset 2>&1 | Select-Object -Last 1 } }
function Ev($q, $file) { T "eval $file" { & $py -m ragcore.cli eval --generate --questions $q --out "$Out\$file" 2>&1 | Select-Object -Last 1 } }
function OPs($label) { "--- ollama ps ($label)"; & $ollama ps }

if ($Stage -eq 'base') {
    Ingest 'ingest(card unreviewed)'
    OPs 'before'
    Ev 'eval\questions.jsonl' "eval-63$Tag.json"
    Ev 'eval\questions_v040_holdout.jsonl' "holdout040$Tag.json"
    Ev 'eval\questions_v050_holdout.jsonl' "holdout050$Tag.json"
    OPs 'after'
}
if ($Stage -eq 'new') {
    $env:RAG_GENERAL_MARU = '1'
    Ingest 'ingest(card unreviewed)'
    & $warm -Model 'qwen2.5:1.5b'; OPs 'before unreviewed'
    Ev 'eval\questions_v060.jsonl' "new-unreviewed-qwen2.5-1.5b$Tag.json"
    OPs 'after unreviewed'
    # [검수 가정] 사본: 원본 카드는 바꾸지 않고 rag_eval 적재용 사본만 needs_review=false
    $copy = Join-Path $env:TEMP 'school_info.assumed-reviewed.json'
    $card = Get-Content -Raw -Encoding UTF8 "$app\data\lolypoly\school_info.json" | ConvertFrom-Json
    $card.needs_review = $false
    $card | Add-Member -Force NoteProperty reviewed_by '[검수 가정] 측정 전용 사본'
    $card | Add-Member -Force NoteProperty reviewed_at (Get-Date -Format s)
    [IO.File]::WriteAllText($copy, ($card | ConvertTo-Json -Depth 20), (New-Object Text.UTF8Encoding($false)))
    $env:RAG_LOLYPOLY_SCHOOL_INFO = $copy
    Ingest 'ingest(card [검수 가정])'
    & $warm -Model 'qwen2.5:1.5b'; OPs 'before assumed'
    Ev 'eval\questions_v060.jsonl' "new-card-assumed-reviewed-qwen2.5-1.5b$Tag.json"
    OPs 'after assumed'
    Remove-Item Env:RAG_LOLYPOLY_SCHOOL_INFO
    Ingest 'ingest(card unreviewed 복원)'
}
if ($Stage -eq 'model4b') {
    $env:RAG_GENERAL_MARU = '1'; $env:OLLAMA_MODEL = 'qwen3:4b'
    Ingest 'ingest(card unreviewed)'
    T 'warm qwen3:4b' { & $warm -Model 'qwen3:4b' }
    OPs 'before 4b'
    Ev 'eval\questions_v060.jsonl' "new-unreviewed-qwen3-4b$Tag.json"
    OPs 'after 4b'
    & $ollama stop qwen3:4b
    T 'warm qwen2.5:1.5b' { & $warm -Model 'qwen2.5:1.5b' }
    OPs 'end'
}
