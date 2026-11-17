# 생성 모델 비교 (63문항, 임베딩 multilingual-e5-small@614241f)

환경: 4 CPU, GPU 없음. 검색 단계는 모델과 무관하게 동일하다.

| 지표 | fake-extractive-v1 | ollama:qwen2.5:3b |
|---|---|---|
| 경로 일치 | 63/63 | 63/63 |
| 상태 일치 | 52/63 | 48/63 |
| 정형 정답 | 10/10 | 10/10 |
| 보류 적중 | 10/13 | 13/13 |
| 핵심 사실(자동) | 28/42 | 32/35 |
| 기대 출처 인용 | 36/42 | 34/35 |
| 영어→영어 | 4/8 | 5/6 |
| 답할 수 있는데 보류 | 8/48 | 15/48 |
| 프로젝트 간 노출 | 0 | 0 |
| 없는 인용 ID 반환 | 0 | 0 |
| 제목만·만료 공지 세부 답변 | 0 | 0 |
| 모델 호출 | 43 | 43 |
| 지연 평균/p95 (초) | 0.0 / 0.0 | 22.3 / 46.2 |

## 서버가 버린 모델 주장 (사유별)

| 사유 | fake-extractive-v1 | ollama:qwen2.5:3b |
|---|---|---|
| contradicts_valid_period | 1 | 1 |
| echoes_question | 1 | 2 |
| quote_not_in_source | 0 | 8 |

## 문항별 상태 (기대와 다른 칸에 ✗)

| 문항 | 기대 | fake-extractive-v1 | ollama:qwen2.5:3b |
|---|---|---|---|
| L06 | answered | answered ✗ | answered |
| L07 | answered | answered ✗ | answered ✗ |
| L08 | answered | answered ✗ | answered |
| L09 | answered | answered ✗ | insufficient_evidence ✗ |
| L14 | answered | insufficient_evidence ✗ | answered |
| L15 | insufficient_evidence | answered ✗ | insufficient_evidence |
| L16 | answered | answered ✗ | answered |
| L17 | answered | answered ✗ | answered ✗ |
| L19 | answered | answered ✗ | insufficient_evidence ✗ |
| M01 | answered | answered ✗ | insufficient_evidence ✗ |
| M04 | answered | answered | insufficient_evidence ✗ |
| M05 | answered | answered | insufficient_evidence ✗ |
| M07 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| M12 | answered | answered | insufficient_evidence ✗ |
| M15 | insufficient_evidence | answered ✗ | insufficient_evidence |
| C01 | answered | insufficient_evidence ✗ | answered |
| N02 | answered | answered ✗ | answered ✗ |
| N05 | answered | insufficient_evidence ✗ | answered |
| N06 | answered | answered ✗ | insufficient_evidence ✗ |
| N07 | answered | answered | insufficient_evidence ✗ |
| N09 | answered | answered ✗ | answered |
| N12 | insufficient_evidence | answered ✗ | insufficient_evidence |
| N13 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N16 | answered | answered ✗ | insufficient_evidence ✗ |
| N17 | answered | answered ✗ | insufficient_evidence ✗ |
| N18 | answered | answered ✗ | answered |
| N19 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N22 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N24 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |

(모든 모델이 기대대로 처리한 문항은 표에서 생략)

## 원문에 없는 발췌 예시 (원인 분석용)

- [ollama:qwen2.5:3b] M01: 발췌 “'궁궐 역사 산책 코스 > 문단 5': 키워드: 조선 왕실문화, 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 ” ↔ 원문 “키워드: Joseon Dynasty — 조선 왕실문화와 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 아니라 의”
- [ollama:qwen2.5:3b] M02: 발췌 “의미: 서울특별시 종로구 사직로 161” ↔ 원문 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.”
- [ollama:qwen2.5:3b] M02: 발췌 “의미: 서울특별시 종로구 사직로 161” ↔ 원문 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.”
- [ollama:qwen2.5:3b] M03: 발췌 “비 오는 날 실내 전통문화 코스 (Rainy-Day Indoor Traditional Culture Course): 비가 오거나 더운 날에도 실내 전시와 짧은 동” ↔ 원문 “추천 이유: 우천 시 이동 부담을 줄이면서 왕실문화, 도시사, 한옥 생활문화를 끊기지 않는 해설 흐름으로 연결합니다.”
