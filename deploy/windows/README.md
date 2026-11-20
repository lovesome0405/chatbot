# 학교 PC(Windows)에 엔진 설치 — Docker 없이, 관리자 권한 최소

대상: 롤리폴리가 돌고 있는 강의실 PC(Windows 11, i7-10700, RAM 15.9GB, GPU 미확인).
제약(LOLYPOLY `docs/PROGRESS.md` 2026-11-04): BIOS 가상화 꺼짐 → **Docker·WSL 불가**.
상태: **이 문서와 스크립트는 Windows에서 실행해 보지 않았다(미검증).** 클라우드 Linux에서 같은 구성 요소(PostgreSQL+pgvector, Ollama, e5, uvicorn)로만 확인했다.

## 구성
```
D:\lolypoly\rag\
  miniforge\          파이썬·PostgreSQL·pgvector (conda-forge, 사용자 설치 = 관리자 권한 불필요)
  pgdata\             엔진 DB(롤리폴리 DB와 별개)
  chatbot\            이 저장소
  lolypoly-export.json  롤리폴리 공개 데이터 내보내기(매일 갱신)
  logs\
Ollama              사용자 설치(공식 문서: 관리자 권한 불필요), 모델 qwen2.5:1.5b 또는 qwen3:4b
```
연결: 롤리폴리(같은 PC) → `http://127.0.0.1:8088/v1/chat` (같은 PC라 https 불필요, 앱 설정이 127.0.0.1 만 http 허용).
MARU(방문객 브라우저) → 공개 https 주소가 필요 → 기존 Cloudflare 터널에 경로를 추가하는 작업이 따로 필요(아래 6절, 미구현).

## 1. 프로그램 설치(한 번)
1. **Miniforge**: https://github.com/conda-forge/miniforge 의 Windows 설치 파일 → "Just Me" 선택, 위치 `D:\lolypoly\rag\miniforge`.
2. Miniforge Prompt에서:
   ```bat
   conda create -y -p D:\lolypoly\rag\env -c conda-forge python=3.12 postgresql=17 pgvector
   ```
   conda-forge win-64에 pgvector(0.8.2~0.8.6)·postgresql 패키지가 있는 것을 2026-11-19에 확인했다(설치 자체는 미검증).
3. **Ollama**: https://ollama.com/download 의 OllamaSetup.exe (공식 문서: 관리자 권한 없이 홈 폴더에 설치).
   모델 받기: `ollama pull qwen2.5:1.5b` (약 1.0GB). 상업 이용 제한 없는 Apache 2.0 모델만 쓴다.
4. 이 저장소: `git clone https://github.com/lovesome0405/chatbot D:\lolypoly\rag\chatbot`

## 2. DB 만들기(한 번)
```bat
D:\lolypoly\rag\env\Library\bin\initdb -D D:\lolypoly\rag\pgdata -U rag -E UTF8 --locale=C
D:\lolypoly\rag\env\Library\bin\pg_ctl -D D:\lolypoly\rag\pgdata -o "-p 54329 -c listen_addresses=127.0.0.1" -l D:\lolypoly\rag\logs\pg.log start
D:\lolypoly\rag\env\Library\bin\createdb -h 127.0.0.1 -p 54329 -U rag rag
```

## 3. 엔진 설정(`D:\lolypoly\rag\chatbot\.env`, Git에 넣지 않음)
```
DATABASE_URL=postgresql://rag@127.0.0.1:54329/rag
RAG_EMBEDDER=e5-onnx
RAG_GENERATOR=ollama
OLLAMA_MODEL=qwen2.5:1.5b
RAG_GEN_BUDGET_S=8
RAG_APP_KEYS=lolypoly:<긴 무작위 값>          # 롤리폴리 LOLYPOLY_RAG_APP_KEY 와 같은 값. 예시에 실제 값 쓰지 않기
RAG_PUBLIC_PROJECT=maru
RAG_PUBLIC_ORIGINS=<MARU 사이트 Origin>
RAG_LOLYPOLY_EXPORT=D:\lolypoly\rag\lolypoly-export.json
```
패키지·모델: `D:\lolypoly\rag\env\python -m pip install -r requirements.lock` → `python scripts\fetch_e5.py`.

## 4. 작업 등록 — `install_tasks.ps1`
| 작업 | 언제 | 하는 일 |
|---|---|---|
| `RAG-DB` | 부팅 시 | PostgreSQL 시작 |
| `RAG-API` | 부팅 시(죽으면 1분 뒤 재시작) | `uvicorn ragcore.api:app --host 127.0.0.1 --port 8088` |
| `RAG-Refresh` | 매일 07:10 (롤리폴리 수집 06:10~06:40 뒤) | 롤리폴리 `export_rag` → 엔진 `ingest` → `warm`(자주 묻는 질문 답 미리 만들기) |

미리 만든 답은 **사람이 '맞음'으로 판정한 것만** 화면에 나간다. 자료가 바뀐 날은 새 답이 판정 대기로 쌓이므로, 필요할 때:
```bat
python -m ragcore.cli cache-export --out D:\lolypoly\rag\warm-review.csv
rem 엑셀로 열어 '사람 판정' 열에 맞음/틀림 입력 후 저장
python -m ragcore.cli cache-import --csv D:\lolypoly\rag\warm-review.csv
```
검토하지 않아도 동작은 한다(실시간 경로로 10초 이내 답).

Ollama는 설치 시 사용자 로그인 때 자동 실행된다. 로그인 없이 부팅만 된 상태에서도 돌려야 하면 `ollama serve`를 작업으로 등록해야 한다(미검증).

## 5. 확인
```bat
curl http://127.0.0.1:8088/health
curl -X POST http://127.0.0.1:8088/v1/chat -H "Authorization: Bearer <키>" -H "Content-Type: application/json" -d "{\"question\":\"11월 10일 점심 뭐야?\"}"
```
롤리폴리 `.env`에 `LOLYPOLY_RAG_API_URL=http://127.0.0.1:8088`, `LOLYPOLY_RAG_APP_KEY=<같은 키>` → 웹앱 재시작 → 식단 화면에 안내 칸.
끄기: 롤리폴리 두 값을 비우고 재시작(칸이 사라짐). 엔진 작업 해제: `Get-ScheduledTask RAG-* | Unregister-ScheduledTask -Confirm:$false`.

## 6. 아직 정하지 않은 것
- MARU용 공개 주소: 기존 `lolypoly.lolypoly.workers.dev` Worker → 터널 구조에 `/rag/` 경로를 엔진 8088로 보내는 규칙을 추가하거나, 별도 호스트를 만든다. 어느 쪽이든 공개 경로는 `/v1/public/chat`만 열고 `/v1/chat`(앱 키 경로)은 열지 않는다.
- 학교 PC에서의 실제 생성 속도(8코어라 이 문서의 4코어 측정보다 빠를 것으로 **추정**). 설치 후 `scripts\measure_timeouts.sh` 대신 아래로 잰다:
  `python -m ragcore.cli eval --generate --out reports\school-pc.json` (63문항, 약 10분).
