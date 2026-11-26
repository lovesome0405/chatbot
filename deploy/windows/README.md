# 학교 PC(Windows)에 엔진 설치 — Docker 없이, 관리자 권한 최소

대상: 롤리폴리가 돌고 있는 강의실 PC(Windows 11 Home, i7-10700 8코어/16스레드, RAM 15.9GB, **GPU GTX 1660 Ti 6GB**, C: NVMe SSD 여유 약 10GB, D: HDD).
제약(LOLYPOLY `docs/PROGRESS.md` 2026-11-04): BIOS 가상화 꺼짐 → **Docker·WSL 불가**.
학교 PC에서 Claude 세션으로 설치하려면 `CLAUDE_SESSION_PROMPT.md`의 요청을 붙여 넣는다.

상태(2026-11-20, 학교 PC에서 Claude 세션이 직접 실행): 1~3절과 5절의 엔진 확인, 63문항 측정은 **Windows에서 실행해 확인**.
4절 작업 등록은 **관리자 권한이 필요해 아직 등록하지 않음**(일반 권한으로는 접근 거부). 같은 스크립트를 작업 없이 직접 실행해 동작은 확인했다.
Windows에서 원래 문서와 다르게 동작한 것과 고친 내용은 7절에 있다.

## 구성
```
D:\lolypoly\rag\
  miniforge\          conda(사용자 설치 = 관리자 권한 불필요)
  env\                파이썬 3.12 · PostgreSQL 16 · pgvector (conda-forge)
  pgdata\             엔진 DB(롤리폴리 DB와 별개)
  ollama\             Ollama 프로그램(약 3.2GB, C: 여유가 적어 D: 에 설치)
  ollama-models\      Ollama 모델(qwen2.5:1.5b 1.0GB + qwen3:4b 2.5GB)
  chatbot\            이 저장소
  lolypoly-export.json  롤리폴리 공개 데이터 내보내기(매일 갱신)
  logs\               pg.log · ollama.log · api.log · refresh.log
```
연결: 롤리폴리(같은 PC) → `http://127.0.0.1:8088/v1/chat` (같은 PC라 https 불필요, 앱 설정이 127.0.0.1 만 http 허용).
MARU(방문객 브라우저) → 공개 https 주소가 필요 → 기존 Cloudflare 터널에 경로를 추가하는 작업이 따로 필요(아래 6절, 미구현).

## 1. 프로그램 설치(한 번, 관리자 권한 불필요)
1. **이 저장소**: `git clone https://lovesome0405@github.com/lovesome0405/chatbot D:\lolypoly\rag\chatbot`
   (비공개 저장소. Git 자격 증명 관리자에 GitHub 계정이 여러 개 있으면 계정 없는 주소로는 다른 계정이 쓰여 `Repository not found` 가 난다 → 주소에 `lovesome0405@` 를 붙인다.)
2. **Miniforge**: https://github.com/conda-forge/miniforge/releases 의 `Miniforge3-Windows-x86_64.exe`(2026-11-20: 26.9.4-2, 158MB, GitHub에 적힌 sha256과 대조, 서명 NumFOCUS).
   조용히 "Just Me" 설치(PATH·기본 파이썬 등록 안 함):
   ```powershell
   Start-Process .\Miniforge3-Windows-x86_64.exe -Wait -ArgumentList '/S','/InstallationType=JustMe','/RegisterPython=0','/AddToPath=0','/NoRegistry=1','/NoShortcuts=1','/D=D:\lolypoly\rag\miniforge'
   ```
3. 파이썬·DB 환경 — **PostgreSQL 16**(17이 아님):
   ```bat
   D:\lolypoly\rag\miniforge\Scripts\conda.exe create -y -p D:\lolypoly\rag\env -c conda-forge python=3.12 postgresql=16 pgvector=0.8
   ```
   conda-forge 의 Windows(win-64) pgvector 0.8.x 는 모두 libpq 16 으로 빌드돼 있어 `postgresql=17` 과 함께 풀리지 않는다(2026-11-20 확인).
   결과: PostgreSQL 16.15 + pgvector 0.8.6. `sql/schema.sql` 은 PostgreSQL 15+ 기준이라 16 에서 그대로 동작한다.
4. **Ollama**: https://ollama.com/download 의 `OllamaSetup.exe`(2026-11-20: 0.40.16, 1.86GB, 서명 Ollama Inc.).
   설치하면 약 3.2GB, 모델까지 3.3GB 가 더 필요해 C: 대신 D: 에 둔다. 모델 위치는 사용자 환경변수 `OLLAMA_MODELS` 로 정한다:
   ```powershell
   [Environment]::SetEnvironmentVariable('OLLAMA_MODELS','D:\lolypoly\rag\ollama-models','User')
   Start-Process .\OllamaSetup.exe -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/DIR=D:\lolypoly\rag\ollama'
   ```
   (`-Wait` 를 붙이면 설치 프로그램이 띄운 트레이 앱이 끝날 때까지 기다려 멈춘 것처럼 보인다.)
   설치 직후 뜬 트레이 앱은 환경변수 설정 전에 시작돼 모델을 C: 에 받으려 한다 → 트레이 앱을 끄고(`Get-Process 'ollama app','ollama' | Stop-Process`)
   다음 줄로 서버를 띄운 뒤 모델을 받는다(2026-11-20 에는 트레이 앱을 다시 켜도 서버가 뜨지 않았다. 원인 미확인).
   ```powershell
   powershell -ExecutionPolicy Bypass -File D:\lolypoly\rag\chatbot\deploy\windows\run_ollama.ps1
   ```
   모델 받기(상업 이용 제한 없는 Apache 2.0 모델만, `ollama show <모델> --license` 로 확인):
   ```bat
   D:\lolypoly\rag\ollama\ollama.exe pull qwen2.5:1.5b
   D:\lolypoly\rag\ollama\ollama.exe pull qwen3:4b
   ```
   이 PC에서는 Ollama 가 GTX 1660 Ti 를 CUDA 로 잡아 모델 전체(29/29층)를 GPU 에 올린다.

## 2. DB 만들기(한 번)
**cmd(명령 프롬프트)에서** 실행한다. Git Bash 에서 `cmd //c '...'` 로 넘기면 `-o "..."` 따옴표가 깨져 `pg_ctl: unrecognized operation mode "54329"` 가 난다.
```bat
D:\lolypoly\rag\env\Library\bin\initdb -D D:\lolypoly\rag\pgdata -U rag -E UTF8 --locale=C
D:\lolypoly\rag\env\Library\bin\pg_ctl -D D:\lolypoly\rag\pgdata -o "-p 54329 -c listen_addresses=127.0.0.1" -l D:\lolypoly\rag\logs\pg.log start
D:\lolypoly\rag\env\Library\bin\createdb -h 127.0.0.1 -p 54329 -U rag rag
```
initdb 는 로컬 접속을 `trust`(비밀번호 없음)로 만든다. 127.0.0.1 에만 열려 있지만, 이 PC에 로그인하는 다른 사용자는 접속할 수 있다.

## 3. 엔진 설정(`D:\lolypoly\rag\chatbot\.env`, Git에 넣지 않음)
```
DATABASE_URL=postgresql://rag@127.0.0.1:54329/rag
RAG_EMBEDDER=e5-onnx
RAG_E5_MODEL_DIR=models/multilingual-e5-small
RAG_GENERATOR=ollama
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:1.5b
RAG_WARM_MODEL=qwen3:4b
RAG_GEN_BUDGET_S=8
# 학교 PC 필수: 모델을 메모리에서 내리지 않음(7절 ④ — 다시 적재하면 8초 상한에 걸려 적재가 반복 취소됨)
OLLAMA_KEEP_ALIVE=-1m
# 롤리폴리 LOLYPOLY_RAG_APP_KEY 와 같은 값. 예시·채팅에 실제 값 쓰지 않기(줄 끝 주석은 지원하지 않음)
RAG_APP_KEYS=lolypoly:<긴 무작위 값>
RAG_PUBLIC_PROJECT=maru
# MARU 공개 주소가 정해지면(6절) 추가: RAG_PUBLIC_ORIGINS=<MARU 사이트 Origin>
RAG_LOLYPOLY_EXPORT=D:\lolypoly\rag\lolypoly-export.json
```
키 만들기(화면에 찍지 않고 파일에만): 파이썬 `secrets.token_urlsafe(48)` 로 만든 값을 엔진 `.env` 와 롤리폴리 `.env` 두 곳에만 쓴다.
패키지·모델(저장소 폴더에서):
```bat
D:\lolypoly\rag\env\python -m pip install -r requirements.lock
D:\lolypoly\rag\env\python scripts\fetch_e5.py
```
엔진은 `.env` 를 **스스로 읽는다**(`ragcore.services.load_dotenv`, 이미 있는 환경변수는 덮어쓰지 않음). 작업 스케줄러 스크립트는 `env.ps1` 로도 읽는다.
그래서 `.env` 값을 한 번만 바꾸려면 변수를 지우지 말고 **다른 값으로 설정**해야 한다(지우면 `.env` 값이 다시 들어온다).
손으로 명령을 칠 때는 PowerShell 에서 먼저:
```powershell
cd D:\lolypoly\rag\chatbot; . .\deploy\windows\env.ps1 (Get-Location); $env:PYTHONPATH="$PWD\src;$PWD"; $env:PYTHONUTF8='1'
```

## 4. 작업 등록 — `install_tasks.ps1` (**관리자 PowerShell 필요**)
"로그인하지 않아도 실행"(S4U) 작업은 관리자만 등록할 수 있다. 일반 권한으로 실행하면 `Register-ScheduledTask : 액세스가 거부되었습니다 (0x80070005)`.
롤리폴리 작업 5개도 같은 방식이다. 롤리폴리 작업은 건드리지 않는다(이름이 모두 `RAG-` 로 시작).
```powershell
powershell -ExecutionPolicy Bypass -File D:\lolypoly\rag\chatbot\deploy\windows\install_tasks.ps1
```
| 작업 | 언제 | 하는 일 |
|---|---|---|
| `RAG-DB` | 부팅 시 | PostgreSQL 시작 |
| `RAG-Ollama` | 부팅 시(죽으면 1분 뒤 재시작) | `run_ollama.ps1` → `ollama serve`(모델 위치 D:, 모델 상주). 트레이 앱은 로그인 때만 뜨므로 따로 둔다 |
| `RAG-API` | 부팅 1분 뒤(죽으면 1분 뒤 재시작) | `run_api.ps1` → 실시간 모델 미리 적재(`warm_model.ps1`) → `uvicorn ragcore.api:app --host 127.0.0.1 --port 8088` |
| `RAG-Refresh` | 매일 07:10 (롤리폴리 수집 06:10~06:40 뒤) | 롤리폴리 `export_rag` → 엔진 `ingest` → `warm`(자주 묻는 질문 답 미리 만들기, qwen3:4b) → 4B 내리고 1.5B 다시 데우기 |

이 PC의 PowerShell 실행 정책은 LocalMachine=AllSigned 이다. 작업은 `-ExecutionPolicy Bypass` 로 실행해 서명 없이 돈다.
로그는 실행 중에도 메모장·`Get-Content` 로 읽을 수 있다(`logutil.ps1`).

미리 만든 답은 **사람이 '맞음'으로 판정한 것만** 화면에 나간다. 자료가 바뀐 날은 새 답이 판정 대기로 쌓이므로, 필요할 때:
```bat
python -m ragcore.cli cache-export --out D:\lolypoly\rag\warm-review.csv
rem 엑셀로 열어 '사람 판정' 열에 맞음/틀림 입력 후 저장
python -m ragcore.cli cache-import --csv D:\lolypoly\rag\warm-review.csv
```
검토하지 않아도 동작은 한다(실시간 경로로 10초 이내 답).

## 5. 확인
```bat
curl http://127.0.0.1:8088/health
D:\lolypoly\rag\ollama\ollama.exe ps
```
`/health` 는 `"status":"ok"`, `"generator_ready":true`. `ollama ps` 는 `qwen2.5:1.5b  100% GPU ... Forever` 여야 한다(Forever 가 아니면 7절 ④).
앱 키 경로 확인은 키를 명령줄에 쓰지 말고 파일에서 읽어 보낸다(2026-11-20: 맞는 키 200, 틀린 키 401 확인).
롤리폴리 `.env`에 `LOLYPOLY_RAG_API_URL=http://127.0.0.1:8088`, `LOLYPOLY_RAG_APP_KEY=<같은 키>` 두 줄 → 웹앱 재시작 → 식단 화면에 안내 칸.
롤리폴리 쪽 코드(`export_rag`, 안내 칸, D-073)는 LOLYPOLY `main` 3fd5417 부터 있다. 학교 PC는 2026-11-23 `update.ps1 -Branch main`(관리자)으로 afe70e2 → 3fd5417 업데이트했다(아래 "운영 적용").
끄기: 롤리폴리 두 값을 비우고 재시작(칸이 사라짐). 엔진 작업 해제(관리자): `Get-ScheduledTask RAG-* | Unregister-ScheduledTask -Confirm:$false`.

**엔진 코드를 바꾼 뒤 재시작(관리자 PowerShell 필요, 7절 ⑫)** — `git pull` 만으로는 돌고 있는 API 가 바뀌지 않는다:
```powershell
Stop-ScheduledTask RAG-API; Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object CommandLine -like '*uvicorn*ragcore.api*' | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-ScheduledTask RAG-API
```
확인: `api.log` 에 새 `Started server process` → `Uvicorn running on http://127.0.0.1:8088`(그 사이 `Errno 10048` 이 없어야 함), `/health` = ok.

### 63문항 측정(학교 PC, 2026-11-20)
평가 문항은 저장소 fixture 기준이라 운영 DB와 섞이지 않게 별도 DB 에서 잰다:
```powershell
D:\lolypoly\rag\env\Library\bin\createdb -h 127.0.0.1 -p 54329 -U rag rag_eval
cd D:\lolypoly\rag\chatbot; . .\deploy\windows\env.ps1 (Get-Location); $env:PYTHONPATH="$PWD\src;$PWD"; $env:PYTHONUTF8='1'; $env:TZ='Asia/Seoul'
$env:DATABASE_URL='postgresql://rag@127.0.0.1:54329/rag_eval'; $env:RAG_LOLYPOLY_EXPORT="$PWD\data\lolypoly\export.json"
D:\lolypoly\rag\env\python -m ragcore.cli ingest
D:\lolypoly\rag\env\python -m ragcore.cli eval --generate --out reports\school-pc.json
```
| 지표 | 클라우드 4코어 CPU (SPEED.md, 1.5B [재생]) | 학교 PC, 모델 차가운 상태 (`school-pc.json`) | **학교 PC, 모델 상주** (`school-pc-warm.json`) | **학교 PC v0.6.0, 모델 상주** (`school-pc-v060/eval-63.json`, 2026-11-26) |
|---|---|---|---|---|
| 10초 이내 답변 | 63/63 | 63/63 | **63/63** | **63/63** |
| 지연 평균 / p95 / 최대 | 2.6 / 8.0 / 8.1초 | 3.3 / 8.0 / 8.3초 | **0.5 / 1.5 / 2.2초** | **0.6 / 1.5 / 4.1초** |
| 상태 일치 | 56/63 | 54/63 | **57/63** | **57/63** |
| 생성이 8초 안에 끝난 횟수 | 20/26 | 0/26 (전부 적재 중 취소) | **26/26** | **26/26** (최대 지연 4.1초) |
| 답할 수 있는데 보류 | 6/48 | 8/48 | 6/48 | 6/48 |
| 핵심 사실 · 기대 출처 인용 | 43/43 · 40/43 | 40/41 · 39/41 | 43/44 · 41/44 | 43/44 · 41/44 |
| 정형 정답 · 노출 | 10/10 · 0 | 10/10 · 0 | 10/10 · 0 | 10/10 · 0 |
| 영어 질문 → 영어 답 | 6/10 | 6/10 | 7/11 (이전 표기 7/10 은 오기, JSON 분모 11) | **11/11** |

- 같은 63문항, 같은 모델(qwen2.5:1.5b), e5-small, 생성 상한 8초. 클라우드 열은 [재생] 값이고 학교 PC 두 열은 [실생성] 값이다.
- 첫 측정은 모델이 메모리에 없는 상태에서 시작해, 생성 26회가 모두 적재 중에 8초 상한으로 끊겼다(7절 ④). 상주시킨 뒤 같은 명령으로 다시 쟀다.
- 첫 측정은 211초 걸렸다(클라우드 예상 약 10분). 상주 측정의 소요 시간은 따로 재지 않았다.
- v0.6.0 열(2026-11-26): 같은 명령, 같은 조건(모델 상주 확인 후 시작). 63문항 42초. 검증 질문 25개와 v0.6.0 새 질문 24개는 `reports/school-pc-v060/REPORT.md`.

### 롤리폴리 main 사전 확인(운영과 분리한 시험본, 2026-11-20)
운영 롤리폴리 업데이트(관리자 필요) 전에, LOLYPOLY `main`(3fd5417)을 임시 폴더에 복제하고 **운영 DB 사본**·운영 venv·다른 포트(8001, 개발 서버)로 띄워 확인했다. 운영 코드·DB·웹앱은 바꾸지 않았고, 시험본과 DB 사본은 확인 뒤 지웠다.
- `check` 이슈 0, `migrate --plan` 적용할 마이그레이션 없음(운영 DB 사본 기준).
- `refresh.ps1 -LolypolyApp <시험본>`: export_rag(식단 84·일정 93·공지 42) · ingest · warm(2분 44초) · warm_model **모두 종료 코드 0**. 끝난 뒤 `ollama ps` = qwen2.5:1.5b Forever.
- 브라우저: 식단 화면에 "롤리폴리 안내에게 물어보기" 칸. "11월 10일 점심 뭐야?" → 3초 안에 실제 메뉴와 출처([1] 식단, 수집 2026-11-14 06:11 KST). "기숙사 관련 공지 있어?" → 지어내지 않고 "찾지 못했어요" + 관련 공지 3건.
- 그 결과 엔진 운영 DB(`rag`)에는 이미 실제 롤리폴리 자료가 적재돼 있다(RAG-Refresh 가 매일 같은 일을 한다).

발견한 것:
- **식사시간표 미연동**: 저장소 fixture 에는 `meal_hours`(학생식당 식사시간)가 있지만 롤리폴리 `export_rag` 는 내보내지 않는다 → 운영 적재 상태가 `partial`(`meal_hours: failed`)이고 "식사시간" 질문에 정형 답이 나가지 않는다. 설치 문제가 아니라 두 저장소의 연동 차이(코드 수정 필요, 이 작업 범위 밖).
- **캐시 폴더 권한**: 운영 웹앱(S4U 작업)이 만든 `%TEMP%\lolypoly-cache` 는 로그인한 사용자 세션에서 접근 거부된다. 같은 계정으로 롤리폴리 개발 서버·명령을 손으로 돌리면 파일 캐시가 임시 파일 만들기를 계속 재시도하며 **멈춘다**(안내 칸 질문이 응답 없음). 시험할 때는 `LOLYPOLY_CACHE_DIR` 를 다른 폴더로 준다. 운영 웹앱 자신은 해당 없음.
- **Ollama 트레이 앱**: `run_ollama.ps1` 서버가 떠 있을 때 트레이 앱을 켜면 두 번째 서버를 띄우지 않고 기존 서버(11434)를 그대로 쓴다. 모델 상주(Forever) 유지. 트레이 앱의 1시간 간격 자동 업데이트가 서버를 건드리는지는 미확인.

### 운영 적용(학교 PC, 2026-11-23)
1. 손으로 띄워 둔 엔진(PostgreSQL·Ollama·API)을 멈추고 관리자 PowerShell 로 `install_tasks.ps1` 실행 → 종료 코드 0, `RAG-DB`·`RAG-Ollama`·`RAG-API`·`RAG-Refresh` 등록.
   - `RAG-DB` 는 `pg_ctl start` 가 끝나면 작업 상태가 Ready(결과 0)로 바뀌지만 PostgreSQL 은 계속 떠 있다(정상).
   - S4U(로그인 세션 밖) Ollama 도 GPU(GTX 1660 Ti, CUDA)를 잡았다. API 시작 때 `warm_model` 이 디스크에서 처음 적재해 **89.6초** 걸렸고(그동안 `/health` 응답 없음), 그 뒤 `/health` = ok, `ollama ps` = qwen2.5:1.5b 상주(Forever).
2. 관리자 PowerShell 로 롤리폴리 `update.ps1 -Branch main` → afe70e2 → 3fd5417. 표별 행 수 그대로, 마이그레이션 0건, 응답 점검 6개 모두 기대값, 웹앱 재시작으로 `.env` 의 `LOLYPOLY_RAG_*` 두 줄 적용.
3. `Start-ScheduledTask RAG-Refresh` → 작업 결과 0. 로그: export_rag(식단 105·일정 93·공지 42, 수집 상태 모두 success) · ingest(문서 284, 청크 535) · warm(1분 9초) · warm_model(4B 내리고 1.5B 0.2초) **모두 종료 코드 0**.
4. 브라우저, 공개 주소 `https://lolypoly.lolypoly.workers.dev/meals/` 식단 화면: "11월 10일 점심 뭐야?" → 실제 메뉴와 출처([1] 2026-11-10(화) 중식 식단, 수집 DB). 엔진 로그 `route=structured, status=answered, 19.9ms`.
5. 재부팅 뒤 자동 시작 — **확인(2026-11-26)**. 2026-11-23 에는 하지 않았고(이 PC는 다른 사람도 쓴다), 그날 허락을 받아 2026-11-26 에 재부팅했다. 부팅 10:09:05, 점검 10:11~10:12(부팅 2분 12초·3분 22초 뒤 두 번, 결과 같음).
   - `Get-ScheduledTask RAG-* | Get-ScheduledTaskInfo`: `RAG-DB` 10:09:21 결과 0(Ready, 정상) · `RAG-Ollama` 10:09:21 Running(267009 = 실행 중) · `RAG-API` 10:10:21 Running(267009) · `RAG-Refresh` 다음 실행 11-27 07:10.
   - `curl http://127.0.0.1:8088/health` → `"status":"ok"`, `generator_ready:true`, 문서 285 · 청크 536. `api.log`: 10:10:34 `warm_model` 1.5B 적재 11.7초 → `Uvicorn running on http://127.0.0.1:8088`, 그 사이 `Errno 10048` 없음.
   - `ollama ps` → qwen2.5:1.5b, 100% GPU, CONTEXT 4096, UNTIL **Forever**.
   - 공개 주소 식단 화면 "학생식당 몇 시까지 해?" → "학생식당 주중: 아침 08:00 - 08:50, 점심 11:50 - 13:20, 저녁 17:30 - 18:20 [1]" + 출처(학생식당 식사시간표, LOLYPOLY 수집 DB). 엔진 로그 `route=structured, status=answered, 367.8ms, model_calls=0`.
   - 주의: 이 PC 는 부팅 18초 뒤(10:09:23) 대화형 로그온이 있었다(자동 로그온 또는 사용자). 그래서 "아무도 로그인하지 않은 상태"는 따로 확인하지 못했다. 다만 세 작업(S4U)은 로그온보다 먼저(10:09:21) 시작됐다.
   - 이번 확인은 운영 main b50aff3 기준이다. 이 브랜치의 num_ctx 수정(7절 ⑬)은 아직 운영에 없다.

발견한 것:
- 롤리폴리 `.env` 의 `DJANGO_ALLOWED_HOSTS` 에 있는 `lolypoly.com` 은 2026-11-23 현재 다른 곳의 판매용 주차 도메인(GoDaddy)으로 열린다. 실제 공개 주소는 `lolypoly.lolypoly.workers.dev`. 로컬 `http://127.0.0.1:8000` 은 HTTPS 로 넘기므로(301) 브라우저 확인은 공개 주소로 한다.
- 업데이트 직후 첫 방문에는 "Lolypoly가 새로워졌어요" 안내 창이 안내 칸 입력을 가린다(닫으면 정상).

### v0.6.0 업데이트(학교 PC, 2026-11-26) — 상세·수치 `reports/school-pc-v060/REPORT.md`
1. 엔진 `git pull`(main b50aff3) → RAG-API 재시작은 **관리자 필요**(위 명령, 7절 ⑫). 롤리폴리 `update.ps1 -Branch main`(관리자) 3fd5417 → 97142cf, 마이그레이션 `campus.0006_mealhours` 1개.
2. 식단 수집 1회 → `RAG-Refresh`: `export_rag` 에 `meal_hours` 1행·success, `ingest` lolypoly success(이전 partial). 공개 화면 "학생식당 몇 시까지 해?" → 정형 답 + 출처.
3. 일반 답변이 상주 모델을 내리는 문제 발견(7절 ⑬) → 브랜치 `claude/school-pc-v060` 에서 수정. 운영 반영은 main 병합 + RAG-API 재시작 뒤.

## 6. 아직 정하지 않은 것
- ~~재부팅 뒤 자동 시작: 미확인~~ → 2026-11-26 재부팅으로 확인(위 "운영 적용" 5). 부팅 직후 대화형 로그온이 있어 "로그인 전혀 없음" 상태만 따로 확인하지 못했다.
- MARU용 공개 주소: 기존 `lolypoly.lolypoly.workers.dev` Worker → 터널 구조에 `/rag/` 경로를 엔진 8088로 보내는 규칙을 추가하거나, 별도 호스트를 만든다. 어느 쪽이든 공개 경로는 `/v1/public/chat`만 열고 `/v1/chat`(앱 키 경로)은 열지 않는다.
- 트레이 앱 자동 업데이트가 `RAG-Ollama` 서버를 멈추거나 바꾸는지: **미확인**(동시 실행 자체는 문제없음, 5절). 문제가 있으면 트레이 앱의 시작 프로그램 등록을 끈다.
  - 2026-11-26 관찰: 트레이 앱이 09:24 에 업데이트 설치 파일(`%LOCALAPPDATA%\Ollama\updates_v2\<해시>\OllamaSetup.exe`, 1.9GB)을 받아 두었고, 로그인 세션에서 `ollama` 프로세스를 약 5초마다 새로 띄웠다 끝낸다(`ollama.pid` 가 계속 바뀜). `RAG-Ollama` 서버(세션 0, 0.40.16)와 상주 모델은 5분 지켜본 동안 영향이 없었다(모델이 빠진 원인은 7절 ⑬). 설치 파일이 실행되면 서버 버전이 바뀔 수 있으므로 업데이트 알림은 누르지 않는다.
- ~~롤리폴리 `export_rag` 에 식사시간표(`meal_hours`) 추가(5절 발견).~~ → v0.6.0 코드 반영(LOLYPOLY ERR-015, 브랜치 `claude/rag-v060`). 학교 PC 반영은 병합·`update.ps1` 뒤(요청문 `CLAUDE_V060_PROMPT.md`).
- ~~엔진 쪽 근본 수정(모델이 적재 중이면 바로 원문 발췌로 답하기)~~ → v0.6.0 코드 반영: 모델이 메모리에 없으면 생성 요청을 보내지 않고 뒤에서 적재만 건다(이 세션 CPU 측정 `reports/v0.6.0/REPORT.md` 7절). 상주 설정(`OLLAMA_KEEP_ALIVE=-1m`)은 그대로 두는 것을 권한다. 학교 PC 측정은 요청문 4번.
- MARU 공개 경로: v0.6.0 에서 LOLYPOLY Worker 에 `/rag/v1/public/chat` 규칙을 만들었다(로컬 검증만). 엔진 8088 용 VPC 서비스·배포는 승인 후(`CLAUDE_V060_PROMPT.md` "범위 밖").

## 7. 학교 PC 설치 기록(2026-11-20) — 원래 문서와 다르게 동작한 것
| # | 증상 | 원인 | 고친 것 |
|---|---|---|---|
| ① | `git clone` → `Repository not found` | 자격 증명 관리자에 GitHub 계정 3개, 기본 계정에 비공개 저장소 권한 없음 | 주소에 `lovesome0405@` (1절) |
| ② | `conda create ... postgresql=17 pgvector` 의존성 충돌 | win-64 pgvector 는 libpq 16 으로만 빌드 | `postgresql=16 pgvector=0.8` (1절) |
| ③ | PowerShell 스크립트의 한글 로그가 `醫낅즺 肄붾뱶` 로 깨짐 | BOM 없는 UTF-8 → Windows PowerShell 5.1 이 CP949 로 읽음 | 모든 `.ps1` 에 UTF-8 BOM |
| ④ | 모든 생성이 8초에서 끊겨 원문 발췌/보류만 나옴(26/26) | 모델 적재+첫 실행 20~45초(D: HDD, GPU 첫 실행) > 상한 8초. 끊긴 요청이 Ollama 적재까지 취소해 다음 질문도 처음부터 적재(Ollama 로그 `client connection closed before llama-server finished loading, aborting load`, HTTP 499) | `OLLAMA_KEEP_ALIVE=-1m`(엔진 `.env` + `run_ollama.ps1`), API 시작 전 미리 적재(`warm_model.ps1`), 매일 갱신 뒤 4B 내리고 1.5B 다시 데우기 |
| ⑤ | `run_api.ps1` 이 시작하자마자 종료 | `$ErrorActionPreference='Stop'` + `2>&1` → uvicorn 의 stderr 첫 줄이 NativeCommandError | 네이티브 호출은 `Continue` 로 |
| ⑥ | API 가 도는 동안 `api.log` 를 읽을 수 없음 | 파이프라인 끝 `Add-Content` 가 파일을 독점으로 염 | `logutil.ps1` 의 `Out-Log`(읽기 공유, 줄마다 기록) |
| ⑦ | `refresh.log` 에 stderr 줄마다 `위치 ... + CategoryInfo` 장식 | `Out-String -Stream` 이 ErrorRecord 를 서식화 | `Out-Log`(문자열로 기록), 단계 시작 때 `$LASTEXITCODE=-1` |
| ⑧ | 로그인 없이 부팅된 상태에서 Ollama 없음 | 트레이 앱은 로그인 때만 시작 | `RAG-Ollama` 작업 추가 |
| ⑨ | `install_tasks.ps1` 접근 거부(0x80070005) | S4U 작업 등록은 관리자 권한 필요 | 문서에 명시(4절). 2026-11-23 관리자 PowerShell 로 등록 |
| ⑩ | 문서: "엔진은 `.env` 를 스스로 읽지 않는다" | 실제로는 `load_dotenv()` 가 읽음 | 3절 문구 수정 |
| ⑪ | (2026-11-23) 관리자 창으로 `update.ps1` 을 `*> 로그파일` 로 감싸 실행 → 1단계에서 종료 코드 1, 바뀐 것 없음 | ⑤와 같은 원인: 출력을 돌리면 `git fetch` 의 정상 stderr("From https://...")가 `Stop` 아래 NativeCommandError 가 됨 | 출력을 돌리지 말고 그대로 실행(기록이 필요하면 `Start-Transcript`). `update.ps1` 자체는 수정 불필요 |
| ⑫ | (2026-11-26) 일반 권한으로 `Stop-ScheduledTask RAG-API` → `Start-ScheduledTask RAG-API` 했더니 예전 코드가 계속 응답, 새 API 는 `[Errno 10048]`(8088 사용 중)으로 바로 종료 | 작업을 멈춰도 `run_api.ps1` 이 띄운 python(uvicorn)은 남는다. S4U(세션 0) 프로세스라 로그인한 사용자 권한으로는 명령줄도 안 보이고 `Stop-Process` 는 접근 거부 | 관리자 PowerShell 로 uvicorn 까지 끄고 다시 시작(5절 명령). 그 사이 엔진은 예전 코드로 계속 응답하므로 서비스는 끊기지 않는다 |
| ⑬ | (2026-11-26, v0.6.0) 일반 답변(route=general) 질문이 들어올 때마다 상주 모델이 메모리에서 빠짐 → "광합성이 뭐야?" 8초 시간 초과, 그 뒤 문서 질문도 '준비 중' | 일반 답변 요청만 `num_ctx=2048`(문서 생성·`warm_model` 은 4096). Ollama 는 `num_ctx` 가 바뀌면 모델을 통째로 다시 적재하는데, 이 PC 에서는 재적재가 8초 상한을 넘어 취소되고 모델이 빠진 채로 남는다. Ollama 로그에는 내림이 찍히지 않고(디버그 수준) 다음 적재만 보인다. 클라우드 CPU 에서는 재적재가 빨라 드러나지 않았다 | 모든 생성 요청이 같은 `NUM_CTX=4096`(`src/ragcore/generation.py`, 단위 테스트 추가). 브랜치 `claude/school-pc-v060`, main 병합·RAG-API 재시작(관리자) 전에는 운영에 미반영 |
