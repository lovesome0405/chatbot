# 학교 PC 세션용 요청문 — 엔진 v0.6.0 업데이트와 실측

언제 쓰나: 주상이 **chatbot PR(v0.6.0)과 LOLYPOLY PR(claude/rag-v060)을 main 에 병합하기로 승인한 뒤**.
병합 전에 쓰면 학교 PC가 아직 없는 코드를 찾는다. 이 문서는 학교 PC에서 Claude 새 세션에 그대로 붙여 넣는다.

## 그 전에 사람이 할 일
1. 두 PR 병합 승인(또는 병합). LOLYPOLY `main` 병합은 Render 자동 배포를 시작할 수 있다.
2. 학교 PC에서 관리자 PowerShell 을 열 수 있게 준비한다(LOLYPOLY 업데이트 `update.ps1`, 마이그레이션 1개).
3. Worker 공개 경로(MARU)는 이 요청에 넣지 않았다. 따로 승인한다(아래 "범위 밖").

## 붙여 넣을 요청

```text
학교 PC의 RAG 엔진과 롤리폴리를 v0.6.0 으로 업데이트하고 실측해줘.

먼저 읽기: D:\lolypoly\rag\chatbot 의 deploy/windows/README.md(특히 5~7절), CHANGELOG.md v0.6.0, reports/v0.6.0/REPORT.md,
D:\lolypoly\app 의 AGENTS.md, docs/PROGRESS.md, docs/ERROR_LOG.md(ERR-015).

지킬 것
- 관리자 권한이 필요한 단계(update.ps1, 작업 스케줄러 변경)는 하기 전에 나한테 묻고, 내가 승인하거나 직접 실행한다.
- 운영 DB(rag, 롤리폴리 DB)는 업데이트 절차 말고는 건드리지 않는다. 측정은 별도 DB rag_eval 에서 한다(README 5절 "63문항 측정"과 같은 방법).
- 학교 기본 정보 카드(data/lolypoly/school_info.json)의 needs_review 는 바꾸지 않는다(주상 검수 대상). 측정용으로 검수 가정 사본을 쓸 때는 rag_eval 에서만, 결과에 [검수 가정]이라고 적는다.
- Worker 배포, 엔진 VPC 서비스 생성, 터널 설정 변경은 하지 않는다.
- 앱 키·.env 값은 채팅·로그·Git 에 쓰지 않는다.
- 문서와 실제가 다르면 실제 동작하는 쪽으로 고치고 chatbot 새 브랜치 claude/school-pc-v060 에 커밋·푸시한다(main 병합은 내가 따로 말함).

할 일
1. 업데이트
   - 엔진: cd D:\lolypoly\rag\chatbot; git pull(main) → RAG-API 작업 재시작 → /health 가 ok, generator_ready true.
   - 롤리폴리: 관리자 PowerShell 로 D:\lolypoly\app\deploy\windows\update.ps1 -Branch main (출력 돌리지 말 것, README 7절 ⑪).
     마이그레이션 campus/0006_mealhours 1개가 적용되는지 확인.
   - Start-ScheduledTask RAG-Refresh → 로그에서 export_rag 에 meal_hours 가 나오고(첫 식단 수집 뒤부터), ingest 상태가 success 인지(이전 partial).
     식단 수집이 아직 안 돌았으면 롤리폴리 수집 작업을 한 번 돌린 뒤 다시 확인. 결과를 ERR-015 남은 확인에 적는다.
   - 브라우저(https://lolypoly.lolypoly.workers.dev/meals/): "학생식당 몇 시까지 해?" → 정형 답과 출처, "광합성이 뭐야?" → "출처 없는 일반 답변" 표시, "기숙사비 얼마야?" → 찾지 못했어요(일반 답변 아님).
2. 63문항 + 검증 질문 25개 실측(GPU, 모델 상주) — 기존 school-pc-warm.json 과 같은 조건:
   eval/questions.jsonl, eval/questions_v040_holdout.jsonl, eval/questions_v050_holdout.jsonl → reports/school-pc-v060/*.json
   표: 10초 이내 수, 평균/p95/최대, 상태 일치, 핵심 사실, 영어 질문→영어 답, 노출·없는 ID·만료 세부 답. v0.5.0 학교 PC 값(57/63, p95 1.5초)과 비교.
3. 새 질문 24개(eval/questions_v060.jsonl) 실측: RAG_GENERAL_MARU=1 로(평가 전용), 카드 미검수 상태와 [검수 가정] 사본 두 가지.
   인수 기준: 함정(T*)·개인정보/탈옥(S*) 질문에 route=general 0건, route=general 답은 citations 0개, 카드 질문(K*)은 원문 인용 또는 보류.
4. 첫 질문 지연(③): ollama stop qwen2.5:1.5b 로 내린 뒤 롤리폴리 안내 칸(또는 /v1/chat)에 문서 질문 1개 → 몇 초에 무엇이 나오는지, 그 뒤 몇 초부터 정상 생성되는지.
   (이 세션 클라우드 CPU 값: 첫 질문 0.05초 '모델 준비 중' 안내 + 관련 자료, 약 4초 뒤부터 정상 생성. 이전 코드는 9.5초 시간 초과가 3번 연속)
   측정이 끝나면 모델을 다시 상주시킨다(warm_model.ps1).
5. 일반 답변 모델 비교: 같은 24문항을 OLLAMA_MODEL=qwen2.5:1.5b 와 qwen3:4b 로 각각(rag_eval, RAG_GENERAL_MARU=1).
   표: 상식 질문(C01~C06) 답 원문(정답 여부 판정 칸은 비워 둠 — 주상이 판정), general 이 버려진 수와 이유(debug.general.dropped), p95 지연, ollama ps 의 메모리(SIZE·GPU 비율).
   기본 모델은 바꾸지 않는다(결정 사항). 결과만 보고.
6. 보고(한국어): 실제로 한 것 / 실패하고 고친 것 / 표(분모 포함, 학교 PC 값이라고 표기) / 미확인 / 주상이 할 일.
```

## 범위 밖(따로 승인)
- MARU 공개 경로 켜기: Cloudflare 에서 엔진 `127.0.0.1:8088` 용 VPC 서비스 만들기 → LOLYPOLY `deploy/cloudflare-worker/wrangler.jsonc` 의 `RAG_ENGINE` 줄 켜기 → `wrangler deploy` → 엔진 `.env` 에 `RAG_PUBLIC_ORIGINS=<MARU 사이트 Origin>`, `RAG_TRUST_PROXY_HOPS=1` → ari `rag-config.json` 의 `endpoint` 를 `https://lolypoly.lolypoly.workers.dev/rag/v1/public/chat`. 실제 경로에서 `X-Forwarded-For` 가 한 값으로 오는지(hops=1 이 맞는지) 다시 확인해야 한다(로컬 wrangler dev 에서만 확인함).
- 미리 만든 답 39개 판정, 학교 기본 정보 카드 검수(주상).
