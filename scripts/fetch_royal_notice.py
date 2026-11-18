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


def _squash(line: str) -> str:
    toks, out, run = line.split(" "), [], []
    for t in toks + [""]:
        if len(t) == 1 and re.match(r"[가-힣]", t):
            run.append(t)
            continue
        out.extend(["".join(run)] if len(run) >= 2 else run)
        run = []
        if t:
            out.append(t)
    return " ".join(out)


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


def extract(raw: str) -> dict:
    """공지 상세 HTML → 제목·게시일·본문·날짜 문맥.
    1순위: 궁능유적본부 상세 화면 클래스 board_detail_tit / board_detail_info / board_detail_txt
    (주상 PC에 저장된 원본으로 확인된 구조). 없으면 이전 휴리스틱으로 대체한다."""
    def by_class(cls: str) -> str | None:
        m = re.search(rf'<(\w+)[^>]+class="[^"]*\b{cls}\b[^"]*"[^>]*>', raw, re.I)
        return balanced(raw, m.start(), m.group(1)) if m else None

    page_title = text_of(re.search(r"<title>(.*?)</title>", raw, re.S | re.I).group(1)) if "<title" in raw.lower() else ""
    tit, info, txt = by_class("board_detail_tit"), by_class("board_detail_info"), by_class("board_detail_txt")
    method = "board_detail" if (tit and txt) else "heuristic"
    if method == "board_detail":
        title = text_of(tit).replace("\n", " ").strip()
        title_cands = [title]
        info_text = text_of(info) if info else ""
        posted = [date(int(y), int(m), int(d)).isoformat() for y, m, d in re.findall(DATE, info_text)]
        published_at = posted[0] if posted else None
        body_html = txt
        body = text_of(txt)
    else:
        title_cands = []
        for m in re.finditer(r'<(h\d|th|td|p|strong|span|div|dt|dd)[^>]+class="[^"]*(?:tit|subj)[^"]*"[^>]*>', raw, re.I):
            t = text_of(balanced(raw, m.start(), m.group(1))).replace("\n", " ")
            if 4 <= len(t) <= 150 and t not in title_cands and t != page_title:
                title_cands.append(t)
        title_cands.sort(key=len)
        title = title_cands[0] if title_cands else ""
        info_text, published_at = "", None
        blocks = [balanced(raw, m.start(), "div") for m in re.finditer(r'<div[^>]+class="[^"]*(?:view|cont|board)[^"]*"[^>]*>', raw, re.I)]
        body_html = max(blocks, key=lambda b: len(text_of(b))) if blocks else raw
        body = text_of(body_html)
    # 마크업 때문에 글자마다 띄워진 구간(예: "석 조 물 의")은 붙인다. 원래 어절 경계는 자동으로 되살릴 수 없어
    # "석조물의손상이…"처럼 붙으므로, 사람 검토 때 띄어쓰기를 고친다. 정상 어절("문장 석")은 건드리지 않는다.
    body = "\n".join(_squash(line) for line in body.split("\n"))
    dates = []
    for m in re.finditer(DATE, body):
        try:
            d = date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        except ValueError:
            continue
        dates.append({"date": d, "context": body[max(0, m.start() - 50): m.end() + 50].replace("\n", " ")})
    return {"method": method, "title": title, "title_candidates": title_cands[:6], "page_title": page_title,
            "info": info_text, "published_at": published_at, "body": body, "body_html": body_html, "date_candidates": dates}


def main() -> int:
    ap_args = sys.argv[1:]
    if not ap_args:
        print("사용법: fetch_royal_notice.py <공지 URL> [--html 저장된원본.html]")
        return 2
    url = ap_args[0]
    nid = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("id", ["notice"])[0]
    if "--html" in ap_args:  # 이미 저장한 원본으로 다시 추출(네트워크 없이 재현)
        raw = Path(ap_args[ap_args.index("--html") + 1]).read_text(encoding="utf-8", errors="replace")
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (local RAG demo; manual fetch)"})
        raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
    OUT.mkdir(parents=True, exist_ok=True)
    if "--html" not in ap_args:
        (OUT / f"{nid}.raw.html").write_text(f"<!-- 출처: {url} , {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC 수집 -->\n{raw}", encoding="utf-8")
    x = extract(raw)
    (OUT / f"{nid}.html").write_text(f"<!-- 출처: {url} -->\n{x['body_html']}", encoding="utf-8")
    rec = {
        "source_id": f"royal:{nid}", "collection": "notices", "title": x["title"], "title_candidates": x["title_candidates"],
        "page_title": x["page_title"], "extraction": x["method"], "body": x["body"][:4000], "url": url,
        # 게시일은 상세 정보 영역에서 읽고, 적용 기간은 사람이 date_candidates 문맥을 보고 정한다
        "published_at": x["published_at"], "valid_from": None, "valid_to": None, "date_candidates": x["date_candidates"],
        "action_type": None, "action_target": None, "action_terms": [],
        "replaces_synthetic": "synthetic:royal-gbg-special-opening", "needs_review": True,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (OUT / f"{nid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"추출 방식: {x['method']}")
    print(f"제목: {x['title']}")
    print(f"게시일: {x['published_at']}  (정보 영역: {x['info'][:80]!r})")
    print(f"본문 글자 수: {len(x['body'])}  (앞부분: {x['body'][:120]!r})")
    print("날짜 후보와 문맥:", *[f"  - {d['date']}: …{d['context']}…" for d in x["date_candidates"]] or ["  (없음)"], sep="\n")
    print(f"→ {OUT / (nid + '.json')} 에서 valid_from·valid_to·action_type(예: access_restricted)·action_target·action_terms 를 정하고 needs_review=false 로 바꾸세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
