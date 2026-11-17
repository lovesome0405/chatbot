# 작업 계획 (2026-11-17, 짧은 기록)

목표: 한국어 대학 생활정보(롤리폴리)와 외국인 대상 서울 전통문화 안내(MARU)에 같은 검색·근거·답변 엔진을 재사용하고, 어떤 질문에서 기존 방식보다 나아졌는지 실제 평가 기록을 남긴다.

| 단계 | 할 일 | 완료 기준 |
|---|---|---|
| 0 | 작업 위치·원본 조사 | 설정 저장소(jusang-ai-stack)와 분리된 `work/rag-engine` 독립 Git. LOLYPOLY@afe70e2, ari@a3a5f0f는 읽기만 함 |
| 1 | 원본 확보 | LOLYPOLY fixture → 자체 수집 코드 + 임시 SQLite 테스트 DB → 공개 필드 export. 장학표 공개 원문 저장. 접근 실패 원문(royal.khs.go.kr)은 합성 표시 |
| 2 | 공통 엔진 | 표준 문서/조각, 멱등 적재, 키워드·벡터·RRF, 라우팅, 인용 검증, 보류, 생성 인터페이스(fake/Ollama) |
| 3 | 어댑터 | lolypoly·maru 코드 어댑터 + 세 번째 도메인 JSON 등록 |
| 4 | 실행 계약 | CLI(ingest/ask/eval), FastAPI(/v1/chat, /v1/public/chat, /health), Docker Compose, .env.example |
| 5 | 테스트 | fake로 제어 흐름 + 실제 pgvector 통합 테스트, 뮤테이션 점검 |
| 6 | 평가 | 고정 질문 37개, 키워드/벡터/RRF/Ari 기준선 Hit@3, 전체 응답 지표(실제 e5 + qwen2.5:3b) |
| 7 | 연결 예제·문서 | Django·Ari 호출 예제 실행 확인, README(명령·결과·한계·3분 시연) |

범위 밖(별도 작업): 운영 배포, 원격 푸시, 유료 API 호출, 기존 앱 DB 이전, 원본 저장소 수정.
