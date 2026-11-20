"""원문 발췌 답(v0.5.0). 생성 모델이 시간 상한을 넘기거나 실패했을 때, 새 문장을 쓰지 않고
검색된 근거에서 질문과 가장 많이 겹치는 문장을 그대로 보여 준다. 결과는 모델 주장과 같은 형식이라
서버 인용 검증(citations.verify)을 똑같이 통과해야 화면에 나간다.
"""

from __future__ import annotations

import re

from . import textnorm
from .models import Evidence

_SENT = re.compile(r"(?<=[.!?])\s+|(?<=다\.)\s*|\n+")
_MIN_OVERLAP = 2          # 질문 내용어(별칭 확장 포함)와 2개 이상 겹치는 문장만 쓴다
_MIN_COVERAGE = 0.6       # 질문 핵심어(조각·2글자 조각 제외)의 60% 이상이 문장에 있어야 한다(무관한 문장을 답으로 내지 않기)
_GENERIC = {"알려줘", "알려", "기간", "신청", "방법", "언제", "어디", "정보", "추천", "추천해줘", "있어", "있나요", "좋아",
            "where", "what", "when", "which", "good", "place", "places", "recommend"}


def _sentences(ev: Evidence) -> list[str]:
    if ev.text.startswith("[") and " | " in ev.text:      # 표 한 행은 쪼개지 않는다(행을 섞지 않기)
        return [ev.text]
    return [s.strip() for s in _SENT.split(ev.text) if s and len(s.strip()) >= 6]


def _core_terms(question: str) -> set[str]:
    """질문의 핵심어: 원래 단어(조사 뗀 형태)만, 2글자 조각·일반어 제외."""
    out = set()
    for raw in textnorm.normalize(question).split():
        base = textnorm.strip_josa(raw)
        if len(base) >= 2 and base not in textnorm.QUERY_STOPWORDS and base not in _GENERIC:
            out.add(base)
    return out


def extract(question: str, lang: str, evidences: list[Evidence], aliases: dict[str, list[str]], limit: int = 2) -> list[dict]:
    q = {t for t in textnorm.expand_query(question, aliases) if len(t) >= 2 and t not in _GENERIC}
    core = _core_terms(question)
    scored = []
    for rank, ev in enumerate(evidences):
        for sent in _sentences(ev):
            toks = set(textnorm.tokens(sent))
            overlap = len(q & toks)
            # 핵심어는 원래 단어나 별칭(한국어) 어느 쪽으로든 문장에 있으면 맞은 것으로 센다
            hit = sum(1 for c in core if c in toks or any(v in toks for v in textnorm.expand_query(c, aliases) if v != c))
            coverage = hit / len(core) if core else 0
            if overlap >= _MIN_OVERLAP and coverage >= _MIN_COVERAGE:
                english = len(re.findall(r"[A-Za-z]", sent)) > len(re.findall(r"[가-힣]", sent))
                pref = 1 if (lang == "en") == english else 0          # 질문 언어와 같은 언어 문장 우선(앱 영어 설명 등)
                scored.append((pref, overlap, -rank, ev, sent))
    scored.sort(key=lambda x: (-x[0], -x[1], -x[2]))
    scored = [(o, r, ev, sent) for _, o, r, ev, sent in scored]
    out, seen = [], set()
    for _, _, ev, sent in scored:
        if sent in seen:
            continue
        seen.add(sent)
        en_sent = len(re.findall(r"[A-Za-z]", sent)) > len(re.findall(r"[가-힣]", sent))
        text = (f"자료에는 “{sent}”라고 나와 있어요." if lang == "ko" else
                (f'The app data says: "{sent.removeprefix("English (app data): ")}"' if en_sent
                 else f'The source (in Korean) says: "{sent}"'))
        out.append({"text": text, "citations": [{"id": ev.eid, "quote": sent}]})
        if len(out) == limit:
            break
    return out
