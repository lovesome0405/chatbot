"""궁능유적본부 공지 원문 수집 (주상 PC 등 접속 가능한 곳에서 실행). 표준 라이브러리만 사용.

    python scripts/fetch_royal_notice.py "https://royal.khs.go.kr/ROYAL/contents/R403000000.do?id=20260830151817711582&schBdcode=gbg&schM=view"

결과: data/maru/royal_notices/<id>.html (본문 영역 원문) + <id>.json (제목·본문·기간 후보, needs_review=true)
1) JSON의 valid_from / valid_to / published_at 을 원문과 대조해 고친 뒤 needs_review 를 false 로 바꾼다.
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


def main() -> int:
    url = sys.argv[1]
    nid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("id", ["notice"])[0]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (local RAG demo; manual fetch)"})
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    title = text_of(re.search(r"<title>(.*?)</title>", raw, re.S | re.I).group(1)) if "<title" in raw.lower() else ""
    # 게시판 본문 후보: 가장 긴 view/content 영역
    blocks = re.findall(r'<div[^>]+class="[^"]*(?:view|cont|board)[^"]*"[^>]*>.*?</div>', raw, flags=re.S | re.I)
    body_html = max(blocks, key=len) if blocks else raw
    body = text_of(body_html)
    dates = [date(int(y), int(m), int(d)).isoformat() for y, m, d in re.findall(DATE, body)]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{nid}.html").write_text(f"<!-- 출처: {url} , {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC 수집 -->\n{body_html}",
                                     encoding="utf-8")
    rec = {
        "source_id": f"royal:{nid}", "collection": "notices", "title": title, "body": body[:4000], "url": url,
        "published_at": dates[0] if dates else None, "valid_from": dates[1] if len(dates) > 1 else None,
        "valid_to": dates[2] if len(dates) > 2 else None, "date_candidates": dates,
        "replaces_synthetic": "synthetic:royal-gbg-special-opening", "needs_review": True,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / f"{nid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: rec[k] for k in ("title", "published_at", "valid_from", "valid_to", "date_candidates")}, ensure_ascii=False, indent=1))
    print(f"→ {OUT / (nid + '.json')} 의 날짜를 원문과 대조해 고치고 needs_review=false 로 바꾼 뒤 적재하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
