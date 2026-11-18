"""한글 키워드 검색용 단순 정규화.

- 영어 FTS 사전(english stemmer)을 한글에 쓰지 않는다. PostgreSQL에는 'simple' 설정으로
  이 모듈이 미리 만든 토큰 문자열만 넣는다.
- 규칙(명시적, 평가로 조정):
  1. NFKC + 소문자. 한글·영문·숫자 외 문자는 공백. 숫자 사이 점(3.0)은 보존.
  2. 한글 토큰 끝의 조사를 한 번 떼어낸 형태를 함께 넣는다(장학금은 → 장학금).
  3. 띄어쓰기 차이 대응: 한글 토큰의 글자 2-gram을 함께 넣는다(학과수석 ↔ 학과 수석).
  4. 질의어 불용어(뭐야/알려줘/what/the 등)는 질의에서만 뺀다.
  5. 동의어·한영 지명 별칭은 어댑터가 사전으로 제공하고 질의 확장에만 쓴다.
"""

from __future__ import annotations

import re
import unicodedata

HANGUL = re.compile(r"^[가-힣]+$")
_KEEP = re.compile(r"(?<=\d)\.(?=\d)")
_NON_WORD = re.compile(r"[^0-9a-z가-힣ㄱ-ㆎ.]+")

# 긴 조사부터 검사. 한 글자 조사는 남는 글자가 2자 이상일 때만 뗀다.
JOSA = sorted(
    [
        "에서는", "에서도", "으로는", "이라도", "까지는", "부터는", "에게서", "이랑은",
        "에서", "으로", "에게", "께서", "부터", "까지", "마다", "이나", "이랑", "하고", "처럼", "보다", "이야", "이에요", "예요",
        "은", "는", "이", "가", "을", "를", "에", "의", "와", "과", "도", "로", "만", "랑", "야",
    ],
    key=len,
    reverse=True,
)

QUERY_STOPWORDS = {
    # 한국어 질문 표현
    "뭐야", "뭐", "뭔가요", "무엇", "무엇인가요", "알려줘", "알려", "주세요", "줘", "해줘", "있어", "있나요", "있어요", "어디", "어디야",
    "언제", "언제야", "어떻게", "어떤", "좀", "그", "이", "저", "수", "있는", "있었던", "곳은", "곳", "해", "돼", "되나요", "인가요", "나요",
    "거기", "여기", "궁금해", "말해줘", "가르쳐줘", "봐", "보여줘", "할", "하는",
    # 영어
    "the", "a", "an", "is", "are", "was", "were", "what", "which", "where", "when", "how", "who", "do", "does", "did", "can",
    "could", "i", "me", "my", "you", "your", "it", "its", "of", "to", "in", "on", "at", "for", "and", "or", "please", "tell",
    "about", "there", "this", "that", "be", "now", "any", "with", "from", "by", "as", "if", "will", "would", "should", "see",
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = _KEEP.sub("․", text)  # 숫자 사이 점을 임시 문자로 보존
    text = _NON_WORD.sub(" ", text.replace(".", " "))
    text = text.replace("․", ".")
    return re.sub(r"\s+", " ", text).strip()


def strip_josa(token: str) -> str:
    if not HANGUL.match(token):
        return token
    for j in JOSA:
        if token.endswith(j):
            rest = token[: -len(j)]
            if len(rest) >= (2 if len(j) == 1 else 1):
                return rest
    return token


def bigrams(token: str) -> list[str]:
    if not HANGUL.match(token) or len(token) < 3:
        return []
    return [token[i : i + 2] for i in range(len(token) - 1)]


def tokens(text: str, *, query: bool = False) -> list[str]:
    """중복 제거된 검색 토큰 목록(순서 유지)."""
    out: list[str] = []
    for raw in normalize(text).split():
        if query and raw in QUERY_STOPWORDS:
            continue
        base = strip_josa(raw)
        if query and base in QUERY_STOPWORDS:
            continue
        for t in [raw, base, *bigrams(base)]:
            if len(t) >= 2 or t.isdigit():
                out.append(t)
    return list(dict.fromkeys(out))


def search_text(*parts: str | None) -> str:
    """색인용 토큰 문자열 (PostgreSQL to_tsvector('simple', ...) 입력)."""
    return " ".join(tokens(" ".join(p for p in parts if p)))


def expand_query(question: str, aliases: dict[str, list[str]]) -> list[str]:
    """질의 토큰 + 어댑터 별칭 확장. aliases 키는 정규화된 구(phrase)."""
    norm = f" {normalize(question)} "
    toks = tokens(question, query=True)
    compact = norm.replace(" ", "")
    for key, values in aliases.items():
        k = normalize(key)
        if not k:
            continue
        hit = f" {k} " in norm if re.match(r"^[0-9a-z .]+$", k) else k.replace(" ", "") in compact
        if hit:
            for v in values:
                toks.extend(tokens(v))
    return list(dict.fromkeys(toks))


def to_tsquery(toks: list[str]) -> str:
    safe = [t for t in toks if re.match(r"^[0-9a-z가-힣.]+$", t)]
    return " | ".join(f"'{t}'" for t in safe)


def is_korean(text: str) -> bool:
    hangul = len(re.findall(r"[가-힣]", text or ""))
    latin = len(re.findall(r"[a-zA-Z]", text or ""))
    return hangul >= max(1, latin // 3)


def topic(word: str) -> str:
    """받침에 맞춰 은/는을 붙인다(한글이 아니면 은(는))."""
    last = (word or "").rstrip()[-1:]
    if not ("가" <= last <= "힣"):
        return f"{word}은(는)"
    return f"{word}{'은' if (ord(last) - 0xAC00) % 28 else '는'}"
