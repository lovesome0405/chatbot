"""v0.6.0 학교 기본 정보 카드 수집 도구(롤리폴리 대상: 한국폴리텍대학 춘천캠퍼스).

공식 홈페이지 공개 페이지에서 **원문 줄을 그대로** 찾아 data/lolypoly/school_info.json 에 적는다. 값을 지어내거나
기억으로 채우지 않는다. 페이지에서 찾지 못한 항목은 text=null + missing_reason 으로 남긴다.
결과는 needs_review=true 로 저장되고, 사람이 원문과 대조한 뒤 needs_review=false 로 바꿔야 엔진이 적재한다
(scripts/fetch_royal_notice.py 와 같은 규칙).

  python scripts/fetch_school_info.py            # 페이지 받기 + 카드 다시 만들기(기존 검수 표시는 지움)
  python scripts/fetch_school_info.py --check    # 받기만 하고, 저장된 카드의 원문 줄이 아직 페이지에 있는지 확인
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/lolypoly/school_info.json"
BASE = "https://www.kopo.ac.kr/chuncheon/"
PAGES = {
    "location": BASE + "content.do?menu=4849",    # 찾아오시는 길: 주소·대표전화·팩스·해당학과
    "org": BASE + "content.do?menu=4842",         # 조직구성: 과정별 학과
    "home": BASE + "index.do",                    # 첫 화면: 입학 문의전화
}
CAMPUS = "한국폴리텍대학 춘천캠퍼스"


def page_text(raw: str, whole: bool = False) -> list[str]:
    i = -1 if whole else raw.find('id="contents')
    body = raw[i:] if i >= 0 else raw
    body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", body)
    t = re.sub(r"<br\s*/?>|</(p|li|tr|div|h\d|dd|dt)>", "\n", body)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return [re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in t.splitlines() if ln.strip()]


def find(lines: list[str], pattern: str) -> str | None:
    rx = re.compile(pattern)
    return next((ln for ln in lines if rx.search(ln)), None)


def org_departments(lines: list[str]) -> dict[str, list[str]]:
    """조직구성 페이지의 '학위과정 / 전문기술과정 / 하이테크과정' 아래 '…과' 줄들(첫 번째 목록만)."""
    out, cur = {}, None
    for ln in lines:
        if ln in ("학위과정", "전문기술과정", "하이테크과정"):
            if ln in out:
                break
            cur = ln
            out[cur] = []
        elif cur and re.fullmatch(r"[A-Za-z가-힣]+과", ln):
            out[cur].append(ln)
        elif cur and out[cur]:
            cur = None if ln not in ("학위과정", "전문기술과정", "하이테크과정") else cur
    return out


def build(pages: dict[str, str], checked: str) -> dict:
    lines = {k: page_text(v, whole=(k == "home")) for k, v in pages.items()}   # 첫 화면 문의전화는 본문 영역 밖
    loc = lines["location"]
    addr = find(loc, r"주소\s*:\s*\[\d{5}\]")
    tel = find(loc, r"대표전화\s*:")
    fax = find(loc, r"팩스번호\s*:")
    # 첫 화면 문의 배너: '춘천캠퍼스 입학 문의전화' 와 번호가 줄이 나뉘어 있어 이어 붙여 찾는다
    m = re.search(r"춘천캠퍼스\s*입학\s*문의전화\s*[\d-]{9,}", " ".join(lines["home"]))
    adm = re.sub(r"\s+", " ", m.group(0)) if m else None
    depts_loc = [ln for ln in loc if re.match(r"•\s*\d년제\s*(학위|전문기술|하이테크)", ln)]
    org = org_departments(lines["org"])
    names = sorted({d for v in org.values() for d in v} | {d.strip() for ln in depts_loc for d in ln.split(":", 1)[-1].split(",")})
    items = [
        {"key": "address", "label": "캠퍼스 주소", "text": addr, "url": PAGES["location"], "names": []},
        {"key": "phone", "label": "대표 연락처", "text": " / ".join(x for x in (tel, fax) if x) or None, "url": PAGES["location"], "names": []},
        {"key": "admission_phone", "label": "입학 문의전화", "text": adm, "url": PAGES["home"], "names": []},
        {"key": "departments", "label": "학과 목록(과정별, 조직구성 페이지의 과정·학과 줄을 순서대로 모음)",
         "text": " / ".join(f"{k}: {', '.join(v)}" for k, v in org.items()) or None, "url": PAGES["org"], "names": names},
        {"key": "departments_location_page", "label": "학과 목록(찾아오시는 길 페이지 표기)", "text": " / ".join(depts_loc) or None,
         "url": PAGES["location"], "names": []},
        {"key": "buildings", "label": "주요 건물", "text": None, "url": None, "names": [],
         "missing_reason": "공식 페이지 텍스트에서 건물 목록을 찾지 못함(식당·도서관 '시설안내'는 이미지로만 있음, 2026-11-23 확인)"},
        {"key": "email", "label": "대표 이메일", "text": None, "url": None, "names": [],
         "missing_reason": "확인한 공식 페이지(찾아오시는 길·조직구성·첫 화면)에 대표 이메일이 없음"},
    ]
    for it in items:
        if it["text"] is None and "missing_reason" not in it:
            it["missing_reason"] = "페이지 구조가 바뀌어 원문 줄을 찾지 못함 — 수집 도구 확인 필요"
    notes = []
    if any("바이오의학공정과" in ln for ln in depts_loc) and "바이오의약공정과" in names:
        notes.append("학과 이름 표기가 페이지마다 다름: 조직구성 '바이오의약공정과' / 찾아오시는 길 '바이오의학공정과'. 카드는 두 원문을 따로 둠.")
    if any("1캠퍼스" in ln for ln in loc):
        notes.append("찾아오시는 길의 주소는 '춘천1캠퍼스' 기준. 2캠퍼스(후평동 쪽)는 카드에 넣지 않음(LOLYPOLY D-052와 같은 판단).")
    return {
        "campus": CAMPUS, "checked_at": checked, "needs_review": True,
        "source_type": "public_original", "collector": "scripts/fetch_school_info.py",
        "pages": {k: {"url": PAGES[k], "sha256": hashlib.sha256(v.encode()).hexdigest()[:16]} for k, v in pages.items()},
        "items": items, "review_notes": notes,
        "review_howto": "각 항목 text 를 url 원문과 대조 → 맞으면 needs_review 를 false 로 바꾸고 reviewed_by·reviewed_at 을 적는다.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    pages = {}
    with httpx.Client(timeout=30, headers={"User-Agent": "Mozilla/5.0 (rag school-info collector)"}, follow_redirects=True) as c:
        for k, url in PAGES.items():
            r = c.get(url)
            r.raise_for_status()
            pages[k] = r.text
    checked = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    if a.check:
        card = json.loads(OUT.read_text(encoding="utf-8"))
        texts = {k: "\n".join(page_text(v, whole=(k == "home"))) for k, v in pages.items()}
        flat = {k: re.sub(r"\s+", " ", v) for k, v in texts.items()}
        bad = [it["key"] for it in card["items"] if it.get("text") and it["key"] != "departments"
               and not all(part.strip() in flat[next(k for k, u in PAGES.items() if u == it["url"])] for part in it["text"].split(" / "))]
        print(json.dumps({"checked_at": checked, "changed_items": bad}, ensure_ascii=False))
        sys.exit(1 if bad else 0)
    card = build(pages, checked)
    OUT.write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    for it in card["items"]:
        print(f"{it['key']:28} {it['text'] or '(없음) ' + it.get('missing_reason', '')}")
    print("notes:", *card["review_notes"], sep="\n  ")
    print(f"→ {OUT} (needs_review=true). 원문과 대조한 뒤 needs_review=false 로 바꿔야 적재된다.")


if __name__ == "__main__":
    main()
