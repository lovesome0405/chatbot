"""MARU(외국인 대상 서울 전통문화 안내) 어댑터.

원본 (lovesome0405/ari 커밋 data/maru/ARI_COMMIT)
- ari_culture_resources_appjs.json : 장소 29곳 (앱 데이터, 공식 출처 재검증 전 → repository_data)
- data/courses.json : 코스 6개와 코스별 장소 순서
- data/heritage.json : 해설 키워드
- data/maru/synthetic_*.json : 합성 테스트 데이터(화면·인용에 [합성] 표시)
본문은 한국어 필드로 색인한다(영어 질문도 한국어 근거를 검색). 영어 이름은 제목·별칭으로만 쓴다.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

from ragcore import textnorm
from ragcore.adapter import DETAIL_TERMS, TIME_SENSITIVE_TERMS, Adapter, Claim, Part, PartResult, SyncBatch, has_any
from ragcore.engine import citation_from
from ragcore.models import Chunk, Document

PROJECT = "maru"
GITHUB = "https://github.com/lovesome0405/ari/blob/{commit}/{path}"
COURSE_REF = ["이 코스", "이코스", "이 루트", "이 경로", "이 동선", "this course", "this route", "this tour", "on this route",
              "on this course"]
PLACE_REF = ["여기", "이곳", "이 곳", "거기", "그곳", "이 장소", "this place", "here", "there"]
RANKING_TERMS = ["추천 순위", "인기 코스", "인기 순위", "순위", "top routes", "top courses", "ranking", "most popular",
                 "recommended routes", "recommended courses"]


class MaruAdapter(Adapter):
    project = PROJECT
    allowed_collections = {"places", "courses", "notices"}
    fresh_days = 0  # 가격·운영시간·개방 여부는 적용 기간이 명시된 근거만 인정
    base_aliases = {
        "palace": ["궁궐", "궁"], "palaces": ["궁궐", "궁"], "royal": ["왕실"], "king": ["왕", "왕실"], "joseon": ["조선"],
        "ritual": ["의례", "의식"], "rituals": ["의례", "의식"], "ceremony": ["의례", "의식"], "ceremonies": ["의례", "의식"],
        "museum": ["박물관"], "market": ["시장"], "markets": ["시장"], "street food": ["시장", "미식"], "food": ["미식", "음식", "시장"],
        "hanok": ["한옥"], "temple": ["사찰", "절"], "buddhist": ["불교", "사찰"], "craft": ["공예"], "crafts": ["공예"],
        "rain": ["비 오는 날", "우천", "실내"], "rainy": ["비 오는 날", "우천", "실내"], "indoor": ["실내"], "night": ["야간"],
        "evening": ["야간"], "walk": ["걷기", "산책"], "walking": ["걷기", "도보"], "photo": ["사진"], "tomb": ["왕릉", "무덤"],
        "tombs": ["왕릉", "고분"], "shrine": ["종묘", "사당"], "wall": ["성곽", "성벽"], "fortress": ["성곽"],
        "gate": ["문"], "guard": ["수문장"], "changing of the guard": ["수문장 교대"], "special opening": ["특별 개방"], "geunjeongjeon": ["근정전"], "terrace": ["월대"],
        "woldae": ["월대"], "restricted": ["제한"], "restriction": ["제한"], "go up": ["출입"], "access": ["출입"],
        "opening": ["개방"], "performance": ["공연"], "traditional music": ["국악"], "independence": ["독립"],
        "prison": ["형무소"], "history": ["역사"], "folk": ["민속"], "village": ["마을"], "first visit": ["첫 방문"],
        "first time": ["첫 방문", "처음"], "의식": ["의례"], "궁": ["궁궐"], "식사시간": ["식사 시간", "점심 휴식"],
    }

    def __init__(self, data_dir: str | Path = "data/maru"):
        self.dir = Path(data_dir)
        self.commit = (self.dir / "ARI_COMMIT").read_text().strip()
        self._places: dict[str, dict] = {}
        self._courses: dict[str, dict] = {}
        self.aliases = dict(self.base_aliases)
        self._index_ids()

    def _read(self, name):
        return json.loads((self.dir / name).read_text(encoding="utf-8"))

    def _index_ids(self):
        for r in self._read("ari_culture_resources_appjs.json"):
            self._places[r["id"]] = r
        for c in self._read("courses.json"):
            self._courses[c["id"]] = c
            for p in c["places"]:
                self._places.setdefault(p["id"], {"id": p["id"], "nameKo": p["name"]["ko"], "nameEn": p["name"]["en"],
                                                  "_course_place": p})
        for pid, r in self._places.items():
            if r.get("nameEn"):
                en = r["nameEn"].lower()
                self.aliases[en] = [r["nameKo"]]
                short = re.sub(r"\b(palace|museum|village|market|temple|gate|square|road|street|theater|theatre|hall|of korea|national)\b",
                               "", en).strip()
                if len(short) >= 4 and short not in self.aliases:
                    self.aliases[short] = [r["nameKo"]]
        for cid, c in self._courses.items():
            self.aliases[c["title"]["en"].lower()] = [c["title"]["ko"]]

    # ── 적재 ───────────────────────────────
    def load(self) -> SyncBatch:
        heritage = {h["id"]: h for h in self._read("heritage.json")}
        snap = f"MARU 저장소 데이터 ari@{self.commit[:7]} (공식 출처 재검증 전)"
        docs: list[Document] = []
        for pid, r in self._places.items():
            if "_course_place" in r:
                p = r["_course_place"]
                paras = [f"{p['name']['ko']} ({p['name']['en']})", f"주소: {p.get('address', '')}", p["description"]["ko"],
                         f"자료 출처 표기: {p.get('publicDataSource', '미표기')}"]
                path = "data/courses.json"
            else:
                paras = [
                    f"{r['nameKo']} ({r['nameEn']}) — {r.get('category', '')} / {r.get('district', '')}",
                    f"주소: {r.get('address', '')}",
                    r.get("aiSimpleExplanation", ""),
                    f"의미: {r.get('aiWhyItMatters', '')}",
                    f"방문 팁: {r.get('aiVisitTip', '')}",
                    f"실내/실외: {r.get('indoorOutdoor', '')}, 걷기 난이도: {r.get('walkingLevel', '')}",
                ]
                path = "ari_culture_resources_appjs.json"
            if pid in heritage:
                h = heritage[pid]
                paras.append(f"해설 키워드: {', '.join(h.get('interpretationKeywords', []))}. 해설 역할: {h.get('aiInterpretationRole', '')}")
            paras = [x for x in paras if x and not x.endswith(": ")]
            title = f"{r['nameKo']} ({r['nameEn']})"
            docs.append(Document(
                project=PROJECT, source_id=f"place:{pid}", collection="places", title=title, body="\n\n".join(paras),
                url=GITHUB.format(commit=self.commit, path=path), language="ko", content_level="body",
                source_type="repository_data", metadata={"place_id": pid, "snapshot": snap},
                chunks=[Chunk(f"p{i:02d}", f"{title} > 문단 {i}", t) for i, t in enumerate(paras, start=1)],
            ))
        for cid, c in self._courses.items():
            order = [p["id"] for p in c["places"]]
            names = " → ".join(p["name"]["ko"] for p in c["places"])
            paras = [
                f"{c['title']['ko']} ({c['title']['en']}): {c['aiSummary']['ko']}",
                f"코스 순서: {names}",
                f"추천 이유: {c['reason']['ko']}",
                f"팁: {c['tip']['ko']}",
                "키워드: " + "; ".join(f"{k['name']} — {k['description']['ko']}" for k in c.get("keywords", [])),
                f"소요 시간: {c.get('duration', '')}, 걷기: {c['walking']['ko']}, 비용 수준: {c['fee']['ko']}",
            ]
            docs.append(Document(
                project=PROJECT, source_id=f"course:{cid}", collection="courses", title=f"{c['title']['ko']} ({c['title']['en']})",
                body="\n\n".join(paras), url=GITHUB.format(commit=self.commit, path="data/courses.json"), language="ko",
                content_level="body", source_type="repository_data",
                metadata={"course_id": cid, "place_ids": order, "snapshot": snap},
                chunks=[Chunk(f"c{i:02d}", f"{c['title']['ko']} > 문단 {i}", t) for i, t in enumerate(paras, start=1)],
            ))
        # 실제 공지 원문(scripts/fetch_royal_notice.py로 수집, 사람이 기간 확인 후 needs_review=false)이 있으면 합성 공지를 대체
        replaced: set[str] = set()
        for f in sorted((self.dir / "royal_notices").glob("*.json")):
            n = json.loads(f.read_text(encoding="utf-8"))
            if n.get("needs_review", True):
                continue  # 확인 안 된 기간으로 답하지 않는다
            replaced.add(n.get("replaces_synthetic") or "")
            paras = [x for x in re.split(r"\n{1,}", n["body"]) if x.strip()]
            docs.append(Document(
                project=PROJECT, source_id=n["source_id"], collection="notices", title=n["title"], body=n["body"],
                url=n["url"], language="ko", content_level="body", source_type="public_original",
                published_at=_d(n.get("published_at")), valid_from=_d(n.get("valid_from")), valid_to=_d(n.get("valid_to")),
                checked_at=datetime.fromisoformat(n["checked_at"]) if n.get("checked_at") else None,
                metadata={"place_id": "gyeongbokgung-palace", "fetched_by": "scripts/fetch_royal_notice.py"}
                | {k: n[k] for k in ("action_type", "action_target", "action_target_en", "action_terms") if k in n},
                chunks=[Chunk(f"p{i:02d}", f"{n['title']} > 문단 {i}", t) for i, t in enumerate(paras, start=1)],
            ))
        for f in sorted(self.dir.glob("synthetic_*.json")):
            for s in json.loads(f.read_text(encoding="utf-8")):
                if s["source_id"] in replaced:
                    continue
                docs.append(Document(
                    project=PROJECT, source_id=s["source_id"], collection=s["collection"], title=s["title"], body=s["body"],
                    url=s.get("url"), language="ko", content_level="body", source_type="synthetic",
                    published_at=_d(s.get("published_at")), valid_from=_d(s.get("valid_from")), valid_to=_d(s.get("valid_to")),
                    metadata=s.get("metadata", {}) | {"synthetic": True},
                    chunks=[Chunk(f"p{i:02d}", f"{s['title']} > 문단 {i}", t)
                            for i, t in enumerate([x for x in s["body"].split("\n\n") if x.strip()], start=1)],
                ))
        return SyncBatch(docs, {"places": "complete", "courses": "complete", "notices": "complete"})

    # ── context: 허용된 ID만 통과 ───────────
    def validate_context(self, context: dict | None) -> dict:
        c = context or {}
        out = {}
        if c.get("course_id") in self._courses:
            out["course_id"] = c["course_id"]
        if c.get("place_id") in self._places:
            out["place_id"] = c["place_id"]
        out["ranked_route_ids"] = [x for x in c.get("ranked_route_ids") or [] if x in self._courses][:10]
        out["ranked_place_ids"] = [x for x in c.get("ranked_place_ids") or [] if x in self._places][:10]
        return out

    def course_place_ids(self, cid: str) -> list[str]:
        return [p["id"] for p in self._courses[cid]["places"]]

    # ── 라우팅 규칙 ─────────────────────────
    def classify(self, text: str, lang: str, ctx: dict, now: datetime) -> Part:
        low = text.lower()
        ts = has_any(low, TIME_SENSITIVE_TERMS)
        detail = has_any(low, DETAIL_TERMS)
        if has_any(low, RANKING_TERMS):
            return Part("structured", text, "ranking", params={"ids": ctx.get("ranked_route_ids", [])})
        if has_any(low, COURSE_REF):
            cid = ctx.get("course_id")
            if not cid:
                q = "어느 코스를 말하는지 알려줄래?" if lang == "ko" else "Which course do you mean?"
                return Part("clarify", text, "course_ref", clarify=q)
            order = [f"place:{p}" for p in self.course_place_ids(cid)]
            # 코스 문서(코스 순서·추천 이유)를 맨 앞에, 이어서 앱이 정한 장소 순서를 그대로 보존
            return Part("document", text, "course_ref", source_ids=[f"course:{cid}", *order], keep_order=[f"course:{cid}", *order],
                        time_sensitive=ts, needs_detail=detail)
        if re.search(r"(^|\s)(여기|이곳|거기|그곳|이 장소)", text) or re.search(r"\b(this place|here|there)\b", low):
            pid = ctx.get("place_id")
            named = any(n.lower() in low for n in self._names())
            if pid and not named:
                r = self._places[pid]
                hint = (f"{text} (여기 = {r['nameKo']} ({r.get('nameEn', '')}))" if lang == "ko"
                        else f"{text} (here = {r.get('nameEn', '')} / {r['nameKo']})")
                return Part("document", hint, "place_ref", source_ids=[f"place:{pid}"], time_sensitive=ts, needs_detail=detail)
            if not named:
                q = "어느 장소를 말하는지 알려줄래?" if lang == "ko" else "Which place do you mean?"
                return Part("clarify", text, "place_ref", clarify=q)
        return Part("document", text, "doc", time_sensitive=ts, needs_detail=detail)

    def _names(self):
        for r in self._places.values():
            yield r["nameKo"]
            if r.get("nameEn"):
                yield r["nameEn"]

    def run_structured(self, part: Part, store, now: datetime, lang: str) -> PartResult:
        if part.intent != "ranking":
            raise NotImplementedError(part.intent)
        ids = part.params.get("ids") or []
        if not ids:
            m = ("앱이 계산한 추천 순위가 전달되지 않아 순위를 말할 수 없어." if lang == "ko"
                 else "The app did not pass its computed ranking, so I can't state one.")
            return PartResult("insufficient_evidence", message=m)
        docs = {d["source_id"]: d for d in store.documents(PROJECT, "courses")}
        claims = []
        for i, cid in enumerate(ids, start=1):  # Ari가 넘긴 순서를 그대로 보존
            d = docs.get(f"course:{cid}")
            if d:
                claims.append(Claim(f"{i}. {d['title']}", [citation_from(d | {"locator": "코스 목록"}, d["title"],
                                                                         "순위: MARU 앱 계산값(전달받은 순서)")]))
        return PartResult("answered", claims=claims, debug={"order": ids})


def _d(v):
    return date.fromisoformat(v) if v else None


def detect_lang(text: str) -> str:
    return "ko" if textnorm.is_korean(text) else "en"
