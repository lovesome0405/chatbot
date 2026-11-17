"""질의 처리 오케스트레이션."""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta

from . import citations as citecheck
from . import textnorm
from .adapter import Adapter, Claim, Part, PartResult
from .generation import GenerationError
from .models import ChatResult, Citation, Evidence
from .retrieval import retrieve
from .timeutil import seoul_now

log = logging.getLogger("ragcore.request")

MSG = {
    "insufficient": {"ko": "확인된 자료에서 찾지 못했어.", "en": "I couldn't find this in the verified sources."},
    "title_only": {"ko": "이 공지는 제목만 수집돼 있어서 세부 내용은 확인할 수 없어. 원문 링크에서 확인해줘.",
                   "en": "Only the title of this notice was collected, so the details can't be confirmed. Please check the original link."},
    "time": {"ko": "가격·운영시간·개방 여부처럼 시점이 중요한 내용은 지금 시점에 맞는 근거가 없어서 확정할 수 없어.",
             "en": "This depends on the current date (prices, hours, opening status), and no source valid for the current date was found, so I can't confirm it."},
    "unavailable": {"ko": "일시적인 오류로 답변을 만들지 못했어. 아래는 확인 가능한 검색 결과야(생성된 답변 아님).",
                    "en": "A temporary error prevented generating an answer. Below are search results you can check (not a generated answer)."},
    "partial": {"ko": "[일부 확인 불가]", "en": "[Partly unconfirmed]"},
}


def msg(key: str, lang: str) -> str:
    return MSG[key].get(lang, MSG[key]["en"])


def evidence_as_of(ev: Evidence | dict) -> str | None:
    g = ev.get if isinstance(ev, dict) else (lambda k, d=None: getattr(ev, k, d))
    if g("valid_from") or g("valid_to"):
        return f"적용 기간 {g('valid_from') or '?'} ~ {g('valid_to') or '?'}"
    if g("published_at"):
        return f"게시일 {g('published_at')}"
    meta = g("metadata") or {}
    if meta.get("snapshot"):
        return meta["snapshot"]
    if g("checked_at"):
        return f"확인 시각 {g('checked_at'):%Y-%m-%d %H:%M} UTC" if hasattr(g("checked_at"), "strftime") else str(g("checked_at"))
    return None


def citation_from(ev: Evidence | dict, quote: str, note: str | None = None) -> Citation:
    g = ev.get if isinstance(ev, dict) else (lambda k, d=None: getattr(ev, k, d))
    return Citation(source_id=g("source_id"), title=g("title"), url=g("url"), quote=quote, locator=g("locator") or "",
                    as_of=evidence_as_of(ev), source_type=g("source_type"), note=note)


class Engine:
    def __init__(self, settings, store, embedder, generator, adapters: dict[str, Adapter]):
        self.settings, self.store, self.embedder, self.generator = settings, store, embedder, generator
        self.adapters = adapters
        self.min_sim = 0.80 if embedder.name.startswith("multilingual-e5") else 0.25

    # ── 공개 진입점 ─────────────────────────
    def chat(self, project: str, question: str, language: str | None = None, context: dict | None = None,
             reference_time: datetime | None = None, mode: str | None = None) -> ChatResult:
        t0 = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]
        adapter = self.adapters[project]  # 프로젝트는 호출자(서버 설정/앱 자격)가 결정
        now = seoul_now(reference_time)
        lang = language or ("ko" if textnorm.is_korean(question) else "en")
        ctx = adapter.validate_context(context or {})
        debug: dict = {"parts": [], "model_calls": 0, "chunk_ids": [], "errors": []}
        try:
            parts = adapter.plan(question, lang, ctx, now)
            clar = next((p for p in parts if p.kind == "clarify"), None)
            if clar:
                result = ChatResult("clarification_needed", "clarify", clar.clarify or "", [], now.isoformat(), request_id)
            else:
                results = [self._run_part(adapter, p, lang, now, mode, debug) for p in parts]
                result = self._combine(parts, results, lang, now, request_id)
        except Exception as exc:  # 예기치 못한 장애도 RAG 답변처럼 보이지 않게 unavailable로
            debug["errors"].append(type(exc).__name__)
            log.exception("chat failed")
            result = ChatResult("unavailable", "none", msg("unavailable", lang), [], now.isoformat(), request_id)
        debug["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        debug["model"] = self.generator.name
        debug["embedder"] = self.embedder.name
        result.debug = debug
        log.info(json.dumps({
            "request_id": request_id, "project": project, "route": result.route, "status": result.status,
            "latency_ms": debug["latency_ms"], "model": self.generator.name, "model_calls": debug["model_calls"],
            "chunk_ids": debug["chunk_ids"], "errors": debug["errors"],
        }, ensure_ascii=False))
        return result

    # ── 부분 처리 ───────────────────────────
    def _run_part(self, adapter: Adapter, part: Part, lang: str, now: datetime, mode, debug) -> PartResult:
        if part.kind == "structured":
            res = adapter.run_structured(part, self.store, now, lang)
        else:
            res = self._document_part(adapter, part, lang, now, mode)
        debug["parts"].append({"kind": part.kind, "intent": part.intent, "status": res.status} | res.debug)
        debug["model_calls"] += res.model_calls
        debug["chunk_ids"] += res.debug.get("chunk_ids", [])
        if res.debug.get("error"):
            debug["errors"].append(res.debug["error"])
        return res

    def _document_part(self, adapter: Adapter, part: Part, lang: str, now: datetime, mode) -> PartResult:
        as_of = now.date()
        r = retrieve(self.store, self.embedder, self.settings, project=adapter.project, question=part.text,
                     aliases=adapter.aliases, as_of=as_of, mode=mode, source_ids=part.source_ids,
                     collections=part.collections,
                     top_k=self.settings.keyword_top_n + self.settings.vector_top_n)  # 후보 전체 → 자격 필터 → 상위 final_top_k
        rows = [x for x in r.rows if x.get("kw_rank") or (x.get("distance") is not None and 1 - x["distance"] >= self.min_sim)]
        if part.keep_order:
            pos = {sid: i for i, sid in enumerate(part.keep_order)}
            rows.sort(key=lambda x: pos.get(x["source_id"], len(pos)))
        dbg = {"chunk_ids": [x["chunk_id"] for x in rows], "retrieval_ms": r.latency_ms,
               "ranks": [(x["source_id"], x.get("kw_rank"), x.get("vec_rank")) for x in rows]}
        if r.errors:
            dbg["error"] = ",".join(r.errors)
        evidences = [self._evidence(i, x) for i, x in enumerate(rows, start=1)]
        title_only = [e for e in evidences if e.content_level == "title_only"]
        body = [e for e in evidences if e.content_level != "title_only"]
        if part.needs_detail and evidences and evidences[0].content_level == "title_only":
            body = []  # 질문이 가리키는 1순위 원본이 제목만 있는 공지 → 다른 문서로 세부 답변을 만들지 않음

        if part.time_sensitive:
            fresh = [e for e in body if self._time_ok(adapter, e, now)]
            if not fresh:
                related = [citation_from(e, e.text[:120], "답변 근거 아님(시점 미확인)") for e in body[:2]]
                related += self._expired_related(adapter, part, as_of)
                return PartResult("insufficient_evidence", message=f"{msg('insufficient', lang)} {msg('time', lang)}",
                                  related=related, debug=dbg)
            body = fresh
        if not body:
            if title_only:
                rel = [citation_from(e, e.title, "제목만 있음") for e in title_only[:3]]
                return PartResult("insufficient_evidence", message=f"{msg('insufficient', lang)} {msg('title_only', lang)}",
                                  related=rel, debug=dbg)
            return PartResult("insufficient_evidence", message=msg("insufficient", lang),
                              related=self._expired_related(adapter, part, as_of), debug=dbg)

        body = self._diverse(body, self.settings.final_top_k, self.settings.max_chunks_per_source)
        for i, e in enumerate(body, start=1):  # 모델에 보낼 ID를 1부터 다시 매김
            e.eid = f"E{i}"
        try:
            gen = self.generator.generate(part.text, lang, body, today=as_of.isoformat())
        except GenerationError as exc:
            dbg["error"] = f"generation:{type(exc).__name__}"
            return PartResult("unavailable", message=msg("unavailable", lang),
                              related=[citation_from(e, e.text[:160], "검색 결과(생성 실패)") for e in body],
                              model_calls=1, debug=dbg)
        checked = citecheck.verify(gen.claims, body, question=part.text)
        if part.time_sensitive:
            checked.claims = self._drop_period_contradictions(checked, as_of)
        dbg |= {"gen_ms": round(gen.latency_ms, 1), "abstain": gen.abstain, "dropped": checked.dropped,
                "unknown_ids": checked.unknown_ids, "quote_misses": checked.quote_misses,
                "value_mismatches": checked.value_mismatches, "raw_claims": len(gen.claims),
                "raw_output": gen.raw[:2000] if gen.raw else None, "evidence_ids": [(e.eid, e.source_id, e.locator) for e in body]}
        if not checked.claims:
            rel = [citation_from(e, e.text[:120], "관련 원문(답변 근거 아님)") for e in body[:3]]
            return PartResult("insufficient_evidence", message=msg("insufficient", lang), related=rel, model_calls=1,
                              debug=dbg)
        claims = [Claim(text, [citation_from(ev, quote) for ev, quote in good]) for text, good in checked.claims]
        if part.time_sensitive:
            claims += self._period_notes(checked, as_of, lang)
        return PartResult("answered", claims=claims, model_calls=1, debug=dbg)

    NEGATION = ["않", "없", "종료", "닫", "끝났", "not ", "n't", "closed", "no longer", "ended", "over"]

    def _drop_period_contradictions(self, checked, as_of):
        """기준일이 인용 근거의 적용 기간 안인데 주장이 부정(닫힘·종료)이면 모순으로 보고 버린다(휴리스틱, 평가로 점검)."""
        kept = []
        for text, good in checked.claims:
            in_period = any(ev.valid_from and ev.valid_to and ev.valid_from <= as_of <= ev.valid_to for ev, _ in good)
            if in_period and any(n in text.lower() for n in self.NEGATION):
                checked.dropped.append({"reason": "contradicts_valid_period", "claim": text[:200]})
                continue
            kept.append((text, good))
        return kept

    def _period_notes(self, checked, as_of, lang) -> list[Claim]:
        """적용 기간과 기준일 비교는 모델이 아니라 서버가 메타데이터로 계산해 덧붙인다."""
        out, seen = [], set()
        for _, good in checked.claims:
            for ev, _q in good:
                if (ev.valid_from or ev.valid_to) and ev.source_id not in seen:
                    seen.add(ev.source_id)
                    txt = (f"(서버 확인) 근거 적용 기간 {ev.valid_from}~{ev.valid_to}, 기준일 {as_of}은 이 기간 안이야."
                           if lang == "ko" else
                           f"(Server check) Source validity {ev.valid_from} to {ev.valid_to}; the reference date {as_of} is within it.")
                    out.append(Claim(txt, [citation_from(ev, f"{ev.valid_from}~{ev.valid_to}", "적용 기간(메타데이터)")]))
        return out

    @staticmethod
    def _diverse(evs: list[Evidence], k: int, per_source: int) -> list[Evidence]:
        """순서를 유지하며 원본당 최대 per_source 조각만 골라 k개를 채운다(한 문서가 근거 칸을 독점하지 않게)."""
        out, count = [], {}
        for e in evs:
            if count.get(e.source_id, 0) < per_source:
                out.append(e)
                count[e.source_id] = count.get(e.source_id, 0) + 1
            if len(out) == k:
                break
        return out

    def _time_ok(self, adapter: Adapter, e: Evidence, now: datetime) -> bool:
        if e.valid_from or e.valid_to:  # SQL에서 이미 기간이 맞는 것만 남음
            return True
        fresh_days = getattr(adapter, "fresh_days", 0)
        return bool(fresh_days and e.checked_at and now - e.checked_at <= timedelta(days=fresh_days))

    def _expired_related(self, adapter, part: Part, as_of) -> list[Citation]:
        r = retrieve(self.store, self.embedder, self.settings, project=adapter.project, question=part.text,
                     aliases=adapter.aliases, as_of=as_of, mode="keyword", source_ids=part.source_ids,
                     collections=part.collections, include_expired=True)
        out = []
        for x in r.rows:
            if x.get("valid_to") and x["valid_to"] < as_of:
                out.append(citation_from(x, x["text"][:120], f"기간 종료({x.get('valid_from')}~{x['valid_to']}), 답변 근거 아님"))
        return out[:2]

    def _evidence(self, i: int, x: dict) -> Evidence:
        return Evidence(eid=f"E{i}", chunk_id=x["chunk_id"], document_id=x["document_id"], project=x["project"],
                        source_id=x["source_id"], title=x["title"], url=x["url"], text=x["text"], locator=x["locator"],
                        content_level=x["content_level"], source_type=x["source_type"], published_at=x["published_at"],
                        checked_at=x["checked_at"], valid_from=x["valid_from"], valid_to=x["valid_to"],
                        structured=x.get("structured") or {}, metadata=x.get("metadata") or {},
                        scores={"kw_rank": x.get("kw_rank"), "vec_rank": x.get("vec_rank"), "rrf": x.get("rrf")})

    # ── 결합 ────────────────────────────────
    def _combine(self, parts: list[Part], results: list[PartResult], lang, now, request_id) -> ChatResult:
        route = "composite" if len(parts) > 1 else parts[0].kind
        statuses = [r.status for r in results]
        cites: list[Citation] = []
        lines: list[str] = []

        def ref(c: Citation) -> int:
            for i, old in enumerate(cites, start=1):
                if (old.source_id, old.quote, old.note) == (c.source_id, c.quote, c.note):
                    return i
            cites.append(c)
            return len(cites)

        for res in results:
            if res.status == "answered":
                for cl in res.claims:
                    marks = "".join(f"[{ref(c)}]" for c in cl.citations)
                    line = f"{cl.text} {marks}".strip()
                    if line not in lines:
                        lines.append(line)
            else:
                prefix = f"{msg('partial', lang)} " if len(results) > 1 else ""
                marks = "".join(f"[{ref(c)}]" for c in res.related)
                lines.append(f"{prefix}{res.message} {marks}".strip())
        if all(s == "answered" for s in statuses):
            status = "answered"
        elif any(s == "answered" for s in statuses):
            status = "partial"
        elif any(s == "unavailable" for s in statuses):
            status = "unavailable"
        else:
            status = "insufficient_evidence"
        return ChatResult(status, route, "\n".join(lines), cites, now.isoformat(), request_id)


def to_json(result: ChatResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False, default=str, indent=1)
