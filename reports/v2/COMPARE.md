# 생성 모델 비교 (63문항, 임베딩 multilingual-e5-small@614241f)

환경: 4 CPU, GPU 없음. 검색 단계는 모델과 무관하게 동일하다.

| 지표 | ollama:qwen2.5:3b | ollama:qwen2.5:7b |
|---|---|---|
| 경로 일치 | 63/63 | 63/63 |
| 상태 일치 | 48/63 | 53/63 |
| 정형 정답 | 10/10 | 10/10 |
| 보류 적중 | 13/13 | 13/13 |
| 핵심 사실(자동) | 32/35 | 39/40 |
| 기대 출처 인용 | 34/35 | 40/40 |
| 영어→영어 | 5/6 | 8/8 |
| 답할 수 있는데 보류 | 15/48 | 10/48 |
| 프로젝트 간 노출 | 0 | 0 |
| 없는 인용 ID 반환 | 0 | 0 |
| 제목만·만료 공지 세부 답변 | 0 | 0 |
| 모델 호출 | 43 | 43 |
| 지연 평균/p95 (초) | 22.3 / 46.2 | 44.3 / 85.7 |

## 서버가 버린 모델 주장 (사유별)

| 사유 | ollama:qwen2.5:3b | ollama:qwen2.5:7b |
|---|---|---|
| contradicts_valid_period | 1 | 0 |
| echoes_question | 2 | 1 |
| quote_not_in_source | 8 | 1 |

## 문항별 상태 (기대와 다른 칸에 ✗)

| 문항 | 기대 | ollama:qwen2.5:3b | ollama:qwen2.5:7b |
|---|---|---|---|
| L07 | answered | answered ✗ | answered |
| L09 | answered | insufficient_evidence ✗ | answered |
| L16 | answered | answered | answered ✗ |
| L17 | answered | answered ✗ | answered |
| L19 | answered | insufficient_evidence ✗ | answered |
| M01 | answered | insufficient_evidence ✗ | answered |
| M04 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| M05 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| M07 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| M12 | answered | insufficient_evidence ✗ | answered |
| N02 | answered | answered ✗ | insufficient_evidence ✗ |
| N06 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N07 | answered | insufficient_evidence ✗ | answered |
| N13 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N16 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N17 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N19 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N22 | answered | insufficient_evidence ✗ | insufficient_evidence ✗ |
| N24 | answered | insufficient_evidence ✗ | answered |

(모든 모델이 기대대로 처리한 문항은 표에서 생략)

## 원문에 없는 발췌 예시 (원인 분석용)

- [ollama:qwen2.5:3b] M01: 발췌 “'궁궐 역사 산책 코스 > 문단 5': 키워드: 조선 왕실문화, 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 ” ↔ 원문 “키워드: Joseon Dynasty — 조선 왕실문화와 국가 질서를 이해하는 핵심 키워드입니다.; Royal Ritual — 궁궐 공간이 단순한 건물이 아니라 의”
- [ollama:qwen2.5:3b] M02: 발췌 “의미: 서울특별시 종로구 사직로 161” ↔ 원문 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.”
- [ollama:qwen2.5:3b] M02: 발췌 “의미: 서울특별시 종로구 사직로 161” ↔ 원문 “의미: 서울 전통문화 여행의 출발점이 되는 상징적 공간이며, 왕실문화의 규모와 질서를 직접 느낄 수 있습니다.”
- [ollama:qwen2.5:3b] M03: 발췌 “비 오는 날 실내 전통문화 코스 (Rainy-Day Indoor Traditional Culture Course): 비가 오거나 더운 날에도 실내 전시와 짧은 동” ↔ 원문 “추천 이유: 우천 시 이동 부담을 줄이면서 왕실문화, 도시사, 한옥 생활문화를 끊기지 않는 해설 흐름으로 연결합니다.”
- [ollama:qwen2.5:7b] M04: 발췌 “전통시장 미식 코스 (Traditional Market Food Course): 전통시장의 먹거리와 생활문화를 연결해 서울 사람들의 일상 속 전통을 체험하는 코스” ↔ 원문 “전통시장 미식 코스 (Traditional Market Food Course): 전통시장의 먹거리와 생활문화를 연결해 서울 사람들의 일상 속 전통을 체험하는 코스”
