"""v0.6.0 일반 답변 B안.

경로(엔진이 결정, 앱 이름은 모른다 — 문구·범위는 어댑터의 GeneralPolicy 에서 온다):
  1) 인사·감사·사용법(질문 전체가 그것뿐일 때) → 고정 응답, route=smalltalk, 모델 0회
  2) 정형·문서 근거로 답함 → 기존 그대로
  3) 근거 없음 + 도메인 사실 질문(어댑터 용어, 금액·날짜·시점 표현) → 기존 보류
  4) 근거 없음 + 도메인 밖 → 일반 답변, route=general, citations=[] (같은 생성 예산)
     서버가 답을 검사해서 도메인 용어·학교/장소 고유명사·금액·날짜·전화번호가 있으면 버리고 보류로 되돌린다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import textnorm


@dataclass
class GeneralPolicy:
    enabled: bool = False
    tone: str = ""                         # 말투(시스템 프롬프트 한 줄)
    scope: str = "general knowledge"       # 답해도 되는 범위 설명(프롬프트용)
    max_chars: int = 320                   # 답 길이 상한(문장 단위로 자름)
    banned_topics: list[str] = field(default_factory=list)     # 정규식. 맞으면 일반 답변 없이 보류(안내 문구)
    domain_terms: list[str] = field(default_factory=list)      # 이 말이 질문·답에 있으면 도메인 질문으로 봄
    smalltalk: dict[str, dict[str, str]] = field(default_factory=dict)   # greet|thanks|help → {ko, en}


# 공통 금지 주제(모든 어댑터): 지시 무시·프롬프트 노출 요구, 개인 연락처·신상
COMMON_BANNED = [
    r"시스템\s*프롬프트", r"system\s*prompt", r"(이전|위의?|모든)\s*(지시|명령|규칙).{0,6}무시", r"ignore\s+(all\s+|your\s+|the\s+|previous\s+|prior\s+)*(instructions|rules)",
    r"jailbreak", r"탈옥", r"make\s+up", r"지어(내|서)", r"(휴대폰|핸드폰|개인)\s*(번호|연락처)", r"주민(등록)?번호", r"학번",
    r"personal\s+(phone|number|address)", r"home\s+address",
]
# 금액·날짜·시점 표현: 질문에 있으면 도메인 사실 질문으로 보고 일반 답변을 하지 않는다
FACT_MARKERS = [
    "얼마", "비용", "가격", "요금", "입장료", "등록금", "몇 시", "몇시", "언제", "날짜", "며칠", "내일", "오늘", "모레", "이번 주", "다음 주",
    "마감", "운영시간", "how much", "price", "cost", "fee", "when", "tomorrow", "today", "tonight", "what time", "deadline",
    "opening hours", "open at", "this week", "next week", "지금", "현재", "now", "right now", "currently", "일정", "스케줄", "행사", "축제", "공연", "schedule", "festival", "concert", "event",
]
OFF_TOPIC_COVERAGE = 0.4   # 도메인 용어가 없고 핵심어 포함률이 이보다 낮으면 문서 생성을 건너뛰고 일반 답변으로(정책이 켜진 경우만)
DOMAIN_COVERAGE = 0.6   # 질문 핵심어의 60% 이상이 검색된 근거 한 곳에 있으면 도메인 질문(근거는 있으나 답을 못 만든 경우)
# 일반 답변 출력에 있으면 버리는 패턴(지어낸 금액·날짜·연락처·주소·링크)
_OUT_BANNED = re.compile(
    r"\d{4}\s*[-./년]\s*\d|\d+\s*월\s*\d+\s*일|\d+\s*(원|만원|won|KRW)\b|[$₩]\s*\d|\b\d{2,3}[-)]\s*\d{3,4}[-\s]\d{4}\b|https?://|www\.|@\w+\.",
    re.I)

SMALLTALK_PATTERNS = {
    "greet": re.compile(r"^(안녕(하세요|하십니까)?|하이|헬로|반가워(요)?|hi|hello|hey|hi there|good (morning|afternoon|evening))$", re.I),
    "thanks": re.compile(r"^((정말|너무|진짜)?\s*(고마워(요)?|고맙습니다|감사(합니다|해요)?|땡큐)(,?\s*(덕분에|잘)\s*\S+)?|thanks?( you)?( (so|very) much| a lot)?|thx|ty)$", re.I),
    "help": re.compile(r"^((너는|넌|여기서|이거)?\s*(뭘|무엇을|뭐|무슨\s*질문을?)\s*(물어볼|할|질문할|답할)\s*수\s*있(어|나요|니|어요)|사용법(\s*알려\s*줘)?|어떻게\s*(써|사용해)|도움말|"
                      r"what can (you|i) (do|ask|answer)( you)?|how (do i|to) use (this|you)|help)$", re.I),
}
_PUNCT = re.compile(r"[\s!?？！.。,，~…:)(\-ㅎㅋ^]+$|^[\s!?？！.。,，~…]+")


def smalltalk_kind(question: str) -> str | None:
    """질문 전체가 인사·감사·사용법일 때만 그 종류. '안녕, 오늘 점심 뭐야?'처럼 내용이 있으면 None."""
    q = _PUNCT.sub("", (question or "").strip()).strip()
    q = re.sub(r"\s+", " ", q)
    if not q or len(q) > 40:
        return None
    for kind, rx in SMALLTALK_PATTERNS.items():
        if rx.match(q):
            return kind
    return None


def _has_term(text: str, terms: list[str]) -> str | None:
    low = (text or "").lower()
    norm = textnorm.normalize(text or "")
    for t in terms:
        t2 = t.lower()
        if not t2:
            continue
        if re.fullmatch(r"[a-z0-9 .'-]+", t2):        # 영어 용어는 단어 경계로('hall' ⊄ 'shall')
            if re.search(rf"\b{re.escape(t2)}\b", low):
                return t
        elif t2 in low or textnorm.normalize(t2) in norm:
            return t
    return None


def banned(question: str, policy: GeneralPolicy) -> str | None:
    for p in COMMON_BANNED + policy.banned_topics:
        if re.search(p, question or "", re.I):
            return p
    return None


def is_domain_question(question: str, policy: GeneralPolicy) -> str | None:
    """도메인 사실 질문이면 그 이유(맞은 말)를, 아니면 None."""
    from .citations import key_values
    hit = _has_term(question, policy.domain_terms) or _has_term(question, FACT_MARKERS)
    if hit:
        return hit
    vals = [v for v in key_values(question) if v]
    return f"value:{vals[0]}" if vals else None


def check_answer(text: str, policy: GeneralPolicy) -> tuple[str | None, str | None]:
    """(통과한 답, 버린 이유). 도메인 용어·고유명사·금액·날짜·연락처·링크가 있으면 버린다."""
    t = (text or "").strip()
    if not t or "NO_ANSWER" in t.upper():
        return None, "model_declined"
    m = _OUT_BANNED.search(t)
    if m:
        return None, f"pattern:{m.group(0)}"
    hit = _has_term(t, policy.domain_terms)
    if hit:
        return None, f"domain_term:{hit}"
    if len(t) > policy.max_chars:                     # 문장 경계에서 자른다
        cut = max(t.rfind(x, 0, policy.max_chars) for x in (". ", "다. ", "요. ", "! ", "? ", ".\n"))
        t = t[: cut + 1].strip() if cut > 40 else t[: policy.max_chars].rstrip() + "…"
    return t, None


def system_prompt(policy: GeneralPolicy, lang: str) -> str:
    language = "Korean" if lang == "ko" else "English"
    return (f"{policy.tone}\nThe app's verified sources do not cover this question, so you may answer it from general knowledge "
            f"only if it is about {policy.scope}.\n"
            f"Answer in {language} in at most 3 short sentences. Plain text, no lists, no links.\n"
            "Never state facts about any specific school, campus, department, building, person, place or event, and never give "
            "prices, dates, schedules, phone numbers or addresses. If answering would require such facts, or the question is "
            "outside the allowed scope, output exactly: NO_ANSWER")
