"""질의 처리 오케스트레이션."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta

from . import citations as citecheck
from . import textnorm
from .adapter import Adapter, Claim, Part, PartResult
from . import extractive
from . import general as gen_policy
from .generation import GenerationError, GenerationTimeout, GenOutput, ModelLoading
from .models import ChatResult, Citation, Evidence
from .retrieval import retrieve
from .timeutil import seoul_now

log = logging.getLogger("ragcore.request")

MSG = {
    "insufficient": {"ko": "확인된 자료에서는 찾지 못했어요.", "en": "I couldn't find this in the verified sources."},
    "title_only": {"ko": "이 공지는 제목만 수집돼 있어서 세부 내용은 확인할 수 없어요. 원문 링크에서 확인해 주세요.",
                   "en": "Only the title of this notice was collected, so the details can't be confirmed. Please check the original link."},
    "time": {"ko": "가격·운영시간·출입 가능 여부처럼 시점이 중요한 내용은 지금 시점에 맞는 근거가 없어서 확정할 수 없어요.",
             "en": "This depends on the current date (prices, hours, access), and no source valid for the current date was found, so I can't confirm it."},
    "unavailable": {"ko": "잠시 오류가 나서 답변을 만들지 못했어요. 아래는 확인할 수 있는 검색 결과예요(생성된 답변 아님).",
                    "en": "A temporary error prevented generating an answer. Below are search results you can check (not a generated answer)."},
    "partial": {"ko": "[일부는 확인하지 못했어요]", "en": "[Partly unconfirmed]"},
    "declined": {"ko": "이 요청은 도와드릴 수 없어요. 앱 자료로 확인할 수 있는 질문을 해 주세요.",
                 "en": "I can't help with that request. Please ask something the app's sources can answer."},
    "timeout": {"ko": "정해진 시간 안에 근거로 확인된 답을 만들지 못했어요. 아래 관련 자료를 확인해 주세요.",
                "en": "I couldn't build a source-checked answer in time. Please check the related sources below."},
    "loading": {"ko": "답변 모델을 준비하는 중이라 지금은 문장을 만들지 못했어요. 아래 관련 자료를 확인하거나 잠시 뒤 다시 물어봐 주세요.",
                "en": "The answer model is still loading, so I couldn't write an answer yet. Please check the related sources below or ask again shortly."},
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
             reference_time: datetime | None = None, mode: str | None = None, *, ask_as: str | None = None,
             cache_source: str = "live") -> ChatResult:
        t0 = time.perf_counter()
        request_id = uuid.uuid4().hex[:12]
        adapter = self.adapters[project]  # 프로젝트는 호출자(서버 설정/앱 자격)가 결정
        now = seoul_now(reference_time)
        lang = language or ("ko" if textnorm.is_korean(question) else "en")
        ctx = adapter.validate_context(context or {})
        debug: dict = {"parts": [], "model_calls": 0, "chunk_ids": [], "errors": []}
        policy: gen_policy.GeneralPolicy | None = getattr(adapter, "general_policy", None)
        # v0.6.0 인사·감사·사용법: 질문 전체가 그것뿐이면 어댑터의 고정 응답(모델 0회, 출처 없음)
        kind = gen_policy.smalltalk_kind(question) if policy else None
        if kind and policy.smalltalk.get(kind):
            texts = policy.smalltalk[kind]
            res = ChatResult("answered", "smalltalk", texts.get(lang, texts.get("en", "")), [], now.isoformat(), request_id,
                             debug=debug | {"smalltalk": kind, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
            log.info(json.dumps({"request_id": request_id, "project": project, "route": "smalltalk", "status": "answered",
                                 "latency_ms": res.debug["latency_ms"], "model_calls": 0}, ensure_ascii=False))
            return res
        # v0.5.0 미리 만든 답: 실제 요청(기준 시각 덮어쓰기 없음)에서만 쓴다. 평가·데모의 고정 시각 요청은 늘 새로 계산
        use_cache = self.settings.answer_cache and reference_time is None and mode is None
        key = version = None
        if use_cache:
            key, version = cache_key(project, question, lang, ctx), self.store.data_version(project)
            hit = self.store.cache_get(project, key, version, self.settings.cache_require_review)
            if hit:
                res = ChatResult(hit["status"], hit["route"], hit["answer"], [Citation(**c) for c in hit["citations"]],
                                 now.isoformat(), request_id,
                                 debug=debug | {"cache_hit": True, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)})
                log.info(json.dumps({"request_id": request_id, "project": project, "route": res.route, "status": res.status,
                                     "latency_ms": res.debug["latency_ms"], "cache_hit": True}, ensure_ascii=False))
                return res
        parts = []
        try:
            parts = adapter.plan(ask_as or question, lang, ctx, now)
            clar = next((p for p in parts if p.kind == "clarify"), None)
            if clar:
                result = ChatResult("clarification_needed", "clarify", clar.clarify or "", [], now.isoformat(), request_id)
            else:
                # 생성 시간 상한은 요청 전체 기준: 문서 부분이 둘이면 반씩 나눈다(복합 질문도 전체 상한 안에)
                n_doc = sum(p.kind == "document" for p in parts) or 1
                if self.settings.gen_budget_s:
                    for p in parts:
                        p.budget_s = self.settings.gen_budget_s / n_doc
                results = [self._run_part(adapter, p, lang, now, mode, debug) for p in parts]
                result = self._combine(parts, results, lang, now, request_id)
        except Exception as exc:  # 예기치 못한 장애도 RAG 답변처럼 보이지 않게 unavailable로
            debug["errors"].append(type(exc).__name__)
            log.exception("chat failed")
            result = ChatResult("unavailable", "none", msg("unavailable", lang), [], now.isoformat(), request_id)
        if policy and parts:
            result = self._maybe_general(policy, question, ask_as, lang, parts, result, debug, t0, now, request_id)
        debug["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        debug["model"] = self.generator.name
        debug["embedder"] = self.embedder.name
        result.debug = debug
        if use_cache and key and cacheable(result, parts):
            payload = {k: v for k, v in result.public_dict().items() if k not in ("as_of", "request_id")}
            # 사람 검토용(응답에는 나가지 않음): 원래 질문·언어·화면 상태
            payload["_review"] = {"question": question, "language": lang, "context": ctx, "ask_as": ask_as}
            self.store.cache_put(project, key, version, payload, cache_source)
        log.info(json.dumps({
            "request_id": request_id, "project": project, "route": result.route, "status": result.status,
            "latency_ms": debug["latency_ms"], "model": self.generator.name, "model_calls": debug["model_calls"],
            "chunk_ids": debug["chunk_ids"], "errors": debug["errors"],
        }, ensure_ascii=False))
        return result

    # ── v0.6.0 일반 답변(B안) ───────────────
    def _maybe_general(self, policy, question, ask_as, lang, parts, result: ChatResult, debug, t0, now, request_id) -> ChatResult:
        """근거 없음(보류) + 도메인 밖 질문일 때만 출처 없는 일반 답변. 그 밖에는 result 를 그대로 돌려준다."""
        if result.status != "insufficient_evidence" or len(parts) != 1 or parts[0].kind != "document":
            return result
        texts = [question] + ([ask_as] if ask_as else [])
        why = next((b for t in texts if (b := gen_policy.banned(t, policy))), None)
        if why:
            debug["general"] = {"declined": why}
            return ChatResult("insufficient_evidence", result.route, msg("declined", lang), [], now.isoformat(), request_id)
        if not policy.enabled:
            return result
        if parts[0].time_sensitive:
            debug["general"] = {"skip": "time_sensitive"}
            return result
        dom = next((d for t in texts if (d := gen_policy.is_domain_question(t, policy))), None)
        cov = (debug["parts"][0].get("q_coverage") or 0) if debug["parts"] else 0
        if not dom and cov >= gen_policy.DOMAIN_COVERAGE:
            dom = f"coverage:{cov}"     # 질문 핵심어 대부분이 앱 자료 한 곳에 있음 = 앱 자료의 주제
        if dom:
            debug["general"] = {"skip": f"domain:{dom}"}
            return result
        # 같은 생성 예산 안에서: 문서 경로가 쓴 시간을 빼고 남은 만큼만(합계 10초 이내 유지)
        remaining = (self.settings.gen_budget_s - (time.perf_counter() - t0)) if self.settings.gen_budget_s else None
        if remaining is not None and remaining < 2:
            debug["general"] = {"skip": "no_budget"}
            return result
        try:
            text = self.generator.generate_text(gen_policy.system_prompt(policy, lang), question, lang, budget_s=remaining)
        except GenerationError as exc:
            debug["general"] = {"error": type(exc).__name__}
            debug["errors"].append(f"general:{type(exc).__name__}")
            return result
        debug["model_calls"] += 1
        ok, reason = gen_policy.check_answer(text, policy)
        debug["general"] = {"raw": text[:600], "dropped": reason}
        if not ok:
            return result
        return ChatResult("answered", "general", ok, [], now.isoformat(), request_id)

    # ── 부분 처리 ───────────────────────────
    def _run_part(self, adapter: Adapter, part: Part, lang: str, now: datetime, mode, debug) -> PartResult:
        res = adapter.run_structured(part, self.store, now, lang) if part.kind == "structured" else None
        if res is None:  # 정형 규칙이 맞는 행을 찾지 못하면(어댑터가 None) 문서 검색으로 처리한다
            if part.kind == "structured":
                part.kind = "document"
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
        if part.source_ids:
            # 앱이 명시적으로 넘긴 장소·코스 범위: 사용자가 대상을 이미 골랐으므로 관련성 관문을 적용하지 않는다
            rows = list(r.rows)
        else:
            rows = [x for x in r.rows if x.get("kw_rank") or (x.get("distance") is not None and 1 - x["distance"] >= self.min_sim)]
        if part.keep_order:
            pos = {sid: i for i, sid in enumerate(part.keep_order)}
            rows.sort(key=lambda x: pos.get(x["source_id"], len(pos)))
        dbg = {"chunk_ids": [x["chunk_id"] for x in rows], "retrieval_ms": r.latency_ms,
               "ranks": [(x["source_id"], x.get("kw_rank"), x.get("vec_rank")) for x in rows]}
        if r.errors:
            dbg["error"] = ",".join(r.errors)
        evidences = [self._evidence(i, x) for i, x in enumerate(rows, start=1)]
        dbg["q_coverage"] = extractive.coverage(part.user_text or part.text, evidences, adapter.aliases)
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

        pol = getattr(adapter, "general_policy", None)
        if (pol and pol.enabled and not part.source_ids and dbg["q_coverage"] < gen_policy.OFF_TOPIC_COVERAGE
                and not gen_policy.is_domain_question(part.user_text or part.text, pol)):
            # v0.6.0: 앱 자료 주제가 아니고(도메인 용어 없음) 검색된 근거와도 거의 안 겹치는 질문 → 관련 없는 근거로 문장을
            # 만들지 않는다(예: 'thank you 한국어' → 엉뚱한 장소 설명 인용). 일반 답변 단계가 같은 예산을 온전히 쓴다
            dbg["off_topic"] = True
            return PartResult("insufficient_evidence", message=msg("insufficient", lang), debug=dbg)
        body = self._diverse(body, self.settings.final_top_k, self.settings.max_chunks_per_source)
        for i, e in enumerate(body, start=1):  # 모델에 보낼 ID를 1부터 다시 매김
            e.eid = f"E{i}"
        fallback = None
        t_gen = time.perf_counter()
        try:
            gen = self.generator.generate(part.text, lang, body, today=as_of.isoformat(), persona=getattr(adapter, "persona", ""),
                                          budget_s=getattr(part, "budget_s", None))
        except GenerationError as exc:
            # v0.5.0: 생성이 시간 상한을 넘기거나 실패하면, 새 문장을 쓰지 않고 근거 원문에서 맞는 문장을 그대로 보여 준다.
            # 이 발췌도 아래 인용 검증을 똑같이 거친다. 발췌할 문장도 없으면 이전처럼 unavailable.
            dbg["error"] = f"generation:{type(exc).__name__}"
            ex = extractive.extract(part.user_text or part.text, lang, body, adapter.aliases)
            has_action = bool(part.time_sensitive and self._action_claims(adapter, part, body, as_of, lang))
            if not ex and not has_action:
                if isinstance(exc, GenerationTimeout):
                    # 시간 상한 초과 + 발췌할 문장 없음: 장애가 아니라 '시간 안에 확인된 답 없음'. 다시 시도해도 같으므로
                    # unavailable(앱이 오류·재시도로 처리) 대신 관련 자료와 함께 보류로 돌려준다
                    return PartResult("insufficient_evidence", message=msg("loading" if isinstance(exc, ModelLoading) else "timeout", lang),
                                      related=[citation_from(e, e.text[:120], "관련 원문(시간 안에 답을 만들지 못함)") for e in body[:3]],
                                      model_calls=1, debug=dbg)
                return PartResult("unavailable", message=msg("unavailable", lang),
                                  related=[citation_from(e, e.text[:160], "검색 결과(생성 실패)") for e in body],
                                  model_calls=1, debug=dbg)
            fallback = "extractive"
            gen = GenOutput(abstain=not ex, claims=ex, model="extractive",
                            latency_ms=(time.perf_counter() - t_gen) * 1000)
            dbg["fallback"] = fallback
        # 되풀이 검사는 앱이 붙인 힌트('(here = …)') 없이 사용자가 실제로 쓴 질문과 비교한다(v0.4.0)
        checked = citecheck.verify(gen.claims, body, question=part.user_text or part.text, aliases=adapter.aliases,
                                   glossary=getattr(adapter, "term_glossary", None),
                                   term_pattern=getattr(adapter, "term_pattern", None), lang=lang)
        dbg |= {"gen_ms": round(gen.latency_ms, 1), "abstain": gen.abstain, "dropped": checked.dropped,
                "unknown_ids": checked.unknown_ids, "quote_misses": checked.quote_misses,
                "value_mismatches": checked.value_mismatches, "raw_claims": len(gen.claims),
                "echo_enriched": len(checked.echo_claims),
                "raw_output": gen.raw[:2000] if gen.raw else None, "evidence_ids": [(e.eid, e.source_id, e.locator) for e in body]}
        action = self._action_claims(adapter, part, body, as_of, lang) if part.time_sensitive else []
        if not checked.claims and not action and not fallback:
            # v0.5.0: 모델 주장이 검증에서 모두 버려졌으면, 근거 원문 발췌로 한 번 더 시도한다(발췌도 같은 검증을 거침)
            ex = extractive.extract(part.user_text or part.text, lang, body, adapter.aliases)
            if ex:
                rechecked = citecheck.verify(ex, body, question=part.user_text or part.text, aliases=adapter.aliases, lang=None)
                if rechecked.claims:
                    checked, fallback = rechecked, "extractive_after_drop"
                    dbg["fallback"] = fallback
        if not checked.claims and not action:
            rel = [citation_from(e, e.text[:120], "관련 원문(답변 근거 아님)") for e in body[:3]]
            return PartResult("insufficient_evidence", message=msg("insufficient", lang), related=rel, model_calls=1,
                              debug=dbg)
        note = {"extractive": "원문 발췌(모델 준비 중이라 문장 생성 생략)" if dbg.get("error") == "generation:ModelLoading"
                else "원문 발췌(생성 시간 초과로 문장 생성 생략)",
                "extractive_after_drop": "원문 발췌(모델 답이 근거 검증을 통과하지 못함)"}.get(fallback)
        # 짧은 발췌(short 인용)는 검증을 통과한 뒤 원문 문장 전체로 넓혀 보여 준다
        good_of = [[(ev, citecheck.expand_quote(q, ev.text)) for ev, q in good] for _, good in checked.claims]
        claims = action + [
            Claim(citecheck.enrich_echo(text, good_of[i][0][1], lang) if i in checked.echo_claims and not fallback else text,
                  [citation_from(ev, quote, note) for ev, quote in good_of[i]])
            for i, (text, good) in enumerate(checked.claims)]
        if part.time_sensitive:
            claims += self._period_notes(checked, as_of, lang, skip={c.citations[0].source_id for c in action})
        if hasattr(adapter, "extra_claims"):  # 어댑터가 메타데이터로 결정적으로 보강(예: 코스 순서)
            claims += adapter.extra_claims(part, claims, lang)
        return PartResult("answered", claims=claims, model_calls=1, debug=dbg)

    def _action_claims(self, adapter, part: Part, body: list[Evidence], as_of, lang) -> list[Claim]:
        """공지의 조치 유형과 적용 기간으로 상태를 코드가 판정한다(모델 판단에 맡기지 않음).
        질문이 공지의 대상(action_terms, 별칭 확장 포함)을 가리킬 때만 붙인다. SQL에서 기간이 맞는 근거만 남아 있다."""
        q = set(textnorm.expand_query(part.text, adapter.aliases))
        out = []
        for ev in body:
            md = ev.metadata or {}
            if md.get("action_type") != "access_restricted" or not (ev.valid_from and ev.valid_to):
                continue
            if not q & {t for term in md.get("action_terms", []) for t in textnorm.tokens(term)}:
                continue
            if lang == "ko":
                txt = (f"공지 기준으로 {textnorm.topic(md['action_target'])} {ev.valid_from}부터 {ev.valid_to}까지 출입이 제한돼요. "
                       f"기준일 {as_of}은 이 기간 안이라 지금은 올라갈 수 없어요.")
            else:
                txt = (f"According to the official notice, access to {md.get('action_target_en', md['action_target'])} is restricted "
                       f"from {ev.valid_from} to {ev.valid_to}. The reference date {as_of} is within this period, so you can't go up now.")
            out.append(Claim(txt, [citation_from(ev, ev.text, "조치 유형·적용 기간(서버 판정)")]))
            break
        return out

    def _period_notes(self, checked, as_of, lang, skip=frozenset()) -> list[Claim]:
        """적용 기간과 기준일 비교는 모델이 아니라 서버가 메타데이터로 계산해 덧붙인다."""
        out, seen = [], set()
        for _, good in checked.claims:
            for ev, _q in good:
                if (ev.valid_from or ev.valid_to) and ev.source_id not in seen and ev.source_id not in skip:
                    seen.add(ev.source_id)
                    txt = (f"(서버 확인) 근거 적용 기간은 {ev.valid_from}~{ev.valid_to}이고, 기준일 {as_of}은 이 기간 안이에요."
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


_KEY_STRIP = re.compile(r"[\s?？!！.。,，~…'\"“”‘’]+")


def cache_key(project: str, question: str, lang: str, ctx: dict) -> str:
    """질문 문장(대소문자·공백·문장부호 차이 무시) + 언어 + 화면 상태 ID. 뜻이 비슷한 다른 문장은 다른 키다(안전 우선)."""
    import hashlib
    import unicodedata
    q = _KEY_STRIP.sub(" ", unicodedata.normalize("NFKC", question).lower()).strip()
    raw = json.dumps([project, lang, q, sorted((k, v) for k, v in ctx.items() if v)], ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def cacheable(result: ChatResult, parts) -> bool:
    """모델이 만든 답 중, 시점과 무관하고(기간·시점 질문 아님) 원문 발췌 대체가 아닌 것만 저장한다."""
    d = result.debug
    if result.route in ("general", "smalltalk"):     # 출처 없는 답은 미리 만든 답으로 저장하지 않는다
        return False
    if result.status not in ("answered", "partial") or not d.get("model_calls"):
        return False
    if any(getattr(p, "time_sensitive", False) for p in parts) or any(x.get("fallback") for x in d.get("parts", [])):
        return False
    return not any((c.as_of or "").startswith("적용 기간") for c in result.citations)


def to_json(result: ChatResult) -> str:
    return json.dumps(asdict(result), ensure_ascii=False, default=str, indent=1)
