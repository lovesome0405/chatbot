"""MARU 기존 방식 기준선: app.js의 tokenizeAriSearchText / scoreAriTextMatch / rankAriItemsByMessage 이식.

원본: lovesome0405/ari app.js (data/maru/ARI_COMMIT), 함수 위치 L7783~L7814.
검색 문장(haystack)은 buildAriContext()의 routes/resources 매핑 + routeSearchText/resourceSearchText(L7748~L7773)를
한국어 화면(ko) 기준 원자료 필드로 재구성했다. 앱의 getRouteView/getResourceView 가공(번역·표시 이름)은
재현하지 않았으므로, 기준선 수치는 "같은 데이터·같은 점수 함수" 기준이다(README 한계 참고).
JS 결과와의 일치는 scripts/ari_parity.mjs 로 확인한다.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_SPLIT = re.compile(r"[\s,.;:!?()\[\]{}\"'/\\|_-]+")


def normalize_search_text(value) -> str:
    return str(value or "").lower()


def tokenize(value) -> list[str]:
    out = []
    for t in _SPLIT.split(normalize_search_text(value)):
        t = t.strip()
        if len(t) >= 2 and t not in out:
            out.append(t)
    return out


def score(message: str, haystack: str) -> int:
    text = normalize_search_text(haystack)
    tokens = tokenize(message)
    if not tokens or not text:
        return 0
    total = 0
    for token in tokens:
        if f" {token} " in text:
            total += 4
        elif text.startswith(token) or text.endswith(token):
            total += 3
        elif token in text:
            total += 2
    return total


def haystacks(data_dir: Path) -> list[tuple[str, str]]:
    """(source_id, haystack) — 엔진 원본 ID(place:/course:)로 맞춘다."""
    res = json.loads((data_dir / "ari_culture_resources_appjs.json").read_text(encoding="utf-8"))
    courses = json.loads((data_dir / "courses.json").read_text(encoding="utf-8"))
    out = []
    for c in courses:  # routeSearchText: id, title, englishTitle, subtitle, summary, reason, tags, flow
        tags = list(c.get("target", [])) + [k["name"] for k in c.get("keywords", [])]
        flow = [p["name"]["ko"] for p in c["places"]]
        parts = [c["id"], c["title"]["ko"], c["title"]["en"], c["aiSummary"]["ko"], c["reason"]["ko"], " ".join(tags), " ".join(flow)]
        out.append((f"course:{c['id']}", " ".join(p for p in parts if p)))
    for r in res:  # resourceSearchText: id, nameKo, nameEn, displayName, secondaryName, category, explanation, whyItMatters, tags
        parts = [r["id"], r["nameKo"], r["nameEn"], r["nameKo"], r["nameEn"], r.get("category"), r.get("aiSimpleExplanation"),
                 r.get("aiWhyItMatters"), " ".join(r.get("globalTags", []))]
        out.append((f"place:{r['id']}", " ".join(p for p in parts if p)))
    return out


def rank(message: str, items: list[tuple[str, str]]) -> list[str]:
    """rankAriItemsByMessage: 점수>0만, 점수 내림차순(동점은 원래 순서 — JS sort는 안정 정렬)."""
    scored = [(sid, score(message, h)) for sid, h in items]
    return [sid for sid, s in sorted((x for x in scored if x[1] > 0), key=lambda x: -x[1])]
