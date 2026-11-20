# 생성 모델 비교 (63문항, 임베딩 multilingual-e5-small@614241f)

환경: 4 CPU, GPU 없음. 검색 단계는 모델과 무관하게 동일하다.

| 지표 | v0.4.0 qwen2.5:3b(비상업) | v0.5.0 qwen2.5:1.5b | v0.5.0 qwen3:4b |
|---|---|---|---|
| 경로 일치 | 61/63 | 46/63 | 46/63 |
| 상태 일치 | 56/63 | 56/63 | 54/63 |
| 정형 정답 | 10/10 | 10/10 | 10/10 |
| 보류 적중 | 13/13 | 13/13 | 13/13 |
| 핵심 사실(자동) | 40/43 | 43/43 | 40/41 |
| 기대 출처 인용 | 40/43 | 40/43 | 39/41 |
| 영어→영어 | 9/10 | 6/10 | 6/10 |
| 질문 되풀이 주장 | 0/32 | 0/17 | 0/16 |
| 한국어 주장 해요체 | 2/23 | 8/13 | 12/12 |
| 되풀이 주장을 근거로 보강한 수 | 4 | 0 | 0 |
| 답할 수 있는데 보류 | 7/48 | 6/48 | 8/48 |
| 프로젝트 간 노출 | 0 | 0 | 0 |
| 없는 인용 ID 반환 | 0 | 0 | 0 |
| 제목만·만료 공지 세부 답변 | 0 | 0 | 0 |
| 모델 호출 | 42 | 26 | 26 |
| 지연 평균/p95 (초) | 10.3 / 24.9 | 2.6 / 8.0 | 3.3 / 8.1 |

## 서버가 버린 모델 주장 (사유별)

| 사유 | v0.4.0 qwen2.5:3b(비상업) | v0.5.0 qwen2.5:1.5b | v0.5.0 qwen3:4b |
|---|---|---|---|
| echo_unsupported | 2 | 1 | 0 |
| echoes_question | 1 | 0 | 0 |
| no_overlap_with_citation | 0 | 1 | 0 |
| non_answer | 4 | 0 | 0 |
| quote_not_in_source | 5 | 3 | 0 |
| topic_not_in_citation | 0 | 2 | 0 |
| value_not_in_cited_source | 0 | 2 | 0 |
| wrong_language | 0 | 5 | 1 |

## 문항별 상태 (기대와 다른 칸에 ✗)

| 문항 | 기대 | v0.4.0 qwen2.5:3b(비상업) | v0.5.0 qwen2.5:1.5b | v0.5.0 qwen3:4b |
|---|---|---|---|---|
| L07 | answered | insufficient_evidence ✗ | answered | answered |
| M01 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| M05 | answered | answered ✗ | answered | answered |
| M17 | partial | partial | insufficient_evidence ✗ | insufficient_evidence ✗ |
| C01 | answered | answered | answered | insufficient_evidence ✗ |
| N02 | answered | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N05 | answered | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N06 | answered | answered ✗ | answered | insufficient_evidence ✗ |
| N07 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N08 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N09 | answered | answered | answered | answered ✗ |
| N13 | answered | insufficient_evidence ✗ | answered | answered |
| N16 | answered | insufficient_evidence ✗ | answered | answered |
| N17 | answered | answered ✗ | answered | answered |
| N22 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ | insufficient_evidence ✗ |

(모든 모델이 기대대로 처리한 문항은 표에서 생략)

## 원문에 없는 발췌 예시 (원인 분석용)

- [v0.4.0 qwen2.5:3b(비상업)] L07: 발췌 “행 3 (교내 / 성적우수 장학금)” ↔ 원문 “[장학제도 표] 구분: 교내 | 종류: 성적우수 장학금 | 수혜자격: 직전학기 학과별 성적우수자 학급당 1명 | 지급액 및 기간: 1개학기 교육비 전액면제 | 비”
- [v0.4.0 qwen2.5:3b(비상업)] M01: 발췌 “궁궐 역사 산책 코스 (Royal Palace History Walk)는 조선 왕실 문화와 서울의 역사적 중심지를 자연스럽게 경험할 수 있는 첫 방문자용 대표 코” ↔ 원문 “키워드: Joseon Dynasty — 조선 왕실문화와 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 아니라 의”
- [v0.4.0 qwen2.5:3b(비상업)] M02: 발췌 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.” ↔ 원문 “주소: 서울특별시 종로구 사직로 161”
- [v0.4.0 qwen2.5:3b(비상업)] M07: 발췌 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토)} 문단 1” ↔ 원문 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토))”
- [v0.5.0 qwen2.5:1.5b] M05: 발췌 “경복궁은 조선 왕실 문화와 서울의 역사적 중심지를 경험할 수 있는 곳입니다.” ↔ 원문 “키워드: Joseon Dynasty — 조선 왕실문화와 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 아니라 의”
- [v0.5.0 qwen2.5:1.5b] M07: 발췌 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토)) 문단 1” ↔ 원문 “경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토))”
- [v0.5.0 qwen2.5:1.5b] M16: 발췌 “인사동 전통공예 코스는 전통 공예를 거리, 상점, 박물관 관점에서 입체적으로 이해하는 체험형 코스입니다.” ↔ 원문 “인사동 전통공예 코스 (Insadong Traditional Craft Course): 전통 공예를 거리, 상점, 박물관 관점에서 입체적으로 이해하는 체험형 코스”
