# 두 앱 연동·배포 인계 (v0.4.0 작성, v0.5.0 갱신)

같은 엔진 하나를 **롤리폴리(학생, Django)** 와 **MARU 아리(외국인 방문객, 정적 웹)** 가 각자 원래 화면에서 쓴다.
상태 표기: 로컬 실연동 = 이 문서의 E2E로 확인 / 스테이징·운영 = **미실행**(아래 4절).

## 1. 무엇을 재사용하고 무엇이 앱별인가

| 층 | 공통(엔진, 이 저장소) | 롤리폴리 | MARU 아리 |
|---|---|---|---|
| 응답 계약 | `status, route, answer, citations[], as_of, request_id` (5개 상태) | 그대로 렌더링 | 그대로 렌더링 |
| 검색 | 한글 정규화 키워드 + e5 벡터 + RRF, 범위·공개·기간 필터 | — | — |
| 근거 검증 | 인용 ID·발췌 원문 포함·숫자/날짜·되풀이·(v0.4.0) 로마자 고유명·영어 되풀이 | — | — |
| 어댑터(엔진 안, 앱별) | 엔진은 앱 이름을 모름 | `adapters/lolypoly`: 식단 정형 조회(3상태), 장학표 행 규칙, 공지 제목만 | `adapters/maru`: 장소·코스 ID 검증, 코스 순서, 출입 제한 판정, 서울 구 용어집 |
| 진입점 | `POST /v1/chat`(앱 키) · `POST /v1/public/chat`(MARU 고정, CORS·요청 제한) | Django `POST /assistant/ask/` → `/v1/chat` | 브라우저 → `/v1/public/chat` |
| 화면 상태 전달 | `context`는 어댑터가 허용 ID만 통과 | 없음(질문만) | `place_id`(카드에서 고른 것), `course_id`+장소 순서, `ranked_route_ids` |
| 데이터 갱신 | `ragcore.cli ingest`(멱등, 실패 컬렉션은 삭제 미반영) | `manage.py export_rag` → `RAG_LOLYPOLY_EXPORT` | 저장소 JSON(ari 커밋 고정) |

## 2. 실행 방법(로컬 재현)

```bash
# 엔진
docker compose up -d db && .venv/bin/python scripts/fetch_e5.py
docker run -d --name ollama --network host -v ollama:/root/.ollama ollama/ollama && docker exec ollama ollama pull qwen2.5:1.5b
export PYTHONPATH=src:.; .venv/bin/python -m ragcore.cli ingest
RAG_PUBLIC_ORIGINS=http://127.0.0.1:8765 .venv/bin/uvicorn ragcore.api:app --host 127.0.0.1 --port 8088
# 평가 전용(과거 공지 기간 재현). 일반 서버에는 두지 않는다
RAG_ALLOW_REFERENCE_TIME=1 RAG_FIXED_NOW=2026-09-15T12:00 RAG_PUBLIC_ORIGINS=http://127.0.0.1:8765 .venv/bin/uvicorn ragcore.api:app --port 8089
RAG_ALLOW_REFERENCE_TIME=1 RAG_FIXED_NOW=2026-11-01T12:00 RAG_PUBLIC_ORIGINS=http://127.0.0.1:8765 .venv/bin/uvicorn ragcore.api:app --port 8090

# 롤리폴리(브랜치 claude/rag-assistant)
LOLYPOLY_RAG_API_URL=http://127.0.0.1:8088 LOLYPOLY_RAG_APP_KEY=<RAG_APP_KEYS의 lolypoly 키> python manage.py runserver 127.0.0.1:8000
# MARU(브랜치 claude/rag-bridge): rag-config.json 의 endpoint 를 "auto" 로 바꾼 뒤
python3 -m http.server 8765 --bind 127.0.0.1

# 화면 E2E(실제 경로 + 장애 모의)
node e2e/apps.e2e.cjs           # → reports/v0.5.0/e2e/results.json, *.png
node e2e/ari_config.test.cjs <ari>/app.js
```

## 3. 공개 데이터 갱신(롤리폴리)

운영 경로(학교 PC 예약 작업 또는 Render 크론):
```bash
python manage.py collect_all --rag-export /data/lolypoly-rag-export.json        # LOLYPOLY 쪽, 일부 수집이 실패해도 내보냄
RAG_LOLYPOLY_EXPORT=/data/lolypoly-rag-export.json python -m ragcore.cli ingest --project lolypoly   # 엔진 쪽
```
- 내보내는 필드: 식단(date, meal_type, items, source_url, collected_at)·학사일정·공지(제목만). 계정·커뮤니티·택시방·의견·사진·버스 제외.
- `collected_at`은 실제 수집 시각 그대로. 실패한 종류는 `last_run_status=failed` → 엔진이 그 종류의 삭제를 반영하지 않아 마지막 성공 데이터·원래 수집일 유지.
- 두 기계가 다르면 파일을 옮기는 단계(scp·공유 폴더 등)가 하나 더 필요하다. **엔진 쪽 HTTP 적재 API는 만들지 않았다.**
- 재현(운영 DB 없이): `scripts/lolypoly_refresh.py` — 임시 DB 2회 갱신 → 재적재 → 답 변경, 공지 실패 시 보존. 2026-11-19 결과 `lolypoly-refresh/report.json` 세 확인 모두 true. 성공 시각은 report.json `run_at`.

## 4. 배포 인계(미실행 — 결정·승인 필요)

| 항목 | 내용 |
|---|---|
| 엔진 실행 위치 | **결정(2026-11-20): 롤리폴리가 도는 학교 PC**. Docker·WSL을 못 쓰는 PC라 Miniforge(PostgreSQL+pgvector)·Ollama 사용자 설치·작업 스케줄러로 구성 → `deploy/windows/README.md`(Windows 미검증). 롤리폴리는 같은 기계라 `http://127.0.0.1:8088`로 부르고, MARU용 공개 주소만 터널에 경로 추가가 필요 |
| 두 앱이 닿을 HTTPS 주소 | 미정. 예: `https://rag.<도메인>` (Cloudflare Tunnel). 롤리폴리는 서버→엔진, MARU는 **방문객 브라우저→엔진**이라 공개 주소가 필요 |
| 엔진 환경변수 | `DATABASE_URL`, `RAG_EMBEDDER=e5-onnx`, `RAG_GENERATOR=ollama`, `OLLAMA_URL`, `OLLAMA_MODEL`, `RAG_APP_KEYS`(lolypoly 키), `RAG_PUBLIC_PROJECT=maru`, `RAG_PUBLIC_ORIGINS`(MARU 사이트 Origin, 쉼표 구분), `RAG_PUBLIC_RATE_PER_MIN`(기본 20), `RAG_TRUST_PROXY_HOPS`(프록시 뒤면 1), `RAG_LOLYPOLY_EXPORT`. 운영에서 `RAG_ALLOW_REFERENCE_TIME`·`RAG_FIXED_NOW`는 두지 않는다 |
| 롤리폴리 환경변수 | `LOLYPOLY_RAG_API_URL`(https), `LOLYPOLY_RAG_APP_KEY`, 선택 `LOLYPOLY_RAG_TIMEOUT_SEC`, `LOLYPOLY_RAG_LIMIT_PER_10MIN` |
| MARU 설정 | `rag-config.json` 의 `endpoint` = `https://<엔진>/v1/public/chat` |
| 비밀 값 | 앱 키는 엔진 `RAG_APP_KEYS` 와 롤리폴리 서버 환경변수에만. 브라우저·저장소·예시에 넣지 않는다 |
| 끄는 방법 | 롤리폴리: `LOLYPOLY_RAG_API_URL` 또는 키를 비움 → 칸 숨김·주소 404. MARU: `endpoint` 를 `off` → 기존 아리 흐름. 엔진: 키 제거로 401 |
| 프록시 점검 | 프록시 뒤면 `RAG_TRUST_PROXY_HOPS=1`(기본 0은 X-Forwarded-For 무시 → 모든 방문객이 프록시 주소 하나로 묶여 20회/분 공유). HTTPS 종단, CORS 응답 헤더, 429 `Retry-After`, `Server-Timing` 노출을 실제 주소에서 확인 |
| 제한 시간 | `TIMEOUTS.md` 참고 |

## 5. 병합·롤백 순서

1. **엔진(계약) 먼저**: 이 PR(`claude/next-steps` → `main`). 응답 계약은 v0.3.0과 같고 추가만 했다(`Server-Timing`·`X-Request-Id` 헤더, 선택 설정). 이전 앱이 깨지지 않는다.
2. **소비 앱**: LOLYPOLY `claude/rag-assistant`, ari `claude/rag-bridge`. 둘 다 기본 꺼짐이라 병합만으로 동작이 바뀌지 않는다. LOLYPOLY `main` 병합은 Render 자동 배포를 시작할 수 있으니 승인 후.
3. **롤백**: 앱은 설정으로 먼저 끈다(위 표) → 필요하면 앱 커밋 되돌리기. 엔진은 `main` 을 이전 태그/커밋으로 되돌리면 되고 DB 스키마 변경은 없다(재적재만).
4. 이 세션은 두 앱 저장소에 push 권한이 없었다(세션 저장소 범위 밖, `add_repo` 거부). 앱 변경은 `patches/` 의 `git am` 용 패치로 남겼다:
   ```bash
   cd LOLYPOLY && git checkout -b claude/rag-assistant ccc0237 && git am <chatbot>/reports/v0.4.0/patches/lolypoly/*.patch
   cd ari && git checkout -b claude/rag-bridge a3a5f0f && git am <chatbot>/reports/v0.4.0/patches/ari/*.patch
   ```
