# ragcore — 한국어 생활정보·전통문화 안내 공통 RAG 엔진

같은 검색·근거·답변 엔진 하나로 두 서비스를 처리한다.
- **롤리폴리**(한국폴리텍대학 춘천캠퍼스 생활정보): 식단·학사일정·공지·장학
- **MARU**(외국인 대상 서울 전통문화 안내): 장소·코스·기간 공지

프로젝트별 명칭·조회 규칙은 어댑터에 두고, 엔진은 프로젝트 이름을 모른다. 세 번째 도메인(도서관, 합성)은 JSON 파일 등록만으로 검색된다.

> 상태(2026-11-17): 로컬 구현·테스트·평가·시연까지 실행했다. 운영 배포, 원격 푸시, 원본 앱(LOLYPOLY·ari) 수정, 유료 API 호출은 하지 않았다.

## 데이터 유형 (화면·인용에 표시)
| 데이터 | 유형 | 내용 |
|---|---|---|
| 장학표 `data/lolypoly/kopo_scholarship_4799.html` | **실제 공개 원문** | kopo.ac.kr 장학 페이지, 2026-11-17 직접 확인 |
| 식단·학사일정·공지 `data/lolypoly/export.json` | 저장소 데이터 | LOLYPOLY@afe70e2 fixture(공식 홈페이지 2026-11-02 수집본)를 LOLYPOLY 자체 수집 코드로 **임시 테스트 DB**에 적재해 공개 필드만 export. 운영 DB 접속 없음. 공지는 본문 필드가 없어 제목만 있음 |
| MARU 장소·코스 `data/maru/*.json` | 저장소 데이터 | ari@a3a5f0f. 공식 출처 재검증 전 앱 데이터 |
| 경복궁 근정전 월대 출입 제한 공지 `data/maru/royal_notices/` | **실제 공개 원문** | 궁능유적본부 공지. 클라우드 환경에서는 접속이 끊겨 주상 PC에서 `scripts/fetch_royal_notice.py`로 수집(2026-11-18). 적용 기간 2026-09-02~10-31 |
| MARU 식사시간 | **합성** | 프로젝트 간 이름 겹침 시험용. 제목에 `[합성 테스트 데이터]` 표시. (v0.2.1까지 쓰던 합성 "특별 개방" 공지는 실제 공지로 대체됨) |
| 도서관 `data/domains/campus_library.json` | 합성 | 세 번째 도메인 등록 확인용 |

계정·익명 커뮤니티·사진·택시방·학생 의견·버스는 적재하지 않는다(어댑터 allowlist 밖 → 거부, 테스트로 확인).

## 구조
```
src/ragcore/  config · models · textnorm(한글 정규화) · chunking · embedding(fake/e5-onnx) · store(PostgreSQL+pgvector)
              ingest(멱등 적재) · retrieval(키워드/벡터/RRF) · adapter(계약) · generation(fake/Ollama) · citations(검증)
              engine(라우팅·보류·결합) · api(FastAPI) · cli · registry
adapters/     lolypoly/ · maru/(+ ari_baseline: 기존 scoreAriTextMatch 이식)
data/         원본 사본(유형 위 표)        eval/  questions.jsonl(37문항) · run_eval.py
examples/     django_lolypoly/ · ari_maru/ · maru-static/      reports/  평가·시연 기록
```
처리 흐름: 질문 → 어댑터 규칙으로 **정형 조회 / 문서 검색 / 복합 / 되묻기** 라우팅 → (문서) 범위·공개·적용 기간 필터 후 키워드와 벡터를 독립 실행, 각 상위 10을 RRF(1/(60+순위))로 결합 → 자격 필터(제목만·시점) → 상위 4조각만 모델에 전달 → 모델이 주장별 인용 ID·발췌를 JSON으로 반환 → 서버가 ID·발췌 원문 포함·날짜/숫자 대조·질문 되풀이·기간 모순을 검사해 통과한 주장만 답변 → URL·제목은 서버가 원본 메타데이터로 채움.

## 재현 명령
요구: Docker, Python 3.12+(검증은 3.13.18), CPU 4코어·RAM 8GB 이상 권장. GPU 불필요.
```bash
cp .env.example .env
docker compose up -d db
python -m venv .venv && .venv/bin/pip install -r requirements.lock
```
```bash
.venv/bin/python scripts/fetch_e5.py            # e5-small ONNX 470MB, 리비전 고정 + sha256 대조
docker compose --profile llm up -d ollama && docker compose exec ollama ollama pull qwen2.5:3b   # 약 1.9GB
```
```bash
export PYTHONPATH=src:.
.venv/bin/python -m ragcore.cli ingest                                  # 적재(반복 실행해도 중복 없음)
.venv/bin/python -m ragcore.cli ask --project lolypoly --as-of 2026-11-10T12:00 "오늘 점심 뭐야?"
.venv/bin/python -m ragcore.cli eval --generate                         # 검색 비교 + 전체 응답 평가
.venv/bin/python -m pytest -q                                           # fake 모델 + 실제 pgvector
.venv/bin/uvicorn ragcore.api:app --host 127.0.0.1 --port 8088          # API (로컬 바인딩)
.venv/bin/python scripts/demo.py                                        # 3분 시연
```
모델 없이 CI처럼 돌리려면 `RAG_EMBEDDER=fake RAG_GENERATOR=fake`. LOLYPOLY export 재생성: `scripts/export_lolypoly.py`(LOLYPOLY `requirements.txt`로 만든 별도 venv). Ari 이식 일치 확인: `scripts/check_ari_parity.py --app-js <ari>/app.js`.

**Supabase 별도 DB**: `DATABASE_URL`만 Supabase 연결 문자열로 바꾸면 같은 `sql/schema.sql`이 적용된다(pgvector 확장 필요). 트랜잭션 풀러(포트 6543)면 prepared statement를 자동으로 끈다. 이번 세션에서 Supabase에 실제로 연결하지는 않았다.

제약: e5 모델 다운로드 470MB, qwen2.5:3b 1.9GB(실행 중 메모리 약 2.4GB). 4코어 CPU에서 생성 1회는 약 15~70초 걸린다. 정형 조회와 보류 응답은 모델을 부르지 않아 수 ms 안에 끝난다.

## API 계약
- `POST /v1/chat` — 헤더 `Authorization: Bearer <앱 키>`. 서버가 `RAG_APP_KEYS`로 프로젝트 범위를 정한다. 본문 `{question, language?, context?}`. 범위 필드(`project` 등)를 넣으면 422로 거부한다.
- `POST /v1/public/chat` — 정적 웹용 공개 중계. `RAG_PUBLIC_PROJECT`(maru) 하나에만 묶이고, CORS는 허용한 Origin만 통과한다. IP당 분당 20회로 제한한다.
- `GET /health` — DB, 임베딩, 생성 모델 준비 상태.
- 응답 `{status, route, answer, citations[{source_id,title,url,quote,locator,as_of,source_type,note}], as_of, request_id}`. 상태는 `answered | partial | insufficient_evidence | clarification_needed | unavailable` 중 하나야.
- 로그에는 request_id·경로·상태·지연·모델·호출 수·조각 ID·오류 종류만 남는다. 질문 원문과 키는 남기지 않는다(테스트로 확인).
- `reference_time`은 평가·데모용이고 `RAG_ALLOW_REFERENCE_TIME=1`일 때만 받는다.

## 두 서비스 연결 예제 (로컬 연결까지 확인, 운영 반영 아님)
| 예제 | 실행 확인 | 한계 |
|---|---|---|
| `examples/django_lolypoly/rag_client.py` (표준 라이브러리, 서버 측 키) | LOLYPOLY와 같은 Django 5.2.19에서 RequestFactory로 view 호출 → 200·answered. 키 오류(401)와 연결 장애를 다른 문구로 구분 | LOLYPOLY 저장소에는 넣지 않았다. 운영 반영 시 URL·키 관리, 타임아웃 UX, Render 배포 네트워크를 따로 결정해야 한다 |
| `examples/ari_maru/ari-rag-bridge.js` | node에서 Ari `buildAriContext()` 모양의 객체로 호출. `ranking.topRoutes` 순서가 응답 인용 순서에 그대로 유지됨 | ari `app.js`는 수정하지 않았다. 장애 시 `fallbackAriReply`는 "로컬 안내(근거 검색 답변 아님)" 표시를 붙여 쓰도록 안내만 했다 |
| `examples/maru-static/index.html` | Playwright로 390px 화면에서 실제 호출·렌더링, 가로 넘침 없음 (`reports/maru-static-demo.png`) | 공개 중계 엔드포인트만 쓴다. 공개 배포 시 HTTPS·도메인·남용 방지 정책이 따로 필요하다 |

## 테스트 (2026-11-17 실행)
`pytest -q` → **33 passed** (단위 12 + 실제 PostgreSQL/pgvector 통합 21, fake 임베딩·생성). GitHub Actions(lovesome0405/chatbot)에서도 같은 테스트가 통과했다.
판정 가능한 필수 조건은 모두 자동 테스트로 확인했다:

| 필수 조건 | 테스트 |
|---|---|
| 두 어댑터 정상 응답 | test_meal_*, test_no_cross_project_evidence, test_ari_ranking_order_preserved |
| 다른 프로젝트 근거 노출 0 | test_no_cross_project_evidence, test_api_scope_and_contract |
| 없는 인용 ID 반환 0 | test_bad_citation_ids_never_returned |
| 반복 적재 중복 0 | test_repeat_ingest_no_duplicates |
| 교체·삭제 뒤 구버전 조각 노출 0 | test_replaced_document_old_chunks_not_exposed, test_delete_only_when_collection_complete, test_private_transition_removed, test_interrupted_sync_is_safe_to_retry |
| 빈 식단 / 없는 식단 구분 | test_meal_present_empty_missing_are_distinct |
| 기간 만료·제목만 공지로 세부 답변 0 | test_expired_notice_not_used_for_answer, test_title_only_notice_returns_link_not_details |

뮤테이션 점검: 기간 필터를 제거하면 2개 테스트, 인용 ID 검사를 제거하면 2개 테스트가 실패하는 것을 확인했다(원복 후 다시 전부 통과). fake 테스트 통과는 제어 흐름 검증일 뿐이고, 검색 품질 수치가 아니다.

## 평가 (실제 e5 + 실제 pgvector + 실제 qwen2.5:3b)
상세: [reports/EVAL.md](reports/EVAL.md). 원본 JSON과 사람 검토 시트(`*.review.csv`)도 같은 폴더에 있다.

검색 비교(같은 자료·같은 질문, 원본 ID 기준, 상위 3개). 대상은 기대 출처가 있는 문서 질문 21개야.

| 방식 | Hit@3 | 비고 |
|---|---|---|
| 키워드(한글 정규화 + 'simple' FTS) | 21/21 | 평균 2ms |
| 벡터(e5-small, pgvector 정확 검색) | 19/21 | 영어 질문 2건(L14, M07) 실패 |
| RRF(k=60, 각 상위 10) | 21/21 | **이 데이터에서는 키워드보다 낫지 않음** |
| 기존 Ari `scoreAriTextMatch` (MARU, Ari 코퍼스 범위 8문항) | 6/8 | 엔진은 같은 8문항에서 8/8 |

장학표의 기대 행이 상위 3조각 안에 든 비율은 키워드 5/5, 벡터 4/5, RRF 5/5야.

전체 응답(37문항: 롤리폴리 19, MARU 17, 도서관 1. 최종 코드로 run5 실행):

| 지표 | 결과 |
|---|---|
| 경로 일치 / 상태 일치 | 37/37 / 30/37 |
| 정형 조회 정답 | 7/7 |
| 근거 부족·되묻기 보류 적중 | 9/9 |
| 답할 수 있는데 보류 | 7/26 (모델이 주장 없이 보류 3: L19·M05·M12 / 원문에 없는 발췌라 서버 폐기 2: M01·M04 / 질문 되풀이 폐기 1: L09 / 기간 모순 폐기 1: M07) |
| 다른 프로젝트 근거 노출 / 반환된 없는 인용 ID | 0 / 0 |
| 제목만·기간 만료 공지로 세부 답변 | 0 |
| 영어 질문 → 영어 답변 | 1/2 |
| 모델 호출 | 23회(정형 조회와 보류는 0회) |
| 지연 | 평균 19.8초, p95 45.9초(4코어 CPU, GPU 없음) |

인용의 의미 일치는 자동으로 판정할 수 없어서 따로 표시했어. 최종 실행의 생성 주장 16개는 Claude 1차 의견으로 모두 인용과 일치하지만, 5개는 답이 불완전해. 이전 회차에서는 자동 검증을 통과한 의미 오류가 실제로 나왔어(EVAL.md 4절). 사람 검토는 아직 하지 않았어.
회차별 변경과 수치는 [reports/HISTORY.md](reports/HISTORY.md), 생성 형식 실험은 [reports/LLM-FORMAT.md](reports/LLM-FORMAT.md)에 있어.

### 확대 평가 v2 (63문항, 3B vs 7B)
결과를 보기 전에 질문 26개를 추가해 고정했다. 새 질문과 영어 질문에서는 RRF가 키워드·벡터 단독보다 높았다(영어 Hit@3 12/14 vs 9/14).
7B는 3B보다 상태 일치(53 vs 48/63), 과잉 보류(10 vs 15/48), 영어 답변(8/8)이 나았다. 대신 지연이 약 2배다(평균 44초).
두 모델 모두 자동 검증을 통과한 의미 오류가 있다. 요약은 [reports/v2/SUMMARY.md](reports/v2/SUMMARY.md), 사람 검토 시트는 [reports/v2/HUMAN-REVIEW.csv](reports/v2/HUMAN-REVIEW.csv)에 있다.

## 3분 시연 순서 (`scripts/demo.py`, 기록: `reports/demo-transcript.txt`)
1. **오늘 점심** (롤리폴리 키, 기준 2026-11-10): 정형 조회로 중식 레코드를 그대로 반환. 모델 호출 0회. 출처 유형 "저장소 데이터"
2. **장학표 한 행 인용**: "학과수석 입학자는 장학금 얼마나 받아?" → `장학제도 표 > 행 2` 인용, 1년간 교육비 전액면제. 출처 유형 "실제 공개 원문"
3. **같은 서버로 영어 문화 질문** (MARU 키): "Tell me about Jongmyo Shrine" → 한국어 원문 근거와 출처 링크. ⚠ 3B 모델이 이 질문에 한국어로 답했다(아래 한계 참고)
4. **낡은 공지에 답변 보류** (기준 2026-11-17): 실제 공지 "경복궁 근정전 월대 출입 제한"(기간 2026-09-02~10-31)은 "기간 종료"로만 표시하고 지금 올라갈 수 있는지는 확정하지 않음

화면 첫 줄에 데이터 유형(실제 원문/저장소/합성)을 표시한다.

## 한계와 미실행 항목
| 항목 | 상태 | 원인 / 재현 |
|---|---|---|
| 국가유산청 궁능유적본부 공지 원문 | **미확인** → 합성 fixture로 대체 | 이 컨테이너에서 TLS 핸드셰이크 중 상대 서버가 연결을 끊음(프록시 CONNECT 200 후 `Connection reset by peer`, 재시도 TLS1.2/1.3 동일). 재현: `curl -v "https://royal.khs.go.kr/ROYAL/contents/R403000000.do?id=20260830151817711582&schBdcode=gbg&schM=view"` |
| 기존 Ari `fallbackAriReply`/`askAri` 응답 비교 | 미실행 | 브라우저 DOM·i18n·localStorage 의존이라 서버에서 그대로 실행하지 못함. 검색 단계(`scoreAriTextMatch`)만 이식해 app.js 원본과 700케이스 일치 확인 후 비교 |
| 사람 검토(인용의 의미 일치) | 미실행 | 자동 검증은 ID·발췌 포함·값 대조만 보장. `reports/*.review.csv`의 사람 판정 칸이 비어 있음. Claude 1차 의견은 EVAL.md에 따로 표시(사람 검토 아님) |
| 영어 질문 → 영어 답변 | 부분 실패 | 3B 모델이 한국어 원문을 그대로 답으로 옮기는 경우가 있음(종묘 질문). 서버에서 막지 않고 지표로 기록 |
| qwen2.5:7b 전체 평가 | 미실행 | 시간 제약(문항당 50~95초). 3문항 비교만 `reports/LLM-FORMAT.md` |
| Supabase 별도 DB 연결 | 미실행 | 설정과 풀러 대응만 있음. 실제 프로젝트 생성·연결은 외부 서비스 변경이라 하지 않음. 재현: `.env`의 `DATABASE_URL` 교체 후 `python -m ragcore.cli ingest` |
| GitHub Actions CI | 미실행 | 원격 저장소가 없어 `.github/workflows/ci.yml`은 초안. 같은 명령(`pytest -q`)은 로컬 pgvector로 통과 |
| 운영 반영(LOLYPOLY·MARU 사이트) | 범위 밖 | 연결 예제와 로컬 호출만 확인. 운영 배포·원격 푸시는 별도 작업 |
| Windows·학교 PC 실행 | 미검증 | 이 결과는 Linux 컨테이너(4 CPU) 기준 |
| 원본 데이터 라이선스 | 확인 필요 | LOLYPOLY·ari 저장소에 LICENSE 없음. 로컬 데모용 사본이며 재배포 전 소유자 확인 |

라우팅 규칙과 별칭 사전은 이번 평가 질문을 보며 만든 소규모 규칙이야. 새 질문 유형에서는 경로 정확도가 떨어질 수 있어. 평가셋 37문항도 작아서, 수치는 이 데이터 안에서의 관찰로만 읽어야 해.
