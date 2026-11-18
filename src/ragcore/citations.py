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


_KO_DATE = re.compile(r"(\d{4})\s*(?:년|\.)\s*(\d{1,2})\s*(?:월|\.)\s*(\d{1,2})\s*일?")


def iso_dates(text: str) -> list[str]:
    """'2026년 10월 31일', '2026. 10. 31.', '2026.10.31' → '2026-10-31' (근거와 주장의 날짜 형식 차이를 흡수)."""
    out = []
    for y, m, d in _KO_DATE.findall(text or ""):
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            out.append(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")
    return out


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
    echo_claims: set = field(default_factory=set)   # 질문을 긍정문으로 되풀이한 주장의 위치(버리지 않고 근거로 보강)


def _overlap(text: str, question: str) -> float:
    from .textnorm import tokens
    a, b = set(tokens(text)), set(tokens(question))
    return len(a & b) / len(a) if a else 0.0


# 되풀이 주장의 '질문 단어'를 근거에서 찾을 때 떼어 보는 서술어 어미(긴 것부터)
_PRED_ENDINGS = ("했어요", "해요", "하면", "하고", "하는", "할까", "했어", "해서", "어요", "아요", "해", "할", "을", "를", "고", "면", "어", "아")
_TIME_WORDS = {"지금", "오늘", "현재", "요즘", "이번", "내일"}   # 기간 판단은 서버가 따로 한다


def _stems(word: str) -> list[str]:
    from .textnorm import strip_josa
    m = re.match(r"^(\d*)([가-힣]+)$", word)          # '1학기에' 같은 숫자+한글 단어도 조사를 뗀다
    if not m:
        return []
    base = m.group(1) + strip_josa(m.group(2))
    for e in _PRED_ENDINGS:
        if base.endswith(e):
            # 어간이 한 글자인 서술어(받을·볼·걷고)는 단어 비교로 확인할 수 없어 건너뛴다
            return [base, base[: -len(e)]] if len(base) - len(e) >= 2 else []
    return [base]


def echo_supported(text: str, question: str, evidence_text: str) -> bool:
    """되풀이 주장이 질문에서 가져온 한국어 단어를 모두 인용 근거(제목·본문)에서 찾을 수 있는지.
    단어 비교라 의미까지 보장하지는 않는다. 영어 주장은 한국어 근거와 단어로 비교할 수 없어 검사하지 않는다."""
    from .textnorm import QUERY_STOPWORDS, normalize
    src = normalize(evidence_text).replace(" ", "")
    q_stems = {st for w in normalize(question).split() for st in _stems(w)}
    for w in normalize(text).split():
        if w in QUERY_STOPWORDS:
            continue
        stems = [st for st in _stems(w) if len(st) >= 2 and st not in QUERY_STOPWORDS and st not in _TIME_WORDS]
        if not stems or not (set(stems) & q_stems):
            continue
        if not any(st in src for st in stems):
            return False
    return True


def enrich_echo(text: str, quote: str, lang: str) -> str:
    """되풀이 주장 뒤에 이미 검증된 근거 발췌를 붙인다(새 사실을 만들지 않음)."""
    q = quote.strip().rstrip(".。")
    return f"{text.rstrip()} 자료에는 “{q}”라고 나와 있어요." if lang == "ko" else f'{text.rstrip()} The source says: "{q}".'


_NON_ANSWER = re.compile(
    r"알려지지 않|알려주지 못|알려드릴 수 없|알 수 없|찾을 수 없|찾지 못|나와 있지 않|언급되지 않|언급이 없|언급하지 않|정보가 없|자료가 없|"
    r"not mention|no information|not available in|can(?:no|')t find|could not find|couldn't find|not provided|"
    r"does(?: not|n't) (?:say|specify|include)|not specified|i don't know|unknown", re.I)


def is_non_answer(text: str) -> bool:
    """'모른다·언급 없음' 문장은 근거 기반 주장이 아니다(보류로 처리)."""
    return bool(_NON_ANSWER.search(text or ""))


def _echoes_question(text: str, question: str | None) -> bool:
    """질문을 그대로 베낀 의문문(물음표로 끝남)은 사실 주장이 아니므로 버린다.
    긍정문 되풀이("~할 수 있어요")는 근거와 맞는 답일 수 있어 버리지 않고 echo_claims 로 표시한다(v0.3.0)."""
    return bool(question) and text.rstrip().endswith(("?", "？"))


def verify(claims: list[dict], evidences: list[Evidence], question: str | None = None) -> Verified:
    by_id = {ev.eid: ev for ev in evidences}
    out = Verified()
    for claim in claims:
        text = str(claim.get("text", "")).strip()
        if is_non_answer(text):
            out.dropped.append({"reason": "non_answer", "claim": text[:200]})
            continue
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
        cited_vals = set(key_values(cited_text)) | set(_VALUES.findall(cited_text)) | set(iso_dates(cited_text))
        missing = [v for v in key_values(text) if v not in cited_vals and v not in cited_text]
        if missing:
            out.value_mismatches += 1
            out.dropped.append({"reason": "value_not_in_cited_source", "values": missing, "claim": text[:200]})
            continue
        if question and _overlap(text, question) >= 0.6:
            if _overlap(text, question) == 1.0:          # 질문을 글자 그대로 옮김: 답이 아님
                out.dropped.append({"reason": "echoes_question", "claim": text[:200]})
                continue
            if not echo_supported(text, question, cited_text):   # v0.3.0 회귀 수정: 무관한 발췌로 근거 없는 답을 감싸지 않는다
                out.dropped.append({"reason": "echo_unsupported", "claim": text[:200]})
                continue
            out.echo_claims.add(len(out.claims))
        out.claims.append((text, good))
    return out
