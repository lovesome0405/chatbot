# 생성 모델 비교 (63문항, 임베딩 multilingual-e5-small@614241f)

환경: 4 CPU, GPU 없음. 검색 단계는 모델과 무관하게 동일하다.

| 지표 | v0.3.0(재실행) | v0.4.0 실생성 | v0.4.0 실생성+검증규칙 재생 |
|---|---|---|---|
| 경로 일치 | 63/63 | 61/63 | 61/63 |
| 상태 일치 | 57/63 | 55/63 | 56/63 |
| 정형 정답 | 10/10 | 9/10 | 10/10 |
| 보류 적중 | 13/13 | 13/13 | 13/13 |
| 핵심 사실(자동) | 38/44 | 39/42 | 40/43 |
| 기대 출처 인용 | 39/44 | 39/42 | 40/43 |
| 영어→영어 | 11/11 | 8/9 | 9/10 |
| 질문 되풀이 주장 | 0/35 | 0/31 | 0/32 |
| 한국어 주장 해요체 | 3/24 | 2/23 | 2/23 |
| 되풀이 주장을 근거로 보강한 수 | 5 | 4 | 4 |
| 답할 수 있는데 보류 | 6/48 | 8/48 | 7/48 |
| 프로젝트 간 노출 | 0 | 0 | 0 |
| 없는 인용 ID 반환 | 0 | 0 | 0 |
| 제목만·만료 공지 세부 답변 | 0 | 0 | 0 |
| 모델 호출 | 44 | 42 | 42 |
| 지연 평균/p95 (초) | 11.7 / 29.8 | 10.3 / 24.9 | 10.3 / 24.9 |

## 서버가 버린 모델 주장 (사유별)

| 사유 | v0.3.0(재실행) | v0.4.0 실생성 | v0.4.0 실생성+검증규칙 재생 |
|---|---|---|---|
| echo_unsupported | 1 | 2 | 2 |
| echoes_question | 2 | 1 | 1 |
| non_answer | 4 | 4 | 4 |
| quote_not_in_source | 5 | 5 | 5 |
| term_not_in_cited_source | 0 | 1 | 0 |

## 문항별 상태 (기대와 다른 칸에 ✗)

| 문항 | 기대 | v0.3.0(재실행) | v0.4.0 실생성 | v0.4.0 실생성+검증규칙 재생 |
|---|---|---|---|---|
| L04 | insufficient_evidence | insufficient_evidence | insufficient_evidence ✗ | insufficient_evidence |
| L07 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| L09 | answered | insufficient_evidence ✗ | answered | answered |
| M01 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| M05 | answered | answered ✗ | answered ✗ | answered ✗ |
| M14 | answered | answered | insufficient_evidence ✗ | answered |
| N02 | answered | answered ✗ | answered | answered |
| N06 | answered | answered ✗ | answered ✗ | answered ✗ |
| N07 | answered | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N08 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N13 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N16 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N17 | answered | answered ✗ | answered ✗ | answered ✗ |
| N19 | answered | answered ✗ | answered | answered |
| N22 | answered | answered ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |

(모든 모델이 기대대로 처리한 문항은 표에서 생략)

## 원문에 없는 발췌 예시 (원인 분석용)

- [v0.3.0(재실행)] L07: 발췌 “행 3 (교내 / 성적우수 장학금)” ↔ 원문 “[장학제도 표] 구분: 교내 | 종류: 성적우수 장학금 | 수혜자격: 직전학기 학과별 성적우수자 학급당 1명 | 지급액 및 기간: 1개학기 교육비 전액면제 | 비”
- [v0.3.0(재실행)] M01: 발췌 “궁궐 역사 산책 코스 (Royal Palace History Walk)는 조선 왕실 문화와 서울의 역사적 중심지를 자연스럽게 경험할 수 있는 첫 방문자용 대표 코” ↔ 원문 “키워드: Joseon Dynasty — 조선 왕실문화와 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 아니라 의”
- [v0.3.0(재실행)] M02: 발췌 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.” ↔ 원문 “주소: 서울특별시 종로구 사직로 161”
- [v0.3.0(재실행)] M07: 발췌 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토)} 문단 1” ↔ 원문 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토))”
- [v0.4.0 실생성] L07: 발췌 “행 3 (교내 / 성적우수 장학금)” ↔ 원문 “[장학제도 표] 구분: 교내 | 종류: 성적우수 장학금 | 수혜자격: 직전학기 학과별 성적우수자 학급당 1명 | 지급액 및 기간: 1개학기 교육비 전액면제 | 비”
- [v0.4.0 실생성] M01: 발췌 “궁궐 역사 산책 코스 (Royal Palace History Walk)는 조선 왕실 문화와 서울의 역사적 중심지를 자연스럽게 경험할 수 있는 첫 방문자용 대표 코” ↔ 원문 “키워드: Joseon Dynasty — 조선 왕실문화와 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 아니라 의”
- [v0.4.0 실생성] M02: 발췌 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.” ↔ 원문 “주소: 서울특별시 종로구 사직로 161”
- [v0.4.0 실생성] M07: 발췌 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토)} 문단 1” ↔ 원문 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토))”
- [v0.4.0 실생성+검증규칙 재생] L07: 발췌 “행 3 (교내 / 성적우수 장학금)” ↔ 원문 “[장학제도 표] 구분: 교내 | 종류: 성적우수 장학금 | 수혜자격: 직전학기 학과별 성적우수자 학급당 1명 | 지급액 및 기간: 1개학기 교육비 전액면제 | 비”
- [v0.4.0 실생성+검증규칙 재생] M01: 발췌 “궁궐 역사 산책 코스 (Royal Palace History Walk)는 조선 왕실 문화와 서울의 역사적 중심지를 자연스럽게 경험할 수 있는 첫 방문자용 대표 코” ↔ 원문 “키워드: Joseon Dynasty — 조선 왕실문화와 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 아니라 의”
- [v0.4.0 실생성+검증규칙 재생] M02: 발췌 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.” ↔ 원문 “주소: 서울특별시 종로구 사직로 161”
- [v0.4.0 실생성+검증규칙 재생] M07: 발췌 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토)} 문단 1” ↔ 원문 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토))”
