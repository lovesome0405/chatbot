# 출처·라이선스 기록

## 참고만 하고 코드를 복사하지 않은 자료
| 자료 | 참고한 부분 | 비고 |
|---|---|---|
| Supabase Hybrid search 가이드 https://supabase.com/docs/guides/ai/hybrid-search | FTS + pgvector 결과를 RRF(1/(k+rank))로 합치는 구조 | SQL은 새로 작성. Supabase 예제는 SQL 함수 안에서 full outer join으로 합치지만, 이 엔진은 두 검색을 독립 실행하고 Python에서 결합해 방식별 비교·로그를 남긴다 |
| pgvector-python https://github.com/pgvector/pgvector-python | `register_vector(conn)`로 psycopg3에 vector 타입 등록, `<=>` 코사인 거리 | 라이브러리로 사용(MIT). 예제 코드 복사 없음 |
| LangChain langchain-rag SKILL.md | 분할 → 색인 → 검색 → 생성 절차 점검 | LangChain 런타임 미사용 |
| Supabase supabase-postgres-best-practices SKILL.md | 매개변수 바인딩, 필요한 인덱스(GIN, FK 인덱스), identity PK | 스킬 설치 없이 원칙만 반영 |
| GOV.UK Chat evaluation 문서 | 구성요소별 평가(검색·답변·보류 분리), 인용 가능한 범위 | 평가 CLI 구조 참고 |
| AnythingLLM Desktop, Slack Enterprise Search | 문서 넣기 → 첫 답 흐름, 모델 전달 전 권한 제한 | 설계 비교 대상(코드 무관) |

두 SKILL.md는 2026-11-17 git으로 받아 읽었다(복사한 코드 없음, 두 저장소 모두 MIT).
- langchain-ai/langchain-skills: 프롬프트의 `config/skills/langchain-rag/SKILL.md` 경로는 최신 커밋 8883a4a에 없다. 2026-11-15 커밋 f68d40f(구조 개편)에서 빠졌고, 그 직전 버전을 읽었다. Index(Load→Split→Embed→Store) → Retrieve → Generate 단계 구분과 상위 k=4 기본값을 점검 기준으로 썼다. 예제가 쓰는 OpenAI 임베딩·LangChain 런타임은 도입하지 않았다.
- supabase/agent-skills@c9be0e9 `supabase-postgres-best-practices` v1.1.1: `advanced-jsonb-indexing`에 따라 metadata GIN(jsonb_path_ops) 인덱스를 추가했다. `conn-prepared-statements`에 따라 트랜잭션 풀러(6543)에서는 psycopg prepare를 끈다. `advanced-full-text-search`의 tsvector 생성 열과 GIN 구성은 따르되, 예시의 'english' 설정 대신 'simple'과 Python 사전 토큰화(한글 조사·2-gram)를 쓴다. `schema-foreign-key-indexes`(rag_chunk.document_id 인덱스), `lock-short-transactions`(문서 1건 단위 트랜잭션)도 따른다.

## 실행 의존성 (requirements.lock 고정)
psycopg 3.2.12(LGPL-3.0), pgvector-python 0.4.1(MIT), FastAPI 0.121.2(MIT), Starlette 0.49.3(BSD-3), uvicorn 0.38.0(BSD-3), httpx 0.28.1(BSD-3), numpy 2.3.4(BSD-3), pydantic 2.12.4(MIT), onnxruntime 1.23.2(MIT), tokenizers 0.22.1(Apache-2.0), pytest 8.4.2(MIT).
Docker 이미지: pgvector/pgvector:0.8.1-pg17, ollama/ollama:0.12.6.

## 모델
| 모델 | 역할 | 리비전 | 라이선스 |
|---|---|---|---|
| intfloat/multilingual-e5-small (ONNX) | 임베딩 | 614241f622f53c4eeff9890bdc4f31cfecc418b3, model.onnx sha256 ca456c06…8665 | MIT (모델 카드) |
| qwen2.5:3b (Ollama) | 생성(기본) | Ollama digest 357c53fb659c | Qwen RESEARCH LICENSE(3B) — 상업 이용 전 확인 필요 |
| qwen2.5:7b (Ollama) | 생성(비교) | 845dbda0ea48 | Apache-2.0 (Qwen2.5-7B) |

라이선스는 모델 카드 기준 정보를 기록했으며, 운영·상업 이용 전에는 해당 모델 페이지에서 다시 확인한다.

## 데이터
| 데이터 | 유형 | 출처 |
|---|---|---|
| data/lolypoly/export.json | repository_data | chanmini584-ux/LOLYPOLY@afe70e2 `campus/tests/fixtures`(공식 홈페이지 2026-11-02 수집본) → LOLYPOLY 수집 코드로 임시 테스트 DB 적재 후 공개 필드 export |
| data/lolypoly/kopo_scholarship_4799.html | public_original | https://www.kopo.ac.kr/chuncheon/content.do?menu=4799 2026-11-17 직접 확인, 본문 영역만 |
| data/maru/*.json (synthetic 제외) | repository_data | lovesome0405/ari@a3a5f0f |
| data/maru/synthetic_notices.json, data/domains/campus_library.json | synthetic | 이 작업에서 만든 합성 테스트 데이터 |

두 원본 저장소(LOLYPOLY, ari)에는 LICENSE 파일이 없다. 이 저장소의 데이터 사본은 로컬 데모·평가용이며 공개 재배포 전 각 저장소 소유자의 허락을 확인한다.
