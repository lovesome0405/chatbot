"""표준 라이브러리만 쓰는 작은 HTML 표 파서. rowspan/colspan을 펼쳐 격자로 만든다."""

from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser


class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._t = None
        self._row = None
        self._cell = None
        self._section = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self._t = {"caption": "", "head": [], "body": [], "attrs": a}
        elif self._t is None:
            return
        elif tag in ("thead", "tbody"):
            self._section = tag
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = {"th": tag == "th", "text": "", "rowspan": int(a.get("rowspan", 1) or 1), "colspan": int(a.get("colspan", 1) or 1)}
        elif tag == "caption":
            self._cell = {"text": "", "caption": True}
        elif tag == "br" and self._cell is not None:
            self._cell["text"] += "\n"

    def handle_endtag(self, tag):
        if self._t is None:
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(self._cell)
            self._cell = None
        elif tag == "caption" and self._cell is not None:
            self._t["caption"] = self._cell["text"].strip()
            self._cell = None
        elif tag == "tr" and self._row is not None:
            (self._t["head"] if self._section == "thead" else self._t["body"]).append(self._row)
            self._row = None
        elif tag == "table":
            self.tables.append(self._t)
            self._t = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data


def _grid(rows: list[list[dict]]) -> list[list[str]]:
    grid: list[list[str | None]] = []
    pending: dict[tuple[int, int], str] = {}
    for r, row in enumerate(rows):
        out: list[str] = []
        c = 0
        cells = iter(row)
        while True:
            if (r, c) in pending:
                out.append(pending.pop((r, c)))
                c += 1
                continue
            cell = next(cells, None)
            if cell is None:
                break
            text = clean(cell["text"], squash=cell.get("th", False))
            for dc in range(cell["colspan"]):
                out.append(text)
                for dr in range(1, cell["rowspan"]):
                    pending[(r + dr, c + dc)] = text
            c += cell["colspan"]
        while (r, c) in pending:
            out.append(pending.pop((r, c)))
            c += 1
        grid.append(out)
    return grid


def clean(text: str, squash: bool = False) -> str:
    text = unescape(text).replace("\xa0", " ")
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    # "교\n내"처럼 한 글자씩 줄바꿈된 셀은 붙이고, 그 외 줄바꿈은 공백으로
    if lines and all(len(ln) == 1 for ln in lines):
        return "".join(lines)
    out = re.sub(r"\s+", " ", " ".join(lines)).strip()
    return squash_spaced(out) if squash else out


def squash_spaced(text: str) -> str:
    """'공 로 장학금' → '공로 장학금': 연속된 한 글자 한글 토큰(2개 이상)만 붙인다. '및' 같은 단독 한 글자는 유지."""
    toks = text.split(" ")
    out, run = [], []
    for t in toks + [""]:
        if len(t) == 1 and re.match(r"[가-힣]", t):
            run.append(t)
            continue
        if len(run) >= 2:
            out.append("".join(run))
        else:
            out.extend(run)
        run = []
        if t:
            out.append(t)
    return " ".join(out)


def parse_tables(html: str) -> list[dict]:
    p = _TableParser()
    p.feed(html)
    return [{"caption": t["caption"], "headers": (_grid(t["head"]) or [[]])[-1], "rows": _grid(t["body"]),
             "summary": t["attrs"].get("summary", "")} for t in p.tables]
