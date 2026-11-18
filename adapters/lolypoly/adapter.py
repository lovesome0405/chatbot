"""롤리폴리(한국폴리텍대학 춘천캠퍼스 생활정보) 어댑터.

원본
- data/lolypoly/export.json : LOLYPOLY 공개 필드 export (Meal, AcademicEvent, Notice + 식사시간표). 유형 repository_data
- data/lolypoly/kopo_scholarship_4799.html : 장학 페이지 공개 원문 일부. 유형 public_original
allowlist 밖(계정·커뮤니티·사진·택시방·학생 의견·버스)은 적재하지 않는다.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

from ragcore import textnorm
from ragcore.adapter import DETAIL_TERMS, Adapter, Claim, Part, PartResult, SyncBatch, has_any
from ragcore.chunking import table_row_chunks
from ragcore.engine import citation_from
from ragcore.html_table import parse_tables
from ragcore.models import Chunk, Citation, Document
from ragcore.timeutil import fmt_day, resolve_date, resolve_range, seoul_now

PROJECT = "lolypoly"
MEALS_URL = "https://www.kopo.ac.kr/chuncheon/content.do?menu=4819"
SCHOLARSHIP_URL = "https://www.kopo.ac.kr/chuncheon/content.do?menu=4799"
MEAL_KO = {"breakfast": "조식", "lunch": "중식", "dinner": "석식"}
MEAL_EN = {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner"}
MEAL_WORDS = {
    "breakfast": ["아침", "조식", "breakfast"],
    "lunch": ["점심", "중식", "lunch"],
    "dinner": ["저녁", "석식", "dinner", "supper"],
}
MEAL_TERMS = ["메뉴", "식단", "학식", "밥", "반찬", "menu", "meal", "food", "eat"] + sum(MEAL_WORDS.values(), [])
HOURS_TERMS = ["식사시간", "식사 시간", "몇 시", "몇시", "운영시간", "운영 시간", "언제까지", "hours", "what time", "open"]
NOTICE_LIST_TERMS = ["최근", "목록", "뭐 있", "뭐있", "어떤 공지", "공지 알려", "공지 보여", "list", "recent", "latest"]
NOTICE_CATEGORIES = ["학사", "입시", "행정", "공지", "취업", "장학"]
FIXTURE_CAPTURED = "LOLYPOLY 저장소 fixture (공식 홈페이지 2026-11-02 수집본)"
TIME_TERMS = ["마감", "운영시간", "운영 시간", "식사시간", "식사 시간", "몇 시", "몇시", "deadline", "hours", "what time"]


class LolypolyAdapter(Adapter):
    project = PROJECT
    allowed_collections = {"meals", "meal_hours", "events", "notices", "scholarship"}
    structured_keys = {"meals": {"date", "meal_type"}}
    fresh_days = 30
    persona = ("You are the campus guide of 롤리폴리, a student app for 한국폴리텍대학 춘천캠퍼스. "
               "Talk like a kind senior student: short, clear and friendly (Korean: polite 해요체).")  # 운영시간처럼 시점이 중요한 값: 확인 시각이 30일 이내인 근거만
    aliases = {
        "학식": ["식단", "메뉴"], "점심": ["중식"], "저녁": ["석식"], "아침": ["조식"],
        "장학": ["장학금"], "scholarship": ["장학금", "장학"], "scholarships": ["장학금", "장학"],
        "top student": ["수석"], "top of the department": ["학과수석"], "first place": ["수석"], "valedictorian": ["수석"],
        "admission": ["입학", "입학자"], "entrance": ["입학"], "grade": ["성적"], "grades": ["성적"], "gpa": ["성적"],
        "previous semester": ["직전학기"], "last semester": ["직전학기"], "tuition": ["교육비"], "free": ["전액면제"],
        "waiver": ["면제"], "veterans": ["보훈"], "north korean defectors": ["북한이탈주민"], "work study": ["근로 장학금"],
        "national scholarship": ["국가 장학금", "국가장학금"], "documents": ["서류"], "required documents": ["신청 서류"],
        "academic calendar": ["학사일정"], "exam": ["시험"], "final exam": ["기말시험", "기말평가"],
        "midterm": ["중간시험", "중간평가"], "vacation": ["방학"], "cafeteria": ["식당", "학생식당"],
        "성적장학금": ["성적우수 장학금"], "성적 장학금": ["성적우수 장학금"], "수석장학금": ["수석"],
        "기말고사": ["기말시험", "기말평가"], "중간고사": ["중간시험", "중간평가"], "자격증": ["국가기술자격"],
    }

    def __init__(self, data_dir: str | Path = "data/lolypoly"):
        self.dir = Path(data_dir)

    # ── 적재 ───────────────────────────────
    def load(self) -> SyncBatch:
        exp = json.loads((self.dir / "export.json").read_text(encoding="utf-8"))
        commit = exp["provenance"]["lolypoly_commit"][:7]
        snap = f"{FIXTURE_CAPTURED}, lolypoly@{commit}"
        docs: list[Document] = []
        for m in exp["meals"]:
            d = date.fromisoformat(m["date"])
            label = f"{fmt_day(d)} {MEAL_KO[m['meal_type']]}"
            menu = ", ".join(m["items"]) if m["items"] else "(공식 식단표에 메뉴 없음)"
            meta = {"date": m["date"], "meal_type": m["meal_type"], "items": m["items"], "snapshot": snap}
            docs.append(Document(
                project=PROJECT, source_id=f"meal:{m['date']}:{m['meal_type']}", collection="meals",
                title=f"{label} 식단", body=menu, url=m["source_url"], language="ko", content_level="body",
                source_type="repository_data", metadata=meta,
                chunks=[Chunk("meal", f"식단 > {label}", f"{label}: {menu}", {"date": m["date"], "meal_type": m["meal_type"]})],
            ))
        for t in exp.get("meal_hours", []):
            heads = t["headers"]
            rows = [[r.get(h, "") for h in heads] for r in t["rows"]]
            docs.append(Document(
                project=PROJECT, source_id="meal-hours", collection="meal_hours", title="학생식당 식사시간 안내",
                body="\n".join(" | ".join(r) for r in rows), url=t["source_url"], language="ko", content_level="body",
                source_type="repository_data", checked_at=datetime(2026, 11, 2, tzinfo=timezone.utc),
                metadata={"snapshot": snap}, chunks=table_row_chunks("학생식당 식사시간표", heads, rows, "hours"),
            ))
        for e in exp["events"]:
            sid = f"event:{e['course']}:{e['title']}:{e['start_date']}:{e['end_date']}"
            period = e["start_date"] if e["start_date"] == e["end_date"] else f"{e['start_date']} ~ {e['end_date']}"
            text = f"학사일정 {e['title']} | 과정: {e['course'] or '-'} | 기간: {period}"
            docs.append(Document(
                project=PROJECT, source_id=sid, collection="events", title=f"학사일정: {e['title']} ({e['course']})",
                body=text, url=e["source_url"], language="ko", content_level="body", source_type="repository_data",
                metadata={"start_date": e["start_date"], "end_date": e["end_date"], "course": e["course"],
                          "event_title": e["title"], "snapshot": snap},
                chunks=[Chunk("event", f"학사일정 > {e['title']}", text, {"start_date": e["start_date"], "end_date": e["end_date"]})],
            ))
        for n in exp["notices"]:
            docs.append(Document(
                project=PROJECT, source_id=f"notice:{n['post_id']}", collection="notices", title=n["title"], body=None,
                url=n["source_url"], language="ko", content_level="title_only", source_type="repository_data",
                published_at=date.fromisoformat(n["posted_on"]),
                metadata={"category": n["category"], "author": n["author"], "is_pinned": n["is_pinned"], "snapshot": snap},
                chunks=[Chunk("title", "공지 제목(본문 미수집)", n["title"])],
            ))
        docs.append(self._scholarship())
        return SyncBatch(docs, {"meals": "complete", "meal_hours": "complete", "events": "complete",
                                "notices": "complete", "scholarship": "complete"})

    def _scholarship(self) -> Document:
        html = (self.dir / "kopo_scholarship_4799.html").read_text(encoding="utf-8")
        t = parse_tables(html)[0]
        heads = [h.replace(" ", "") for h in t["headers"]]  # 구분, 종류, 수혜자격, 지급액및기간, 비고
        heads = ["구분", "종류", "수혜자격", "지급액 및 기간", "비고"] if len(heads) == 5 else heads
        intro = re.sub(r"<[^>]+>", " ", html[html.find('<h5'):html.find('<table')])
        intro = re.sub(r"\s+", " ", intro).strip()
        chunks = [Chunk("intro", "장학 > 소개", intro)]
        meta = [{"kind": r[1], "eligibility": r[2]} for r in t["rows"]]
        chunks += table_row_chunks("장학제도 표", heads, t["rows"], "row", meta)
        body = intro + "\n\n" + "\n".join(" | ".join(r) for r in t["rows"])
        return Document(
            project=PROJECT, source_id="kopo-4799-scholarship", collection="scholarship",
            title="한국폴리텍대학 춘천캠퍼스 장학제도", body=body, url=SCHOLARSHIP_URL, language="ko", content_level="body",
            source_type="public_original", checked_at=datetime(2026, 11, 17, 8, 26, tzinfo=timezone.utc),
            metadata={"caption": t["caption"]}, chunks=chunks,
        )

    # ── 라우팅 규칙 ─────────────────────────
    def classify(self, text: str, lang: str, ctx: dict, now: datetime) -> Part:
        low = text.lower()
        if has_any(low, ["식당", "학식", "식사", "cafeteria", "밥"]) and has_any(low, HOURS_TERMS):
            return Part("document", text, "meal_hours", collections=["meal_hours"], time_sensitive=True)
        if has_any(low, MEAL_TERMS) and not has_any(low, ["장학", "scholarship"]):
            meal = next((k for k, words in MEAL_WORDS.items() if has_any(low, words)), None)
            day = resolve_date(text, now) or seoul_now(now).date()
            if meal is None:
                q = "조식·중식·석식 중 어느 끼니를 알려드릴까요?" if lang == "ko" else "Which meal do you mean: breakfast, lunch or dinner?"
                return Part("clarify", text, "meal", clarify=q)
            return Part("structured", text, "meal", params={"date": day.isoformat(), "meal_type": meal})
        if has_any(low, ["학사일정", "일정", "schedule", "calendar"]) and (resolve_range(text, now) or resolve_date(text, now)):
            rng = resolve_range(text, now)
            if rng is None:
                d = resolve_date(text, now)
                rng = (d, d)
            return Part("structured", text, "events", params={"start": rng[0].isoformat(), "end": rng[1].isoformat()})
        if has_any(low, ["공지", "notice"]) and has_any(low, NOTICE_LIST_TERMS) and not has_any(low, DETAIL_TERMS):
            cat = next((c for c in NOTICE_CATEGORIES if c in text and c != "공지"), None)
            return Part("structured", text, "notice_list", params={"category": cat})
        return Part("document", text, "doc", needs_detail=has_any(low, DETAIL_TERMS), time_sensitive=has_any(low, TIME_TERMS))

    # ── 정형 조회 ───────────────────────────
    def run_structured(self, part: Part, store, now: datetime, lang: str) -> PartResult:
        if part.intent == "meal":
            return self._meal(part, store, lang)
        if part.intent == "events":
            return self._events(part, store, lang)
        if part.intent == "notice_list":
            return self._notice_list(part, store, lang)
        raise NotImplementedError(part.intent)

    def _meal(self, part: Part, store, lang: str) -> PartResult:
        p = part.params
        rows = store.structured_lookup(PROJECT, "meals", {"date": p["date"], "meal_type": p["meal_type"]},
                                       self.structured_keys["meals"])
        d = date.fromisoformat(p["date"])
        label = f"{fmt_day(d, lang)} {MEAL_KO[p['meal_type']] if lang == 'ko' else MEAL_EN[p['meal_type']]}"
        dbg = {"lookup": {"date": p["date"], "meal_type": p["meal_type"]}, "rows": len(rows)}
        if not rows:
            m = (f"{label} 식단 레코드가 없어요. 아직 수집되지 않았거나 공식 식단표에 없는 날짜예요. 다른 날짜 메뉴로 대신 알려드리지 않을게요."
                 if lang == "ko" else
                 f"There is no meal record for {label}. It may not be collected yet; I won't substitute another day's menu.")
            rel = [Citation("lolypoly:meals-page", "식단 정보 (공식 홈페이지)", MEALS_URL, "", "식단 페이지", None,
                            "repository_data", "해당 날짜 레코드 없음")]
            return PartResult("insufficient_evidence", message=m, related=rel, debug=dbg)
        r = rows[0]
        items = r["metadata"].get("items") or []
        ev = r | {"locator": f"식단 > {label}"}
        if not items:
            txt = (f"{label}은 공식 식단표에 메뉴가 비어 있어요(레코드는 수집됨)." if lang == "ko"
                   else f"{label}: the official menu is empty for this meal (the record exists).")
            return PartResult("answered", claims=[Claim(txt, [citation_from(ev, "(공식 식단표에 메뉴 없음)")])], debug=dbg)
        menu = ", ".join(items)
        txt = f"{label} 메뉴는 이렇게 나와요: {menu}" if lang == "ko" else f"{label} menu (Korean, as published): {menu}"
        return PartResult("answered", claims=[Claim(txt, [citation_from(ev, menu)])], debug=dbg)

    def _events(self, part: Part, store, lang: str) -> PartResult:
        s, e = date.fromisoformat(part.params["start"]), date.fromisoformat(part.params["end"])
        rows = store.date_overlap(PROJECT, "events", s, e)
        dbg = {"lookup": part.params, "rows": len(rows)}
        if not rows:
            m = f"{s}~{e} 기간의 학사일정 레코드가 없어요." if lang == "ko" else f"No academic calendar records for {s}~{e}."
            return PartResult("insufficient_evidence", message=m, debug=dbg)
        claims = []
        for r in rows[:12]:
            md = r["metadata"]
            period = md["start_date"] if md["start_date"] == md["end_date"] else f"{md['start_date']}~{md['end_date']}"
            line = f"- {md['event_title']} ({md['course'] or '-'}): {period}"
            claims.append(Claim(line, [citation_from(r | {"locator": f"학사일정 > {md['event_title']}"}, r["body"])]))
        return PartResult("answered", claims=claims, debug=dbg)

    def _notice_list(self, part: Part, store, lang: str) -> PartResult:
        cat = part.params.get("category")
        rows = store.documents(PROJECT, "notices")
        if cat:
            rows = [r for r in rows if r["metadata"].get("category") == cat or cat in r["title"]]
        rows.sort(key=lambda r: (r["published_at"] or date.min), reverse=True)
        if not rows:
            return PartResult("insufficient_evidence", message="조건에 맞는 공지 레코드가 없어요.", debug={"rows": 0})
        claims = [Claim(f"- {r['title']} ({r['published_at']})",
                        [citation_from(r | {"locator": "공지 제목(본문 미수집)"}, r["title"], "제목만 있음")]) for r in rows[:5]]
        return PartResult("answered", claims=claims, debug={"rows": len(rows)})


def detect_lang(text: str) -> str:
    return "ko" if textnorm.is_korean(text) else "en"
