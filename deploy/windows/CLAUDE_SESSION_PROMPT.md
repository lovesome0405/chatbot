# 학교 PC에서 Claude로 엔진 설치하기

학교 PC에서 Claude(Claude 데스크톱 앱의 Code 탭 또는 Claude Code)를 켜고, 새 세션에 아래 "붙여 넣을 요청"을 그대로 넣는다.

## 그 전에 사람이 할 일 (5분)
1. 학교 PC에 **Git for Windows**가 있는지 확인한다(Claude Code가 Windows에서 Git Bash를 쓴다). 없으면 https://git-scm.com/download/win 에서 설치.
2. Claude 데스크톱 앱(또는 Claude Code)에 로그인한다.
3. 작업 폴더를 **`D:\lolypoly`** 로 연다(롤리폴리가 `D:\lolypoly\app`에 설치된 기준. 위치가 다르면 요청 안의 경로를 바꾼다).
4. GitHub 로그인이 필요할 수 있다(`lovesome0405/chatbot`이 비공개면 git이 브라우저 로그인을 띄운다).
   자격 증명 관리자에 GitHub 계정이 여러 개면 `https://lovesome0405@github.com/lovesome0405/chatbot` 로 clone 한다(README 7절 ①).
5. **관리자 PowerShell이 필요한 단계가 두 개 있다**(2026-11-20 확인): 엔진 작업 등록(`install_tasks.ps1`)과 롤리폴리 업데이트(`update.ps1 -Branch main`, 학교 PC가 3fd5417 이전이면).
   Claude가 물으면 사람이 직접 실행하거나 UAC 창을 승인한다.

## 붙여 넣을 요청

```text
학교 PC(Windows)에 RAG 엔진을 설치해줘. 롤리폴리가 이미 이 PC에서 돌고 있어.

기준 문서: https://github.com/lovesome0405/chatbot 의 main 브랜치 deploy/windows/README.md.
먼저 D:\lolypoly\rag\chatbot 에 clone 하고 README를 끝까지 읽은 뒤, 그 순서대로 진행해.
롤리폴리 저장소 D:\lolypoly\app 의 AGENTS.md 와 docs/PROGRESS.md 도 읽어(이 PC의 제약: Docker·WSL 불가).

지킬 것
- 각 단계마다 실제로 실행하고 결과를 확인한 뒤 다음으로 넘어가. 실패하면 원인을 찾아 고치고, 고친 내용을 기록해.
- README의 경로·명령은 Linux에서만 확인한 거라 Windows에서 틀릴 수 있어. 다르면 실제 동작하는 쪽으로 고치고,
  chatbot 저장소의 deploy/windows/ 문서·스크립트에 반영해(새 브랜치 claude/school-pc-install 에 커밋·푸시, main 병합은 내가 따로 말할게).
- 관리자 권한이 필요한 작업, 방화벽·공유기·학교망 설정, 유료 서비스, 외부 공개(터널 경로 추가 포함)는 하기 전에 나한테 물어봐.
- 롤리폴리의 기존 DB·.env·작업 스케줄러 작업은 지우거나 덮어쓰지 마. 롤리폴리 .env 에는 두 줄(LOLYPOLY_RAG_API_URL, LOLYPOLY_RAG_APP_KEY)만 추가하고, 추가 전 백업해.
- 앱 키는 무작위로 만들어 엔진 .env 와 롤리폴리 .env 에만 넣어. 채팅·로그·Git에 값을 쓰지 마.
- 모델은 상업 이용 제한 없는 Apache 2.0 만: ollama pull qwen2.5:1.5b, ollama pull qwen3:4b.

완료 기준
1. 작업 스케줄러에 RAG-DB, RAG-API, RAG-Refresh 등록, PC 재부팅 후에도 http://127.0.0.1:8088/health 가 응답.
2. RAG-Refresh 한 번 수동 실행 → 로그에 export_rag·ingest·warm 이 모두 종료 코드 0.
3. 롤리폴리 식단 화면에 안내 칸이 보이고 "11월 10일 점심 뭐야?" 같은 질문에 답이 나옴(브라우저로 확인).
4. 63문항 측정: python -m ragcore.cli eval --generate --out reports\school-pc.json
   → 10초 이내 개수, 평균/p95/최대 지연, 상태 일치 수를 표로 보고. 클라우드 4코어 결과(reports/v0.5.0/SPEED.md: 63/63, p95 8.0초)와 비교.
5. 보고는 한국어로: 실제로 한 것 / 실패하고 고친 것 / 미확인 / 내가 할 일.
```

## 참고
- 이 요청은 MARU(외국인용) 공개 주소는 다루지 않는다. 터널 경로 추가는 따로 결정한다(`README.md` 6절).
- 미리 만든 답 39개 검토(`cache-export` → 판정 → `cache-import`)는 설치와 별개로 나중에 해도 된다.
