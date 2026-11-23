"""롤리폴리(한국폴리텍대학 춘천캠퍼스 생활정보) 어댑터.

원본
- export.json : LOLYPOLY 공개 필드 export (Meal, AcademicEvent, Notice + 식사시간표). 유형 repository_data
  경로는 RAG_LOLYPOLY_EXPORT 로 바꿀 수 있다(LOLYPOLY `manage.py export_rag` 출력). 기본은 저장소의 data/lolypoly/export.json.
  각 레코드의 collected_at(원래 수집 시각)을 기준 시각으로 보여준다. export 의 수집 상태가 failed 인 컬렉션은
  이번 적재에서 삭제를 반영하지 않는다(마지막 성공 데이터 보존).
- data/lolypoly/kopo_scholarship_4799.html : 장학 페이지 공개 원문 일부. 유형 public_original
allowlist 밖(계정·커뮤니티·사진·택시방·학생 의견·버스)은 적재하지 않는다.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path

from ragcore import textnorm
from ragcore.adapter import DETAIL_TERMS, Adapter, Claim, Part, PartResult, SyncBatch, has_any
from ragcore.chunking import table_row_chunks
from ragcore.engine import citation_from
from ragcore.html_table import parse_tables

from ragcore.general import GeneralPolicy

from . import en_gloss as G
from ragcore.models import Chunk, Citation, Document
from ragcore.timeutil import SEOUL, fmt_day, resolve_date, resolve_range, seoul_now

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
EXPORT_COLLECTIONS = {"meals": "meals", "events": "events", "notices": "notices"}
# '금일 중식 없음'처럼 식단표가 그 끼니가 없다고 명시한 칸(메뉴가 아님)
EXPLICIT_NONE = re.compile(r"(없음|미운영|미제공|운영\s*안\s*함|운영하지\s*않|휴무|휴관|휴업)")
# 장학 표 비고의 적용 시점 규칙: '신입생은 2학기부터 적용'
TERM_RULE = re.compile(r"([가-힣]+?)(?:은|는)\s*(\d)\s*학기부터\s*적용")
TARGET_WORDS = {"신입생": ["신입생", "새내기", "1학년", "freshman", "freshmen", "new student", "new students", "first-year", "first year"]}
TARGET_ROW_HINTS = {"신입생": ["입학"]}   # 수혜자격에 '입학'이 든 행(예: 학과수석 입학자)은 신입생 대상 행
SEMESTER = [(re.compile(r"(\d)\s*학기"), None), (re.compile(r"첫\s*학기|first semester|1st semester", re.I), 1),
            (re.compile(r"second semester|2nd semester", re.I), 2)]
TIME_TERMS = ["마감", "운영시간", "운영 시간", "식사시간", "식사 시간", "몇 시", "몇시", "deadline", "hours", "what time"]


class LolypolyAdapter(Adapter):
    project = PROJECT
    allowed_collections = {"meals", "meal_hours", "events", "notices", "scholarship", "school_info"}
    structured_keys = {"meals": {"date", "meal_type"}}
    fresh_days = 30
    persona = ("You are the campus guide of 롤리폴리, a student app for 한국폴리텍대학 춘천캠퍼스. "
               "Talk like a kind senior student: short, clear and friendly.")  # 운영시간처럼 시점이 중요한 값: 확인 시각이 30일 이내인 근거만
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
        "work": ["근로"], "works": ["근로"], "working": ["근로"], "work-study": ["근로 장학금"], "college": ["대학", "학교"],
        "freshman": ["신입생", "입학"], "freshmen": ["신입생", "입학"], "new student": ["신입생"], "new students": ["신입생"],
        "first semester": ["1학기"], "second semester": ["2학기"], "academic excellence": ["성적우수"], "merit": ["성적우수"],
        "student council": ["학생회"], "contribution": ["공헌", "공로"], "welfare": ["복지"], "half": ["반액"],
        "waive": ["면제"], "waives": ["면제"], "one full year": ["1년간"], "one year": ["1년간"], "full year": ["1년간"],
        "two years": ["2년간"], "one semester": ["1개학기"], "2 year degree": ["2년제학위과정"], "two year degree": ["2년제학위과정"],
        "degree program": ["학위과정"], "graduation": ["학위수여식"], "commencement": ["학위수여식"], "exams": ["시험"], "final exams": ["기말시험"], "midterm exams": ["중간시험"],
        "practical exam": ["실기시험"], "written exam": ["필기시험"], "breakfast": ["조식"], "lunch": ["중식"], "dinner": ["석식"],
    }

    def __init__(self, data_dir: str | Path = "data/lolypoly", export_path: str | Path | None = None):
        self.dir = Path(data_dir)
        env = os.environ.get("RAG_LOLYPOLY_EXPORT", "").strip()
        self.export_path = Path(export_path or env or self.dir / "export.json")
        info = os.environ.get("RAG_LOLYPOLY_SCHOOL_INFO", "").strip()
        self.school_info_path = Path(info) if info else self.dir / "school_info.json"
        self.general_policy = lolypoly_general_policy(self._school_names())

    def _school_names(self) -> list[str]:
        """학교 정보 카드(검수 여부와 무관)의 학과 이름 — 일반 답변에 학교 고유명사가 나오면 버리기 위해."""
        try:
            card = json.loads(self.school_info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [d for it in card.get("items", []) for d in it.get("names", [])]

    # ── 적재 ───────────────────────────────
    def load(self) -> SyncBatch:
        exp = json.loads(self.export_path.read_text(encoding="utf-8"))
        prov = exp.get("provenance", {})
        commit = (prov.get("lolypoly_commit") or "?")[:7]
        source = prov.get("source", "fixture")
        captured = prov.get("fixture_captured_on")
        origin = {"fixture": "LOLYPOLY 저장소 fixture 재현", "fixture-modified": "재현용 변경 데이터(실제 아님)"}.get(
            source, "LOLYPOLY 수집 DB")
        status = _collection_status(prov)

        def snap(rec: dict) -> str:
            if source == "fixture" and captured:   # 저장본의 원래 수집일(시각 미상)만 표시한다
                return f"{origin} · 공식 홈페이지 {captured} 저장본 · lolypoly@{commit}"
            at = _kst(rec.get("collected_at"))
            return f"{origin} · 수집 {at} · lolypoly@{commit}" if at else f"{origin} · lolypoly@{commit}"

        docs: list[Document] = []
        for m in exp.get("meals", []):
            d = date.fromisoformat(m["date"])
            label = f"{fmt_day(d)} {MEAL_KO[m['meal_type']]}"
            menu = ", ".join(m["items"]) if m["items"] else "(공식 식단표에 메뉴 없음)"
            meta = {"date": m["date"], "meal_type": m["meal_type"], "items": m["items"], "snapshot": snap(m),
                    "collected_at": m.get("collected_at")}
            docs.append(Document(
                project=PROJECT, source_id=f"meal:{m['date']}:{m['meal_type']}", collection="meals",
                title=f"{label} 식단", body=menu, url=m["source_url"], language="ko", content_level="body",
                source_type="repository_data", checked_at=_dt(m.get("collected_at")), metadata=meta,
                chunks=[Chunk("meal", f"식단 > {label}", f"{label}: {menu}", {"date": m["date"], "meal_type": m["meal_type"]})],
            ))
        for t in exp.get("meal_hours", []):
            heads = t["headers"]
            rows = [[r.get(h, "") for h in heads] for r in t["rows"]]
            checked = _dt(t.get("collected_at")) or datetime(2026, 11, 2, tzinfo=timezone.utc)
            docs.append(Document(
                project=PROJECT, source_id="meal-hours", collection="meal_hours", title="학생식당 식사시간 안내",
                body="\n".join(" | ".join(r) for r in rows), url=t["source_url"], language="ko", content_level="body",
                source_type="repository_data", checked_at=checked,
                metadata={"snapshot": snap(t)}, chunks=table_row_chunks("학생식당 식사시간표", heads, rows, "hours"),
            ))
        for e in exp.get("events", []):
            sid = f"event:{e['course']}:{e['title']}:{e['start_date']}:{e['end_date']}"
            period = e["start_date"] if e["start_date"] == e["end_date"] else f"{e['start_date']} ~ {e['end_date']}"
            text = f"학사일정 {e['title']} | 과정: {e['course'] or '-'} | 기간: {period}"
            docs.append(Document(
                project=PROJECT, source_id=sid, collection="events", title=f"학사일정: {e['title']} ({e['course']})",
                body=text, url=e["source_url"], language="ko", content_level="body", source_type="repository_data",
                checked_at=_dt(e.get("collected_at")),
                metadata={"start_date": e["start_date"], "end_date": e["end_date"], "course": e["course"],
                          "event_title": e["title"], "snapshot": snap(e)},
                chunks=[Chunk("event", f"학사일정 > {e['title']}", text, {"start_date": e["start_date"], "end_date": e["end_date"]})],
            ))
        for n in exp.get("notices", []):
            docs.append(Document(
                project=PROJECT, source_id=f"notice:{n['post_id']}", collection="notices", title=n["title"], body=None,
                url=n["source_url"], language="ko", content_level="title_only", source_type="repository_data",
                published_at=date.fromisoformat(n["posted_on"]), checked_at=_dt(n.get("collected_at")),
                metadata={"category": n["category"], "author": n["author"], "is_pinned": n["is_pinned"], "snapshot": snap(n)},
                chunks=[Chunk("title", "공지 제목(본문 미수집)", n["title"])],
            ))
        docs.append(self._scholarship())
        docs += self._school_info_docs()
        cols = {c: ("complete" if status.get(c, "success") == "success" and c in exp else "failed") for c in EXPORT_COLLECTIONS}
        # v0.6.0: 롤리폴리 export_rag 가 식사시간표를 내보낸다(LOLYPOLY ERR-015). 식단 수집 실패나 빈 목록이면 삭제를 반영하지 않음
        hours_ok = status.get("meal_hours", status.get("meals", "success")) == "success"
        cols["meal_hours"] = "complete" if exp.get("meal_hours") and hours_ok else "failed"
        cols["scholarship"] = "complete"
        cols["school_info"] = "complete"     # 검수 전이면 문서 0개 → 이전에 적재된 카드도 지워진다(검수 철회 반영)
        return SyncBatch(docs, cols)

    # ── v0.6.0 학교 기본 정보 카드 ─────────────────
    def _card(self) -> dict | None:
        """scripts/fetch_school_info.py 가 만든 카드. 사람이 needs_review=false 로 바꾼 것만 쓴다(원문 수집 도구 규칙)."""
        try:
            card = json.loads(self.school_info_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return None if card.get("needs_review", True) else card

    def _school_info_docs(self) -> list[Document]:
        card = self._card()
        if not card:
            return []
        checked = _dt(card.get("reviewed_at") or None) or datetime.now(timezone.utc)
        out = []
        for it in card["items"]:
            if not it.get("text"):
                continue                        # 확인하지 못한 항목은 적재하지 않는다(답할 때 '미확인'으로 안내)
            out.append(Document(
                project=PROJECT, source_id=f"school-info:{it['key']}", collection="school_info",
                title=f"{card['campus']} 기본 정보: {it['label']}", body=it["text"], url=it["url"], language="ko",
                content_level="body", source_type="public_original", checked_at=checked,
                metadata={"key": it["key"], "snapshot": f"공식 홈페이지 확인 {card['checked_at']} · 사람 검수 {card.get('reviewed_at', '?')}"},
                chunks=[Chunk("card", f"학교 기본 정보 > {it['label']}", it["text"], {"key": it["key"]})],
            ))
        return out

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
            # v0.5.0: 식사시간표 행을 그대로 답한다(모델 0회). 표가 오래됐으면 None → 문서 경로가 시점 보류를 판단
            return Part("structured", text, "meal_hours", collections=["meal_hours"], time_sensitive=True)
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
        if has_any(low, ["장학", "scholarship"]):
            target = next((t for t, words in TARGET_WORDS.items() if has_any(low, words)), None)
            sem = _semester(text)
            if target and sem:
                return Part("structured", text, "scholarship_term", params={"target": target, "semester": sem})
            # v0.5.0: 질문이 장학표의 한 행(종류·수혜자격·지급액)을 가리키면 그 행으로 답한다. 못 고르면 문서 검색
            return Part("structured", text, "scholarship_row", needs_detail=has_any(low, DETAIL_TERMS))
        key = _card_key(low)
        if key:
            # v0.6.0 학교 기본 정보 카드(주소·연락처·학과·건물·이메일). 검수된 카드가 없으면 None → 문서 검색 → 보류
            return Part("structured", text, "school_info", params={"key": key}, collections=["school_info"])
        if has_any(low, WHEN_TERMS) and not has_any(low, ["공지", "notice"]):
            # v0.5.0: '○○ 언제야?' — 학사일정 제목과 맞는 행을 날짜와 함께 답한다. 못 고르면 문서 검색
            return Part("structured", text, "event_name")
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
        if part.intent == "scholarship_term":
            return self._scholarship_term(part, store, lang)
        if part.intent == "scholarship_row":
            return self._scholarship_row(part, store, lang)
        if part.intent == "event_name":
            return self._event_name(part, store, now, lang)
        if part.intent == "meal_hours":
            return self._meal_hours(part, store, now, lang)
        if part.intent == "school_info":
            return self._school_info(part, store, lang)
        raise NotImplementedError(part.intent)

    def _school_info(self, part: Part, store, lang: str) -> PartResult | None:
        card = self._card()
        rows = store.chunks(PROJECT, "school_info")
        if not card or not rows:
            return None
        key = part.params["key"]
        keys = ["departments", "departments_location_page"] if key == "departments" else (
            ["phone", "admission_phone"] if key == "phone" else [key])
        hit = [r for r in rows if (r["metadata"] or {}).get("key") in keys]
        hit.sort(key=lambda r: keys.index(r["metadata"]["key"]))
        item = next((it for it in card["items"] if it["key"] == key), None)
        if not hit:
            label = item["label"] if item else key
            why = (item or {}).get("missing_reason", "")
            m = (f"학교 기본 정보 카드의 ‘{label}’은(는) 공식 홈페이지에서 아직 확인하지 못한 항목이라 답할 수 없어요. ({why})" if lang == "ko"
                 else f"‘{label}’ is not confirmed on the official website yet, so I can't answer it.")
            return PartResult("insufficient_evidence", message=m, debug={"school_info": key, "missing": True})
        claims = []
        for r in hit:
            lab = r["locator"].split(" > ", 1)[-1]
            txt = (f"{lab}: 공식 홈페이지에는 “{r['text']}”라고 나와 있어요." if lang == "ko"
                   else f"{CARD_LABEL_EN.get((r['metadata'] or {}).get('key'), lab)} — the official website says: “{r['text']}”.")
            claims.append(Claim(txt, [citation_from(r, r["text"], "학교 기본 정보 카드(공식 원문, 사람 검수)")]))
        return PartResult("answered", claims=claims, debug={"school_info": key, "rows": len(hit)})

    def _scholarship_row(self, part: Part, store, lang: str) -> PartResult | None:
        """장학표에서 질문과 가장 많이 겹치는 행(종류·수혜자격·지급액, 별칭 확장)을 고른다.
        최고 점수 2 이상, 동점 행이 2개 이하일 때만 답하고 그 밖에는 None(문서 검색). 행끼리 섞지 않는다."""
        q = _content_tokens(textnorm.expand_query(part.text, self.aliases))
        rows = [r for r in store.chunks(PROJECT, "scholarship") if (r["structured"] or {}).get("cells")]
        # 질문에 숫자 조건(2.5, 3.0, 1년간 …)이 있으면 그 값이 든 행만 후보(비고 열 포함). 없으면 정형 답을 만들지 않음
        from ragcore.citations import key_values

        vals = [v for v in key_values(part.text) if v]
        if vals:
            rows = [r for r in rows if all(v in r["text"] for v in vals)]
            if not rows:
                return None
        scored = []
        for r in rows:
            c = r["structured"]["cells"]
            toks = _content_tokens(textnorm.tokens(" ".join([c.get("종류", ""), c.get("수혜자격", ""), c.get("지급액 및 기간", "")])))
            scored.append((len(q & toks), r))
        best = max((sc for sc, _ in scored), default=0)
        top = [r for sc, r in scored if sc == best]
        # 점수 1이어도, 겹친 말이 장학 '종류' 이름(근로·부사관·보훈 …)이고 그 행 하나뿐이면 그 행으로 답한다
        kind_hit = best == 1 and len(top) == 1 and (bool(vals) or bool(
            q & _content_tokens(textnorm.tokens(top[0]["structured"]["cells"].get("종류", "")))))
        if (best < 2 and not kind_hit) or len(top) > 2:
            return None
        yes = _is_yes_no(part.text)
        claims = []
        for r in top:
            c = r["structured"]["cells"]
            amount, note = c.get("지급액 및 기간", ""), c.get("비고", "")
            if lang == "ko":
                head = "네, " if yes and not claims else ""
                body = "별도 규정에 따라 지급돼요" if amount == "별도 규정" else f"{copula(amount)}"
                txt = f"{head}{c['종류']}(‘{c['수혜자격']}’)는 {body}." + (f" 비고: {note}." if note else "")
            else:
                head = "Yes. " if yes and not claims else ""
                txt = (f"{head}{G.gloss(c['종류'], G.SCHOLARSHIP_KIND)} — eligibility: {G.gloss_pattern(c['수혜자격'], ())}"
                       f"{_en_paren(c['수혜자격'], G.ELIGIBILITY)}; benefit: {G.gloss_pattern(amount, G.AMOUNT_PATTERNS)}"
                       + (f"; note: {G.gloss_pattern(note, G.NOTE_PATTERNS)}." if note else "."))
            claims.append(Claim(txt, [citation_from(r, r["text"], "표 행(서버 조회)")]))
        return PartResult("answered", claims=claims, debug={"rows": [r["locator"] for r in top], "score": best})

    def _event_name(self, part: Part, store, now: datetime, lang: str) -> PartResult | None:
        """학사일정 제목·과정과 질문 내용어가 가장 많이 겹치는 일정을 날짜와 함께 답한다(앞으로 올 일정 먼저, 최대 5개).
        질문 내용어의 절반 이상이 맞고 점수 2 이상일 때만, 아니면 None(문서 검색)."""
        q = _content_tokens(textnorm.expand_query(part.text, self.aliases)) - WHEN_TOKENS
        if not q:
            return None
        rows = store.documents(PROJECT, "events")
        scored = []
        for r in rows:
            md = r["metadata"]
            course = md.get("course", "") or ""
            # '2년제학위과정'처럼 숫자로 시작하는 과정명은 원형과 '2년제 학위과정'으로 나눈 형태를 함께 비교한다
            text = f"{md.get('event_title', '')} {course} {re.sub(r'^(\d+년제)', r'\1 ', course)}"
            toks = _content_tokens(textnorm.tokens(text))
            scored.append((len(q & toks), r))
        best = max((sc for sc, _ in scored), default=0)
        if best < 2 or best < len({t for t in q if not _is_bigram_of(t, q)}) / 2:
            return None
        today = seoul_now(now).date()
        top = [r for sc, r in scored if sc == best]
        top.sort(key=lambda r: (r["metadata"]["end_date"] < today.isoformat(), r["metadata"]["start_date"]))
        claims = []
        for r in top[:5]:
            md = r["metadata"]
            period = md["start_date"] if md["start_date"] == md["end_date"] else f"{md['start_date']}~{md['end_date']}"
            past = md["end_date"] < today.isoformat()
            mark = (" (지난 일정)" if lang == "ko" else " (past)") if past else ""
            line = (f"- {md['event_title']} ({md['course'] or '-'}): {period}{mark}" if lang == "ko" else
                    f"- {G.gloss(md['event_title'], G.EVENT)} — {G.gloss(md['course'] or '-', G.COURSE)}: {period}{mark}")
            claims.append(Claim(line,
                                [citation_from(r | {"locator": f"학사일정 > {md['event_title']}"},
                                               f"학사일정 {md['event_title']} | 과정: {md['course'] or '-'} | 기간: {period.replace('~', ' ~ ')}")]))
        return PartResult("answered", claims=claims, debug={"matched": len(top), "score": best})

    def _meal_hours(self, part: Part, store, now: datetime, lang: str) -> PartResult | None:
        rows = store.chunks(PROJECT, "meal_hours")
        if not rows:
            return None
        checked = rows[0].get("checked_at")
        if not checked or (now - checked).days > self.fresh_days:
            return None   # 오래된 시간표 → 문서 경로가 '시점 확인 불가'로 보류
        claims = []
        en = {"아침": "breakfast", "점심": "lunch", "저녁": "dinner", "주중": "weekdays", "주말": "weekends", "구분": "type"}
        for r in rows:
            # 열 순서는 원문 그대로(조각 원문 '[표] 구분: 주중 | 아침: … | 점심: …')에서 읽는다(JSON 저장은 키 순서를 바꿈)
            pairs = [seg.split(": ", 1) for seg in r["text"].split("] ", 1)[-1].split(" | ") if ": " in seg]
            if not pairs:
                continue
            label = pairs[0][1]
            rest = [(k, v) for k, v in pairs[1:] if v]
            if lang == "ko":
                txt = f"학생식당 {label}: " + ", ".join(f"{k} {v}" for k, v in rest)
            else:
                txt = f"Student cafeteria ({en.get(label, label)}): " + ", ".join(f"{en.get(k, k)} {v}" for k, v in rest)
            claims.append(Claim(txt, [citation_from(r, r["text"], "식사시간표(확인 시각 기준)")]))
        return PartResult("answered", claims=claims, debug={"rows": len(claims)}) if claims else None

    def _scholarship_term(self, part: Part, store, lang: str) -> PartResult | None:
        """장학 표에서 '대상은 N학기부터 적용' 규칙이 있는 행을 찾아, 질문의 대상·학기와 같은 행의 금액·조건으로 답한다.
        규칙 행이 없으면 None → 엔진이 문서 검색으로 처리한다(모델이 판단)."""
        target, sem = part.params["target"], part.params["semester"]
        rows = [r for r in store.chunks(PROJECT, "scholarship") if (r["structured"] or {}).get("cells")]
        q = "".join(textnorm.expand_query(part.text, self.aliases))
        kinds = {r["structured"]["cells"].get("종류", "") for r in rows}
        named = [k for k in kinds if k and (k.replace(" ", "") in part.text.replace(" ", "") or
                                            textnorm.normalize(k.split()[0]) in q)]
        rule_rows = []
        for r in rows:
            cells = r["structured"]["cells"]
            if named and cells.get("종류") not in named:
                continue
            m = next((m for m in TERM_RULE.finditer(cells.get("비고", "")) if m.group(1) == target), None)
            if m:
                rule_rows.append((r, int(m.group(2)), m.group(0)))
        if not rule_rows:
            return None
        claims = []
        for r, start, rule in rule_rows:
            c = r["structured"]["cells"]
            ev = r | {"locator": r["locator"]}
            ok = sem >= start
            if lang == "ko":
                txt = (f"네, {c['종류']}(‘{c['수혜자격']}’, {c['지급액 및 기간']})는 {target}도 {start}학기부터 적용돼서 "
                       f"{sem}학기에는 대상이 될 수 있어요. 비고: “{c['비고']}”." if ok else
                       f"아니요, {c['종류']}(‘{c['수혜자격']}’, {c['지급액 및 기간']})는 {target}의 경우 {start}학기부터 적용돼요. "
                       f"비고: “{c['비고']}”.")
            else:
                head = "Yes" if ok else "No"
                txt = (f"{head}. For the {G.gloss(c['종류'], G.SCHOLARSHIP_KIND)} row ‘{c['수혜자격']}’"
                       f"{_en_paren(c['수혜자격'], G.ELIGIBILITY)}, the table says {target} (new students) are eligible "
                       f"from semester {start} (benefit: {G.gloss_pattern(c['지급액 및 기간'], G.AMOUNT_PATTERNS)}; "
                       f"note: {G.gloss_pattern(c['비고'], G.NOTE_PATTERNS)}).")
            claims.append(Claim(txt, [citation_from(ev, r["text"], "표 행 규칙(서버 판정)")]))
        # 같은 장학 종류에서 대상(예: 입학자)에 해당하는 다른 행은 학기 규칙 없이 그대로 덧붙인다(행을 섞지 않음)
        used = {r["chunk_id"] for r, _, _ in rule_rows}
        kinds_used = {r["structured"]["cells"]["종류"] for r, _, _ in rule_rows}
        for r in rows:
            c = r["structured"]["cells"]
            if r["chunk_id"] in used or c.get("종류") not in kinds_used:
                continue
            if any(h in c.get("수혜자격", "") for h in TARGET_ROW_HINTS.get(target, [])):
                txt = (f"같은 {c['종류']}의 ‘{c['수혜자격']}’ 행은 {copula(c['지급액 및 기간'])}(비고: {c['비고'] or '없음'})."
                       if lang == "ko" else
                       f"The separate {G.gloss(c['종류'], G.SCHOLARSHIP_KIND)} row ‘{c['수혜자격']}’{_en_paren(c['수혜자격'], G.ELIGIBILITY)} "
                       f"gives {G.gloss_pattern(c['지급액 및 기간'], G.AMOUNT_PATTERNS)} (note: {G.gloss_pattern(c['비고'], G.NOTE_PATTERNS) if c['비고'] else '-'}).")
                claims.append(Claim(txt, [citation_from(r, r["text"], "같은 표의 다른 행")]))
        return PartResult("answered", claims=claims, debug={"rule_rows": [r["locator"] for r, _, _ in rule_rows], "semester": sem})

    def _meal(self, part: Part, store, lang: str) -> PartResult:
        p = part.params
        rows = store.structured_lookup(PROJECT, "meals", {"date": p["date"], "meal_type": p["meal_type"]},
                                       self.structured_keys["meals"])
        d = date.fromisoformat(p["date"])
        label = f"{fmt_day(d, lang)} {MEAL_KO[p['meal_type']] if lang == 'ko' else MEAL_EN[p['meal_type']]}"
        dbg = {"lookup": {"date": p["date"], "meal_type": p["meal_type"]}, "rows": len(rows)}
        if not rows:
            cover = _meal_coverage(store)
            last = cover.get("last_collected")
            rng = f"{cover['first']}~{cover['last']}" if cover.get("first") else "없음"
            if lang == "ko":
                m = (f"{label} 식단 레코드가 없어요. 아직 수집되지 않았거나 공식 식단표에 없는 날짜예요"
                     f"(수집된 식단 범위: {rng}, 마지막 확인: {last or '기록 없음'}). "
                     "다른 날 메뉴로 대신 알려드리지 않을게요. 공식 식단 페이지에서 확인해 주세요.")
            else:
                m = (f"No meal data for {label} yet (collected range: {rng}, last checked: {last or 'unknown'}). "
                     "I won't substitute another day's menu. Please check the official meal page.")
            rel = [Citation("lolypoly:meals-page", "식단 정보 (공식 홈페이지)", MEALS_URL, "", "식단 페이지",
                            f"마지막 확인 {last}" if last else None, "repository_data", "해당 날짜 자료 없음 · 공식 식단 경로")]
            return PartResult("insufficient_evidence", message=m, related=rel, debug=dbg | {"coverage": cover})
        r = rows[0]
        items = r["metadata"].get("items") or []
        ev = r | {"locator": f"식단 > {label}"}
        joined = ", ".join(items)
        if items and len(items) <= 2 and EXPLICIT_NONE.search(joined):
            txt = (f"{label}은 공식 식단표에 “{joined}”라고 나와 있어요. 이날은 {MEAL_KO[p['meal_type']]}이 없어요." if lang == "ko"
                   else f"The official menu says “{joined}” for {label}: there is no {MEAL_EN[p['meal_type']]} that day.")
            return PartResult("answered", claims=[Claim(txt, [citation_from(ev, joined, "식단표 명시: 없음")])],
                              debug=dbg | {"explicit_none": True})
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
            line = (f"- {md['event_title']} ({md['course'] or '-'}): {period}" if lang == "ko" else
                    f"- {G.gloss(md['event_title'], G.EVENT)} — {G.gloss(md['course'] or '-', G.COURSE)}: {period}")
            claims.append(Claim(line, [citation_from(r | {"locator": f"학사일정 > {md['event_title']}"}, r["body"])]))
        return PartResult("answered", claims=claims, debug=dbg)

    def _notice_list(self, part: Part, store, lang: str) -> PartResult:
        cat = part.params.get("category")
        rows = store.documents(PROJECT, "notices")
        if cat:
            rows = [r for r in rows if r["metadata"].get("category") == cat or cat in r["title"]]
        rows.sort(key=lambda r: (r["published_at"] or date.min), reverse=True)
        if not rows:
            return PartResult("insufficient_evidence", message="조건에 맞는 공지 레코드가 없어요." if lang == "ko"
                              else "No notice records match this.", debug={"rows": 0})
        claims = [Claim(f"- {r['title']} ({r['published_at']})",
                        [citation_from(r | {"locator": "공지 제목(본문 미수집)"}, r["title"], "제목만 있음")]) for r in rows[:5]]
        return PartResult("answered", claims=claims, debug={"rows": len(rows)})


def detect_lang(text: str) -> str:
    return "ko" if textnorm.is_korean(text) else "en"


WHEN_TERMS = ["언제", "며칠", "날짜", "기간", "when ", "what date", "which date", "date of"]
# 질문 내용어에서 뺄 일반어(어떤 행·일정을 고르는 데 도움이 안 되는 말). 조사·불용어는 textnorm 이 이미 뺀다
_GENERIC = {"장학", "장학금", "학금", "교내", "교외", "받아", "받을", "받는", "혜택", "얼마", "얼마나", "있어", "학생", "대상",
            "언제", "언제야", "일정", "학사일정", "날짜", "기간", "며칠", "알려줘", "scholarship", "scholarships", "when", "date",
            "students", "student", "get", "there", "college", "program", "학교"}
WHEN_TOKENS = {"언제", "언제야", "며칠", "날짜", "when", "date"}


def _content_tokens(toks) -> set[str]:
    return {t for t in toks if len(t) >= 2 and t not in _GENERIC and t not in textnorm.QUERY_STOPWORDS}


def _is_bigram_of(tok: str, toks: set[str]) -> bool:
    return len(tok) == 2 and any(len(o) > 2 and tok in o for o in toks)


def _is_yes_no(text: str) -> bool:
    low = text.strip().lower()
    return bool(re.search(r"(있어|있나요|있을까|되나요|돼\?|되니|수 있어|받을 수|가능)", text)
                or re.match(r"^(is|are|can|do|does|will)\b", low))


def copula(word: str) -> str:
    """받침에 맞춰 '이에요/예요'를 붙인다."""
    last = (word or "").rstrip()[-1:]
    if "가" <= last <= "힣":
        return f"{word}{'이에요' if (ord(last) - 0xAC00) % 28 else '예요'}"
    return f"{word}이에요"


def _semester(text: str) -> int | None:
    for rx, fixed in SEMESTER:
        m = rx.search(text)
        if m:
            return fixed or int(m.group(1))
    return None


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    d = datetime.fromisoformat(v)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _kst(v: str | None) -> str | None:
    d = _dt(v)
    return f"{d.astimezone(SEOUL):%Y-%m-%d %H:%M} KST" if d else None


def _collection_status(prov: dict) -> dict[str, str]:
    """export 의 컬렉션별 마지막 수집 결과(success/failed). v1(collection_runs)·v2(collections) 둘 다 읽는다."""
    src = prov.get("collections") or prov.get("collection_runs") or {}
    return {k: (v.get("last_run_status") or v.get("status") or "success") for k, v in src.items()}


def _meal_coverage(store) -> dict:
    rows = store.documents(PROJECT, "meals")
    if not rows:
        return {}
    dates = sorted(r["metadata"]["date"] for r in rows)
    collected = [r["checked_at"] for r in rows if r.get("checked_at")]
    last = max(collected) if collected else None
    return {"first": dates[0], "last": dates[-1],
            "last_collected": f"{last.astimezone(SEOUL):%Y-%m-%d %H:%M} KST" if last else None}


def _en_paren(value: str, table: dict) -> str:
    """영어 답에서 한국어 원문 뒤에 용어집 설명을 괄호로 붙인다(없으면 빈 문자열)."""
    en = table.get((value or "").strip())
    return f" ({en})" if en else ""


# ── v0.6.0 일반 답변 정책(B안) ─────────────────────────
# 기본값 제안: 켬. 학생 앱이라 '파이썬 리스트와 튜플 차이' 같은 학습·일반 질문이 들어오고, 학교 사실은 아래 용어로 막는다.
# 끄기: RAG_GENERAL_LOLYPOLY=0
LOLYPOLY_DOMAIN_TERMS = [
    "학교", "캠퍼스", "대학", "폴리텍", "kopo", "춘천", "롤리폴리", "기숙사", "생활관", "등록금", "학비", "교육비", "장학", "학사", "식단", "학식",
    "메뉴", "식당", "조식", "중식", "석식", "기말시험", "중간시험", "기말고사", "중간고사", "기말평가", "중간평가", "수강", "개강", "종강", "방학",
    "졸업", "학위", "교수", "학과", "학생회", "도서관", "통학버스", "셔틀", "강의실", "성적", "휴학", "복학", "입학", "원서", "공지", "학번",
    "총장", "학장", "조교", "행정실", "교무", "실습", "현장실습", "자격증", "취업", "축제", "동아리",
    "school", "campus", "college", "university", "polytech", "dorm", "dormitory", "tuition", "scholarship", "professor",
    "library", "cafeteria", "semester", "enrollment", "admission", "graduation", "exam", "exams", "department", "major",
]


def lolypoly_general_policy(school_names: list[str]) -> GeneralPolicy:
    return GeneralPolicy(
        enabled=os.environ.get("RAG_GENERAL_LOLYPOLY", "1").strip() != "0",
        tone="You are a friendly senior student helping a college student. Talk kindly and briefly.",
        scope="general study, technology, science or everyday-life knowledge (not about any school)",
        max_chars=320,
        banned_topics=[r"성적\s*(조작|위조)", r"대리\s*(출석|시험)", r"커닝|부정행위\s*방법"],
        domain_terms=LOLYPOLY_DOMAIN_TERMS + school_names,
        smalltalk={
            "greet": {"ko": "안녕하세요! 롤리폴리 안내예요. 식단·학사일정·장학처럼 학교 공개 자료로 확인되는 내용을 출처와 함께 알려 드려요.",
                      "en": "Hi! I'm the Lolypoly guide. I answer from the school's public data (meals, academic calendar, scholarships) with sources."},
            "thanks": {"ko": "도움이 됐다니 다행이에요. 또 궁금한 게 있으면 물어봐 주세요.",
                       "en": "Glad it helped. Ask me anything else anytime."},
            "help": {"ko": "이렇게 물어보세요: \"11월 10일 점심 뭐야?\", \"기말시험 언제야?\", \"근로 장학금 조건 알려줘\". 답에는 출처가 붙고, "
                           "자료에 없는 학교 정보는 지어내지 않고 '찾지 못했어요'라고 답해요.",
                     "en": "Try: \"What's for lunch on Nov 10?\", \"When are final exams?\", \"Work-study scholarship conditions\". "
                           "Answers come with sources; school facts that aren't in the data are never made up."},
        })


# ── v0.6.0 학교 기본 정보 카드 질문 판별 ─────────────────
_SCHOOLISH = ["학교", "캠퍼스", "대학", "폴리텍", "school", "campus", "college"]
CARD_LABEL_EN = {"address": "Campus address", "phone": "Main phone / fax", "admission_phone": "Admissions phone",
                 "departments": "Departments by program", "departments_location_page": "Departments (location page)"}


def _card_key(low: str) -> str | None:
    if has_any(low, ["이메일", "메일 주소", "email", "e-mail"]):
        return "email"
    if has_any(low, ["건물", "본관", "강의동", "몇 동", "building"]):
        return "buildings"
    if has_any(low, ["어떤 학과", "무슨 학과", "학과들", "학과 목록", "학과가 있", "학과 알려", "departments", "what majors", "which majors"]):
        return "departments"
    if has_any(low, _SCHOOLISH) and has_any(low, ["주소", "위치", "어디에 있", "address", "location", "where is"]):
        return "address"
    if has_any(low, _SCHOOLISH) and has_any(low, ["전화", "연락처", "대표 번호", "대표번호", "팩스", "phone", "contact", "fax"]):
        return "phone"
    return None
