# 학교 PC v0.6.0 업데이트·실측 (2026-11-26)

모든 수치는 **[학교 PC]** 값이다(Windows 11, GTX 1660 Ti 6GB, D: HDD, Ollama 0.40.16, e5-small ONNX CPU, 생성 상한 8초).
측정은 별도 DB `rag_eval`(저장소 fixture)에서 했고 운영 DB(`rag`, 롤리폴리 DB)는 업데이트 절차 말고는 건드리지 않았다.
재현: `eval_v060.ps1`(측정), `coldstart.py`(첫 질문 지연, 앱 키는 `.env` 에서 읽기만 함).

## 1. 업데이트

| 항목 | 결과 |
|---|---|
| 엔진 코드 | `main` b50aff3 로 pull. 의존성·배포 스크립트 변경 없음 |
| RAG-API 재시작 | 일반 권한 `Stop/Start-ScheduledTask` 로는 **안 됨**: 예전 uvicorn(S4U, 세션 0)이 남아 새 API 가 `Errno 10048` 로 종료. 사람이 관리자 PowerShell 로 uvicorn 까지 끄고 재시작(09:40:19) → `/health` ok, `generator_ready` true. README 5절 명령·7절 ⑫ |
| 롤리폴리 `update.ps1 -Branch main` (사람, 관리자) | 3fd5417 → 97142cf. 마이그레이션 **`campus.0006_mealhours` 1개** 적용, 기존 표 행 수 그대로(`campus_mealhours` 0 추가), 응답 점검 6개 기대값 |
| 식단 수집(`Lolypoly-Collect-Meals` 수동) | 종료 코드 0, "식사시간표: 갱신" |
| `RAG-Refresh` | 작업 결과 0. `export_rag` 에 `'meal_hours': 1`, 상태 `'meal_hours': 'success'` → `ingest` lolypoly **success**(이전 partial), 문서 284 → 285 |
| 공개 주소 식단 화면 | "학생식당 몇 시까지 해?" → 정형 답 "학생식당 주중: 아침 08:00 - 08:50, 점심 11:50 - 13:20, 저녁 17:30 - 18:20 [1]" + 출처(수집 2026-11-26 09:44 KST). "기숙사비 얼마야?" → '찾지 못했어요'(일반 답변 아님, 관련 원문 3개는 '답변 근거 아님'). **"광합성이 뭐야?" → '찾지 못했어요'(기대: 출처 없는 일반 답변) ✗** — 아래 2절 |

## 2. 발견·수정: 일반 답변이 상주 모델을 내려 버림 (README 7절 ⑬)

- 증상: 일반 답변(route=general) 질문마다 8초 시간 초과(`errors: general:GenerationTimeout`), 그 뒤 `ollama ps` 가 비고 다음 문서 질문은 '모델 준비 중'. 오늘 세 번 재현(09:41:10 평가 C01, 09:46:05·09:54:2x 화면 "광합성이 뭐야?").
- 원인: `generate_text`(일반 답변)만 `num_ctx=2048`, 문서 생성·`warm_model` 은 4096. Ollama 는 `num_ctx` 가 바뀌면 모델을 통째로 다시 적재하고, 이 PC 에서는 재적재가 8초를 넘어 연결이 끊기며 적재가 취소된다(Ollama 로그 `client connection closed before llama-server finished loading`). 내림 자체는 Ollama 로그에 남지 않는다(디버그 수준). 모델 없이 5분 대기·직접 생성 1회로는 재현되지 않았고, 일반 답변 요청 때만 재현.
- 수정(브랜치 `claude/school-pc-v060`): 모든 생성 요청이 `NUM_CTX=4096`. 단위 테스트 추가(단위 38 passed, DB 테스트는 이 PC 에서 미실행). 평가 기록에 `general`(버린 이유)·`errors` 추가.
- **운영 엔진은 아직 main(수정 전)** 이다. main 병합 + RAG-API 재시작(관리자) 전까지 롤리폴리 안내 칸의 일반 답변은 동작하지 않고, 일반 질문이 들어오면 모델이 빠졌다가 다음 문서 질문 때 뒤에서 다시 적재된다(약 13초, 4절).
- 같이 본 것(원인 아님): Ollama 트레이 앱이 09:24 에 업데이트 설치 파일(1.9GB)을 받아 두었고 로그인 세션에서 `ollama` 를 약 5초마다 띄웠다 끝낸다. 5분 관찰 동안 운영 서버·상주 모델에 영향 없음(README 6절).

## 3. 63문항 + 검증 질문 25개 (main b50aff3, 모델 상주, `school-pc-warm.json` 과 같은 명령)

| 지표 [학교 PC] | v0.5.0 (`../school-pc-warm.json`, 2026-11-20) | **v0.6.0 63문항** (`eval-63.json`) | v0.6.0 v0.4.0 검증 12개 (`holdout040.json`) | v0.6.0 v0.5.0 검증 13개 (`holdout050.json`) |
|---|---|---|---|---|
| 10초 이내 | 63/63 | **63/63** | 12/12 | 13/13 |
| 지연 평균 / p95 / 최대 | 0.54 / 1.51 / 2.23초 | **0.58 / 1.51 / 4.13초** | 0.61 / 1.37 / 2.74초 | 0.22 / 1.20 / 1.61초 |
| 상태 일치 | 57/63 | **57/63** | 11/12 | 11/13 |
| 핵심 사실(답한 문항) | 43/44 | 43/44 | 9/9 | 12/12 |
| 기대 출처 인용 | 41/44 | 41/44 | 9/9 | 0/0 |
| 정형 정답 | 10/10 | 10/10 | 3/3 | 11/13 |
| 답할 수 있는데 보류 | 6/48 | 6/48 | 1/10 | 1/13 |
| **영어 질문 → 영어 답** | 7/11 | **11/11** | 5/5 | 0/0 |
| 노출 · 없는 ID · 만료/제목만 세부 답 | 0 · 0 · 0 | **0 · 0 · 0** | 0 · 0 · 0 | 0 · 0 · 0 |
| 모델 호출(생성) | 26 | 26 | 5 | 2 |

- 상태 불일치 6개(N02·N05·N06·N07·N08·N22, 모두 보류)는 v0.5.0 과 같은 문항이다. 이 63문항에는 일반 답변 질문이 없어 2절 문제가 드러나지 않았다(측정 중 모델 계속 상주, 09:39:55~09:40:56).
- 검증 질문 불일치: H09(보류), P05(partial), P08(보류). 학교 PC 의 v0.5.0 검증 질문 값은 없다(이번이 처음).
- README 의 v0.5.0 상주 열 "영어 7/10" 은 JSON 분모(11)와 달라 7/11 로 고쳤다.

## 4. 첫 질문 지연 (운영 엔진 main, `coldstart.txt`)

엔진의 '적재됨' 캐시(30초)가 지나도록 35초 조용히 둔 뒤 `ollama stop qwen2.5:1.5b` → `/v1/chat` 에 "장학금 신청 공지 알려줘"(문서 경로, 생성 1회)를 응답 후 3초 간격으로.

| 보낸 시각(내린 뒤) | 응답 시간 | 나온 것 |
|---|---|---|
| 0.1초 | **0.22초** | '답변 모델을 준비하는 중이라 지금은 문장을 만들지 못했어요…' + 관련 자료 3개 |
| 3.3 · 6.4 · 10.0초 | 0.12 · 0.57 · 0.13초 | 같음(뒤에서 적재 중) |
| **13.2초** | 2.03초 | 정상 생성(생성 1.97초) |
| 18.2 · 22.0초 | 0.82 · 0.83초 | 정상 생성 |

→ 첫 질문은 0.2초 안에 '준비 중' 안내와 자료, **약 13초 뒤부터 정상 생성**. 뒤에서 건 적재는 `keep_alive=-1m` 이라 끝난 뒤 `ollama ps` = Forever(따로 데우지 않아도 됨, 확인 차 `warm_model` 한 번 더 실행 0.3초).
- 주의: 마지막 성공 생성 뒤 30초 안에 모델이 빠지면 캐시 때문에 생성 요청이 8초 상한으로 나가 적재를 취소한다(2절 첫 재현이 이 경로). 수정본에서는 일반 답변이 모델을 내리지 않으므로 이 경우가 거의 없다.

## 5. 새 질문 24개 (`eval/questions_v060.jsonl`, `RAG_GENERAL_MARU=1` 평가 전용, qwen2.5:1.5b)

| [학교 PC] | main 카드 미검수 | main [검수 가정] | **수정본 카드 미검수** | **수정본 [검수 가정]** |
|---|---|---|---|---|
| 인사 G01~05 → smalltalk | 5/5 | 5/5 | 5/5 | 5/5 |
| 상식 C01~06 → general | **0/6** (4개 8초 초과, 2개 '준비 중') | **0/6** | **6/6** | **6/6** |
| 함정 T01~06 → 보류 | 6/6 | 6/6 | 6/6 | 6/6 |
| 개인정보·탈옥 S01~03 → 보류(고정 거절) | 3/3 | 3/3 | 3/3 | 3/3 |
| 카드 K01~04 | 4/4 모두 보류 | K01·K02 공식 원문 인용, K03·K04 '확인하지 못한 항목' 보류 | 4/4 모두 보류 | K01·K02 원문 인용, K03·K04 보류 |
| **인수: T·S 의 route=general** | **0건** | **0건** | **0건** | **0건** |
| **인수: general 인데 citations>0** | **0건** | **0건** | **0건** | **0건** |
| 상태 일치 | 18/24 | 18/24 | **24/24** | **24/24** |
| 지연 p95 / 최대 | 8.01 / 8.19초 | 8.02 / 8.09초 | 1.35 / 1.75초 | 0.94 / 1.35초 |
| 측정 뒤 `ollama ps` | **비어 있음** | **비어 있음** | 1.5b Forever | 1.5b Forever |

- [검수 가정]: `school_info.json` 원본은 그대로(needs_review=true). `%TEMP%` 사본만 needs_review=false 로 바꿔 `RAG_LOLYPOLY_SCHOOL_INFO` 로 rag_eval 에만 적재하고, 측정 뒤 미검수 상태로 다시 적재했다.
- 카드 미검수일 때 K03 "본관 건물은 어디에 있어?" 는 일반 답변까지 갔다가 답에 '학교'가 있어 서버가 버리고 보류(`domain_term:학교`). 막는 장치가 동작한 것이지만, 카드를 적재하지 않은 동안은 답 필터에만 기대는 경로다.

## 6. 일반 답변 모델 비교 (수정본, 카드 미검수, 같은 24문항)

| [학교 PC] | qwen2.5:1.5b (기본) | qwen3:4b |
|---|---|---|
| 상태 일치 | 24/24 | 22/24 |
| C 일반 답변으로 나간 수 | 6/6 | 4/6 |
| general 시도 / 버림 | 7 / 1 (`domain_term:학교` — K03) | 7 / 3 (`domain_term:college` C02, `domain_term:exams` C03, `domain_term:school` K03) |
| 지연 p95 / 최대 | 1.35 / 1.75초 | 3.58 / 6.46초 |
| `ollama ps` (SIZE · 처리) | 1.2 GB · 100% GPU | 3.2 GB · 100% GPU (측정 중 1.5b 와 함께 상주, 합 4.4GB/6GB) |

**qwen3:4b 의 일반 답변에는 생각 과정 글이 그대로 나온다**(`think:false` 인데도 "Okay, let's see. The user is asking…" 로 시작하는 영어 추론). 버려진 3개도 이 추론 글에 나온 college·exams·school 때문이다. 그대로는 화면에 쓸 수 없다. 기본 모델은 바꾸지 않았다.

상식 질문 답 원문(정답 여부 칸은 비워 둠 — 사람 판정):

| ID | 질문 | qwen2.5:1.5b 답 | 정답? | qwen3:4b 답 | 정답? |
|---|---|---|---|---|---|
| C01 | 파이썬에서 리스트와 튜플의 차이가 뭐야? | 파이썬에서 리스트와 튜플은 동일한 기능을 하지만, 튜플은 변경 불가능한 리스트입니다. 즉, 튜플의 요소는 수정할 수 없지만, 리스트의 요소는 변경할 수 있습니다. (1.1초) |  | Okay, let's see. The user is asking about the difference between lists and tuples in Python. I need to answer in Korean, keep it brief, and make sure it's from general knowledge.  First, I remember that lists are mutable, meaning … (3.2초) |  |
| C02 | 광합성이 뭐야? | 광합성은 식물이 태양의 에너지를 이용해 공기 중의 산소와 물을 분해하면서 생성되는 과정입니다. 이 과정은 식물의 기능 중 하나로, 식물의 생존과 번식에 필수적입니다. (0.5초) |  | (보류, 버림 `domain_term:college`) 버려진 원문: Okay, the user is asking "광합성이 뭐야?" which means "What is photosynthesis?" in Korean.  First, I need to recall what photosynthesis is. From general knowledge, photosy… (2.2초) |  |
| C03 | 시험 공부할 때 집중하는 방법 알려줘 | 시험을 잘 준비하려면 우선 공부 내용을 정리하고, 필요한 정보를 복습하세요. 또한, 적절한 시간을 설정하고, 집중할 수 있는 환경을 만들어야 합니다. 마지막으로, 휴식과 운동도 중요합니다. (0.4초) |  | (보류, 버림 `domain_term:exams`) 버려진 원문: Okay, the user is asking for ways to focus when studying for exams. Let me think about general study techniques that are safe to mention.  First, I need to make sure i… (2.2초) |  |
| C04 | How do I say thank you in Korean? | In Korean, you can say thank you by simply saying "감사합니다" (gamsahamnida). (0.4초) |  | Okay, the user is asking how to say "thank you" in Korean. Let me recall the basic phrases. The most common one is "감사합니다" (gamsa-hamnida). But I should check if there's a more casual way too. Wait, the user might be a foreign vis… (2.8초) |  |
| C05 | 김치는 어떤 음식이야? | 김치는 한국의 전통적인 양념치킨입니다. 간장과 소금을 넣고 냉동시켜 만듭니다. (1.7초) |  | Okay, let's see. The user is asking "김치는 어떤 음식이야?" which translates to "What kind of food is kimchi?" in Korean.  First, I need to recall what kimchi is. Kimchi is a traditional Korean fermented vegetable dish, usually made with n… (6.5초) |  |
| C06 | What is a hanbok? | A hanbok is a traditional Korean dress, worn for special occasions and formal events. It consists of a jacket-like upper garment and a skirt-like lower garment, often paired with a head covering. (0.4초) |  | Okay, the user is asking about what a hanbok is. Let me recall my knowledge. Hanbok is the traditional Korean clothing. It's a key part of Korean culture. I need to keep it brief and friendly as per the instructions.  First, I sho… (2.2초) |  |

(qwen3:4b 답은 230자에서 자름. 전체는 `new-unreviewed-qwen3-4b-fix.json`.)

## 7. 미확인
- 수정본의 운영 반영(main 병합·RAG-API 재시작 전). 수정본으로 공개 화면 "광합성이 뭐야?" → "출처 없는 일반 답변" 표시는 아직 못 봄.
- DB 테스트(test_db.py)는 이 PC 에서 돌리지 않았다(단위 테스트만).
- 재부팅 뒤 자동 시작(이 보고 뒤 따로, README 5절 "운영 적용" 5).
- 트레이 앱이 받아 둔 업데이트가 설치되면 생기는 일.
