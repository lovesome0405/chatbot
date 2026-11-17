# 평가 결과 (2026-11-17T18:57:42+09:00)

- 질문 37개: campus-library 1, lolypoly 19, maru 17
- 임베딩 `multilingual-e5-small@614241f`, 생성 `ollama:qwen2.5:3b`, 분할 `v1-2026-11-17`, 시작값 {'keyword_top_n': 10, 'vector_top_n': 10, 'rrf_k': 60, 'final_top_k': 4}, 벡터 최소 유사도 0.8
- 측정 환경: Python 3.13.18, 4 CPU(x86_64), GPU 없음, Linux-6.18.44-fc-v553-x86_64-with-glibc2.39. 지연은 이 컨테이너의 CPU 추론 기준
- 원본 JSON·사람 검토 시트(CSV)가 같은 폴더에 있다. RRF 점수는 정답 확률이 아니다.

## 1. 검색 비교 (같은 자료·같은 질문, 원본 ID 기준 Hit@3)

정의: Hit@3 = 상위 3개 원본 ID(조각을 원본 단위로 접음) 중 기대 출처가 하나라도 있으면 1. 대상: 기대 경로=document, 기대 출처 있음, 기간 만료 의도 제외

| 방식 | Hit@3 | 평균 지연(ms) |
|---|---|---|
| keyword | 21/21 | 2.1 |
| vector | 19/21 | 8.6 |
| RRF(k=60) | 21/21 | 8.6 |
| 기존 Ari scoreAriTextMatch (MARU만) | 6/11 | 0.4 |

- MARU 질문만(분모 11): keyword 11, vector 10, RRF 11, Ari 6
- Ari 코퍼스(장소·코스)에 정답이 있는 질문만(분모 8): keyword 8, vector 8, RRF 8, Ari 6
- 장학표 기대 행 Hit@3(분모 5): keyword 5, vector 4, RRF 5

검색 실패 사례:

- L14 기대 ['kopo-4799-scholarship']: vector → ['notice:782660', 'notice:784161', 'notice:787646']
- M02 기대 ['place:gyeongbokgung-palace']: ari_baseline → 결과 없음
- M07 기대 ['synthetic:royal-gbg-special-opening']: vector → ['place:gyeongbokgung-palace', 'place:changdeokgung-palace', 'place:changgyeonggung-palace']; ari_baseline → ['place:gyeongbokgung-palace', 'course:palace-history-course', 'course:insadong-craft-course']
- M09 기대 ['synthetic:royal-gbg-special-opening']: ari_baseline → ['course:palace-history-course', 'place:gyeongbokgung-palace', 'place:deoksugung-palace']
- M12 기대 ['synthetic:maru-tour-meal-time']: ari_baseline → 결과 없음
- M16 기대 ['place:insadong', 'course:insadong-craft-course']: ari_baseline → ['place:deoksugung-palace']

## 2. 전체 응답 (hybrid + 생성 + 인용 검증)

| 지표 | 값 |
|---|---|
| 경로 일치 | 37/37 (100%) |
| 상태 일치 | 30/37 (81%) |
| 정형 조회 정답(상태+핵심값) | 7/7 (100%) |
| 근거 부족·되묻기 보류 적중 | 9/9 (100%) |
| 핵심 사실 포함(자동 대리지표) | 19/21 (90%) |
| 답변 시 기대 출처 인용 | 21/21 (100%) |
| 영어 질문 → 영어 답변 | 1/2 (50%) |
| 답할 수 있는데 보류 | 7/26 |
| 다른 프로젝트 근거 노출 | 0 |
| 반환된 인용 중 없는 ID | 0 |
| 모델이 낸 없는 인용 ID(서버가 폐기) | 0 |
| 원문에 없는 발췌(서버가 폐기) | 6 |
| 근거와 다른 날짜·숫자(서버가 폐기) | 0 |
| 제목만 있는/기간 만료 공지로 세부 답변 | 0 |
| 모델 호출 수(37문항 합계) | 23 |
| 지연 ms (평균/p50/p95/최대) | 19783.9 / 22015.5 / 45903.1 / 70175.0 |

### 실패·불일치 사례 (그대로 기록)

- **L07** 기대 ['answered'] → answered (경로 document, 핵심사실 False): 직전학기 성적우수자는 교내 성적우수 장학금을 받을 수 있습니다. [1]
- **L09** 기대 ['answered'] → insufficient_evidence (경로 document, 핵심사실 True): 확인된 자료에서 찾지 못했어. [1][2][3]
- **L17** 기대 ['answered'] → answered (경로 composite, 핵심사실 False): 2026-11-10(화) 중식 메뉴: 상하이파스타, 미니후리카게밥, 단호박스프, 바삭에그카츠/타르타르소스, 사과무생채, 김치/보리과자 [1] / 성적우수 장학금은 학과수석 입학자에게 교육비 전액을 면제해준다. [2]
- **L19** 기대 ['answered'] → insufficient_evidence (경로 document, 핵심사실 True): 확인된 자료에서 찾지 못했어. [1][2][3]
- **M01** 기대 ['answered'] → insufficient_evidence (경로 document, 핵심사실 False): I couldn't find this in the verified sources. [1][2][3]
- **M04** 기대 ['answered'] → insufficient_evidence (경로 document, 핵심사실 True): I couldn't find this in the verified sources. [1][2][3]
- **M05** 기대 ['answered'] → insufficient_evidence (경로 document, 핵심사실 True): 확인된 자료에서 찾지 못했어. [1][2][3]
- **M07** 기대 ['answered'] → insufficient_evidence (경로 document, 핵심사실 True): I couldn't find this in the verified sources. [1][2][3]
- **M12** 기대 ['answered'] → insufficient_evidence (경로 document, 핵심사실 True): 확인된 자료에서 찾지 못했어. [1][2][3]

서버 검증에서 버린 모델 주장: L09 ['echoes_question'], M01 ['quote_not_in_source'], M02 ['quote_not_in_source', 'quote_not_in_source'], M03 ['quote_not_in_source', 'quote_not_in_source'], M04 ['quote_not_in_source'], M07 ['contradicts_valid_period']

## 3. 참고: fake 생성기(CI용) 같은 질문 결과

제어 흐름 확인용이며 답변 품질 수치가 아니다.

- 경로 37/37 (100%), 상태 32/37 (86%), 정형 7/7 (100%), 보류 7/9 (78%), 누출 0, 없는 ID 0

## 4. 인용 의미 검토 — Claude 1차 의견 (사람 검토 아님)

자동 검증은 "인용 ID가 전달한 근거에 있음 + 발췌가 원문에 그대로 있음 + 날짜·숫자 일치"만 보장한다. 아래는 최종 실행의 모델 생성 주장 16개를 Claude가 원문과 대조한 **1차 의견**이야. 사람 판정은 `eval-…qwen2.5-3b.review.csv`의 빈 칸에 채운다.

| 판단 | 문항 |
|---|---|
| 인용이 주장을 지지하고 답이 완결됨 | L06, L14, M02, M03, M09, M16, M17, C01, M14(내용) |
| 지지하지만 답이 불완전함 | L07(혜택 '1개학기 교육비 전액면제' 누락), L08·L17('1년간' 누락), L16(점심 시작 시각만 답하고 종료 13:20 누락), M13(궁궐 이름 창덕궁을 주장에 쓰지 않음) |
| 요청 언어와 다름 | M14: 영어 질문에 한국어 원문 문장을 그대로 답함 |
| 지지하지 않음 | 최종 실행에서는 없음 |

이전 회차와 별도 확인에서는 **자동 검증을 통과한 의미 오류**가 실제로 나왔어:
- run2 M05: 주장은 '국립고궁박물관'을 말하는데 인용은 경복궁 문단이었음
- 원본당 상한 2 확인 실행 M17: 코스 순서를 거꾸로 말함(경복궁 → 국립고궁박물관)
- qwen2.5:7b 영어 장학 질문: 다른 행(이사장 장학금, 2년간)을 인용함

이 오류들은 자동 지표만으로는 걸러지지 않아. 그래서 사람 검토를 남은 확인 항목으로 둬.

## 5. 기존 방식과 비교한 업무 질문 (관찰 범위 안에서)

| 업무 질문 | 기존 방식 | 이번 엔진(실측) | 판정 |
|---|---|---|---|
| "오늘 점심 뭐야?" | 롤리폴리 식단 화면에서 주간 표를 직접 찾음(질의 기능 없음) | 날짜·끼니 레코드를 그대로 반환(L01–L04 4/4). 빈 식단과 레코드 없음을 구분하고, 다른 날짜로 대신 답하지 않음. 모델 호출 0회, 수 ms | 기능 추가. 수치 비교 대상 없음 |
| 장학 자격·혜택 | 앱에 장학 정보 없음. 학교 페이지 표를 직접 읽음 | 기대 행 Hit@3 5/5. 답변 시 해당 행을 locator와 함께 인용. 단 3B 답변 일부가 '1년간' 등을 빠뜨림 | 근거 제시는 개선. 답 완결성은 부분적 |
| 본문 없는 공지의 세부 질문 | 제목 목록과 링크 | 세부 답변 0건. "제목만 있음" 표시와 원문 링크 반환(L10·L11) | 잘못된 단정 방지 |
| MARU 장소·코스 찾기 | Ari `scoreAriTextMatch` 부분 문자열 점수 | 같은 데이터·같은 원본 ID 기준 Hit@3 **Ari 6/8 → 엔진 8/8**(키워드·RRF 모두). Ari는 조사가 붙은 '경복궁은', '인사동에서'에서 0건이거나 엉뚱한 결과 | 검색 개선(분모 8, 작음) |
| 기간·가격 질문 | Ari 로컬 응답 경로는 이번에 실행 못 함(브라우저 의존) | 기간 만료 공지 → 보류(M08). 입장료 → 보류(M10). 기간 안 날짜 → 답변(M09)과 서버 계산 기간 문장. 영어 기간 질문(M07)은 모델 오답을 서버가 버려 보류 | 엔진 쪽만 측정 |
| 키워드 vs 벡터 vs RRF | — | Hit@3 21/21, 19/21, 21/21. 이 데이터에서는 RRF가 키워드보다 낫지 않았음. 벡터 단독은 영어 질문 2건(L14·M07)에서 실패 | 하이브리드 이점 미확인 |
