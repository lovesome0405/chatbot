"""궁능유적본부 공지 원문 수집 (주상 PC 등 접속 가능한 곳에서 실행). 표준 라이브러리만 사용.

    python scripts/fetch_royal_notice.py "https://royal.khs.go.kr/ROYAL/contents/R403000000.do?id=20260830151817711582&schBdcode=gbg&schM=view"

결과: data/maru/royal_notices/<id>.html (본문 영역 원문) + <id>.json (제목·본문·기간 후보, needs_review=true)
1) 출력된 제목 후보·날짜 문맥을 원문과 대조해 JSON의 title / published_at / valid_from / valid_to 를 채우고
   needs_review 를 false 로 바꾼다(날짜는 자동으로 채우지 않는다).
2) `python -m ragcore.cli ingest --project maru` → 이 공지가 public_original 로 적재되고,
   같은 장소의 합성 공지(synthetic:royal-gbg-special-opening)는 적재 대상에서 빠진다.
needs_review=true 인 파일은 적재하지 않는다(확인 안 된 기간으로 답하지 않기 위해).
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "maru" / "royal_notices"
DATE = r"(20\d{2})\s*[.\-년/]\s*(\d{1,2})\s*[.\-월/]\s*(\d{1,2})\s*일?\.?"


def text_of(fragment: str) -> str:
    fragment = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S | re.I)
    fragment = re.sub(r"<br\s*/?>|</p>|</li>|</tr>|</h\d>", "\n", fragment, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", fragment))
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in t.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def balanced(raw: str, start: int, tag: str) -> str:
    """start 위치의 여는 태그부터 같은 이름의 닫는 태그까지(중첩 고려) 잘라낸다."""
    tag = tag.lower()
    depth, i = 0, start
    pat = re.compile(rf"<(/?){tag}\b[^>]*>", re.I)
    for m in pat.finditer(raw, start):
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return raw[start:m.end()]
    return raw[start:start + 20000]


def main() -> int:
    url = sys.argv[1]
    nid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("id", ["notice"])[0]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (local RAG demo; manual fetch)"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    OUT.mkdir(parents=True, exist_ok=True)
    # 원본 전체를 보존(구조 확인·재추출용). 이 파일은 공개 페이지 HTML이다.
    (OUT / f"{nid}.raw.html").write_text(f"<!-- 출처: {url} , {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC 수집 -->\n{raw}", encoding="utf-8")
    page_title = text_of(re.search(r"<title>(.*?)</title>", raw, re.S | re.I).group(1)) if "<title" in raw.lower() else ""
    # 공지 제목 후보: class 에 tit/subject/subj 가 들어간 요소의 짧은 텍스트
    title_cands = []
    for m in re.finditer(r'<(h\d|th|td|p|strong|span|div|dt|dd)[^>]+class="[^"]*(?:tit|subj)[^"]*"[^>]*>', raw, re.I):
        t = text_of(balanced(raw, m.start(), m.group(1))).replace("\n", " ")
        if 4 <= len(t) <= 150 and t not in title_cands and t != page_title:
            title_cands.append(t)
    title_cands.sort(key=len)
    # 본문 후보: class 에 view/cont/board 가 들어간 div 를 중첩까지 따라가 자른 뒤 가장 긴 것
    blocks = [balanced(raw, m.start(), "div") for m in re.finditer(r'<div[^>]+class="[^"]*(?:view|cont|board)[^"]*"[^>]*>', raw, re.I)]
    body_html = max(blocks, key=lambda b: len(text_of(b))) if blocks else raw
    body = text_of(body_html)
    (OUT / f"{nid}.html").write_text(f"<!-- 출처: {url} -->\n{body_html}", encoding="utf-8")
    dates = []
    for m in re.finditer(DATE, body):
        try:
            d = date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            continue
        ctx = body[max(0, m.start() - 50): m.end() + 50].replace("\n", " ")
        dates.append({"date": d, "context": ctx})
    rec = {
        "source_id": f"royal:{nid}", "collection": "notices",
        "title": title_cands[0] if title_cands else "", "title_candidates": title_cands[:6], "page_title": page_title,
        "body": body[:4000], "url": url,
        # 날짜는 자동으로 채우지 않는다: date_candidates 의 문맥을 보고 사람이 정한다
        "published_at": None, "valid_from": None, "valid_to": None, "date_candidates": dates,
        "replaces_synthetic": "synthetic:royal-gbg-special-opening", "needs_review": True,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / f"{nid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print("제목 후보:", *[f"  - {t}" for t in title_cands[:6]] or ["  (없음)"], sep="\n")
    print(f"본문 글자 수: {len(body)}  (앞부분: {body[:120]!r})")
    print("날짜 후보와 문맥:", *[f"  - {x['date']}: …{x['context']}…" for x in dates] or ["  (없음)"], sep="\n")
    print(f"→ {OUT / (nid + '.json')} 에서 title·published_at·valid_from·valid_to 를 정하고 needs_review=false 로 바꾸세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
