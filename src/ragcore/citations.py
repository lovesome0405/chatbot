"""인용 검증(서버 측).

자동 판정:
  1. 인용 ID가 이번 요청에 전달한 근거 ID 중 하나인가 (아니면 그 인용 폐기)
  2. 발췌(quote)가 해당 근거 원문에 그대로 포함되는가 (공백만 정규화)
  3. 주장에 나온 날짜·숫자(금액·학점 등)가 인용된 근거 원문에 있는가
통과한 인용이 하나도 없는 주장은 버린다.
자동 판정은 "인용이 주장을 의미상 지지하는가"를 보장하지 않는다 → 정답셋·사람 검토로 별도 확인.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .models import Evidence

_WS = re.compile(r"\s+")
# 날짜(2026-09-01, 9월 1일), 소수(3.0), 시각(11:50), 2자리 이상 정수. 한 자리 단독 숫자는 서수 표현이 많아 제외.
_VALUES = re.compile(r"\d{4}-\d{1,2}-\d{1,2}|\d{1,2}:\d{2}|\d+\.\d+|\d{2,}")


def _norm(s: str) -> str:
    """공백·전각 문자 정규화(NFKC, 전각 마침표). 내용 글자는 바꾸지 않는다."""
    s = unicodedata.normalize("NFKC", (s or "").replace("\u00a0", " ")).replace("\u3002", ".")
    return _WS.sub(" ", s).strip().lower()


_TRAIL = ".!?…。 "


def strip_locator_prefix(quote: str, locator: str) -> str:
    """모델이 서버가 준 위치 표시(예: '코스 > 문단 5':)를 발췌 앞에 붙였으면 그 부분만 뗀다."""
    q = quote.strip()
    for wrap in ("'{}':", "\"{}\":", "[{}]", "{}:"):
        pre = wrap.format(locator)
        if locator and q.startswith(pre):
            return q[len(pre):].strip()
    return q


def key_values(text: str) -> list[str]:
    vals = []
    for v in _VALUES.findall(text or ""):
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", v):
            y, m, d = v.split("-")
            v = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
        vals.append(v)
    return vals


_SEG = re.compile(r"\s*(?:\||…|\.\.\.)\s*")


def quote_in_source(quote: str, source: str) -> bool:
    """발췌가 원문에 그대로 있는가. ' | ' 또는 '…'로 이어 붙인 발췌는 각 구절(2자 이상)이 원문에 순서대로 있어야 한다."""
    q, s = _norm(quote).rstrip(_TRAIL), _norm(source)
    if len(q) < 2:
        return False
    if q in s:
        return True
    segs = [x for x in _SEG.split(q) if x]
    if len(segs) < 2 or any(len(x) < 2 for x in segs):
        return False
    pos = 0
    for seg in segs:
        i = s.find(seg, pos)
        if i < 0:
            return False
        pos = i + len(seg)
    return True


@dataclass
class Verified:
    claims: list[tuple[str, list[tuple[Evidence, str]]]] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    unknown_ids: int = 0
    quote_misses: int = 0
    value_mismatches: int = 0


def _echoes_question(text: str, question: str | None) -> bool:
    """질문을 되풀이한 문장(물음표 포함 또는 토큰 85% 이상 겹침)은 사실 주장이 아니다."""
    if not question:
        return False
    if text.rstrip().endswith("?"):
        return True
    from .textnorm import tokens
    a, b = set(tokens(text)), set(tokens(question))
    return bool(a) and len(a & b) / len(a) >= 0.85


def verify(claims: list[dict], evidences: list[Evidence], question: str | None = None) -> Verified:
    by_id = {ev.eid: ev for ev in evidences}
    out = Verified()
    for claim in claims:
        text = str(claim.get("text", "")).strip()
        if _echoes_question(text, question):
            out.dropped.append({"reason": "echoes_question", "claim": text[:200]})
            continue
        good: list[tuple[Evidence, str]] = []
        for cit in claim.get("citations") or []:
            ev = by_id.get(str(cit.get("id", "")).strip())
            quote = str(cit.get("quote", "")).strip()
            if ev is None:
                out.unknown_ids += 1
                out.dropped.append({"reason": "unknown_citation_id", "claim": text[:200], "eid": str(cit.get("id"))})
                continue
            quote = strip_locator_prefix(quote, ev.locator)
            if not quote_in_source(quote, ev.text):
                out.quote_misses += 1
                out.dropped.append({"reason": "quote_not_in_source", "eid": ev.eid, "claim": text[:200], "quote": quote[:200],
                                    "source_text": ev.text[:300]})
                continue
            good.append((ev, quote))
        if not text or not good:
            continue
        cited_text = _norm(" ".join(ev.text + " " + ev.title for ev, _ in good))
        cited_vals = set(key_values(cited_text)) | set(_VALUES.findall(cited_text))
        missing = [v for v in key_values(text) if v not in cited_vals and v not in cited_text]
        if missing:
            out.value_mismatches += 1
            out.dropped.append({"reason": "value_not_in_cited_source", "values": missing, "claim": text[:200]})
            continue
        out.claims.append((text, good))
    return out
