# CLAUDE.md — ragcore (공통 RAG 엔진)

이 저장소에서 작업하는 Claude/Codex 세션이 먼저 읽는 규칙. 상세 설명은 README.md, 변경 이력은 CHANGELOG.md.

## 무엇인가
- 롤리폴리(캠퍼스 생활정보)와 MARU(전통문화 안내)가 함께 쓰는 검색·근거·답변 엔진. 프로젝트별 규칙은 `adapters/`에 두고, 엔진(`src/ragcore/`)은 프로젝트 이름을 모른다.
- 운영 위치는 롤리폴리 학교 PC(`deploy/windows/`). 앱 저장소(LOLYPOLY, ari)는 이 저장소에서 직접 고치지 않는다.

## 작업 규칙
- 버전: `0.(기능).(수정)`. 버전마다 `claude/next-steps` → `main` PR, PR 제목과 CHANGELOG에 버전을 적는다.
- 평가 수치는 해당 버전 코드로 **실제 실행한 결과만** 적는다. 재생 평가·fake 모델 결과는 그렇다고 표시한다.
- 상태 표기를 섞지 않는다: 소스 반영 / 로컬 검증 / 학교 PC 운영 / 미구현.
- 데이터 유형(실제 공개 원문·저장소 데이터·합성)을 README 표와 인용에 표시한다. 계정·익명 커뮤니티·개인정보는 적재하지 않는다.
- 생성 모델은 상업 이용 제한 없는 라이선스(Apache 2.0 등)만 기본값으로 쓴다. 유료 API는 호출하지 않는다.
- 커밋·push·병합·운영 반영은 주상이 요청할 때만 한다.

## 비밀값
- 실제 키·비밀번호는 `.env`에만 둔다(Git 제외). 예시 파일에는 `change-me`·`<긴 무작위 값>` 같은 자리표시만 쓴다.
- 이 저장소는 공개 저장소다. 운영 `RAG_APP_KEYS`는 예시 값과 달라야 하고, 키·질문 원문을 로그·보고서·커밋에 남기지 않는다.
- 공개 경로는 `/v1/public/chat`만 연다. `/v1/chat`(앱 키 경로)은 로컬 바인딩으로 둔다.

## 확인 명령
```bash
export PYTHONPATH=src:.
RAG_EMBEDDER=fake RAG_GENERATOR=fake .venv/bin/python -m pytest -q   # fake 모델 + 실제 pgvector(docker compose up -d db)
```
