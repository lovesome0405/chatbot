# 제한 시간 측정 (실제 경로, 2026-11-19)

장비: 클라우드 Linux 컨테이너, CPU 4코어, RAM 15GB, GPU 없음. Ollama 0.40.16(Docker), e5-small ONNX, PostgreSQL 17 + pgvector.
경로: curl(브라우저 대신, CSRF 쿠키·헤더 포함) → LOLYPOLY `/assistant/ask/` → 엔진 `/v1/chat` → Ollama. 명령: `scripts/measure_timeouts.sh` + 아래 추가 측정.

## 1. 구간별 설정값

| 구간 | 설정 | 값 | 근거 |
|---|---|---|---|
| 브라우저(LOLYPOLY `assistant.js`) | AbortController | 75초 | 앱→엔진보다 길게 |
| 브라우저(아리 `app.js`) | AbortController | 75초 | 같음 |
| LOLYPOLY → 엔진 | `LOLYPOLY_RAG_TIMEOUT_SEC` | 60초 | 초과 시 504 + "너무 오래" 안내, 입력 복구 |
| 학교 PC WSGI | waitress `channel_timeout` | 30초 | `deploy/windows/run_web.py` |
| Render/Docker WSGI | gunicorn gthread `--timeout` | 30초 | `Dockerfile` |
| 엔진 → Ollama | `OLLAMA_TIMEOUT_S` | 180초 | 엔진 설정 |
| Cloudflare(학교 PC 공개 주소) | 프록시 응답 대기 | 100초(Cloudflare 문서 기준, **이번에 측정 안 함**) | — |

## 2. 측정 결과

| WSGI 구성 | 질문 | 경로 | HTTP | 총 시간 | 엔진 지연 |
|---|---|---|---|---|---|
| waitress `channel_timeout=30` | 11월 10일 점심 | 정형 | 200 | 1.8초(첫 요청, 앱 기동 포함) | 2.5ms |
| waitress `channel_timeout=30` | 학과수석 입학자 장학금 혜택과 조건(7B) | 생성 | 200 | **53.3초** | 53.2초 |
| waitress `channel_timeout=30` | 국가장학금·근로 장학금 차이(7B) | 생성 | 200 | 36.1초 | 36.1초 |
| gunicorn gthread `--timeout 30` | 11월 10일 점심 | 정형 | 200 | 0.015초 | 1.3ms |
| gunicorn gthread `--timeout 30` | 보훈·북한이탈주민 장학금 비교(7B) | 생성 | 200 | **37.8초** | 36.0초 |
| gunicorn, `LOLYPOLY_RAG_TIMEOUT_SEC=20` | 복지·공로 장학금 비교(7B) | 생성 | **504** | 20.0초 | (엔진은 계속 계산) |

3B 63문항 평가(엔진 직접): 생성 포함 전체 p95 24.9초, 최대 53.1초. 정형 조회·보류는 모델 호출 0회로 수 ms.

## 3. 해석

- **30초 설정은 생성 요청을 끊지 않았다.** waitress `channel_timeout`은 *쉬고 있는* 연결을 닫는 값이고, gunicorn gthread의 `--timeout`은 워커 심장 박동(메인 스레드) 기준이라 스레드에서 처리 중인 요청을 죽이지 않았다. 두 설정 모두 이번 측정에서는 끊는 구간이 아니었다.
- **사용자 요청이 끊기는 구간은 앱 → 엔진 대기(`LOLYPOLY_RAG_TIMEOUT_SEC`)** 였다. 줄이면 504와 안내문이 나오고 화면은 입력을 되살린다. 이때 엔진은 계산을 계속한다(취소 전파 없음 — 남은 한계).
- 운영 공개 주소에서는 Cloudflare 100초가 바깥 한계다. 4코어 CPU + 7B의 최대 53초는 그 안이지만 여유가 크지 않고, 동시에 여러 명이 생성 질문을 하면 Ollama가 차례로 처리해 대기가 더해진다(동시성 측정 안 함).
- 그래서 해결책을 "제한 시간 늘리기"로 두지 않았다: ① 식단·장학 행처럼 구조화된 사실은 정형 경로로 답해 모델을 부르지 않고(L09·N24가 생성 → 정형, 수 ms), ② 화면은 5초 뒤부터 경과 초를 보여 주며, ③ 생성이 필요한 질문만 수십 초가 걸린다는 것을 문서와 화면 문구에 적었다. 학교 GPU·작은 모델·스트리밍 응답은 후속 선택지다.
