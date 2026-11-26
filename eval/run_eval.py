"""고정 평가 실행기.

1) 검색 비교: keyword / vector / hybrid(RRF) (+ MARU: 기존 Ari scoreAriTextMatch 기준선) Hit@3 — 원본 ID 기준
2) 전체 응답(hybrid + 설정된 생성 모델): 경로·상태·정형 정답·보류·핵심 사실·인용·누출·지연·모델 호출 수
분모와 실패 사례를 모두 기록한다. 순위 합산 점수(RRF)는 정답 확률이 아니다.
"""

from __future__ import annotations

import csv
import re
import json
import platform
import statistics
import time
from datetime import datetime
from pathlib import Path

from ragcore.chunking import CHUNKER_VERSION
from ragcore.registry import ROOT
from ragcore.retrieval import retrieve, unique_sources
from ragcore.timeutil import SEOUL

from adapters.maru import ari_baseline


def _load(path) -> list[dict]:
    p = Path(path)
    p = p if p.is_absolute() else ROOT / p
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _ref(q) -> datetime:
    return datetime.fromisoformat(q["as_of"]).replace(tzinfo=SEOUL)


def searchable(q) -> bool:
    return q["expected_route"] == "document" and q["gold_source_ids"] and "expired" not in q["tags"]


def retrieval_eval(engine, qs, modes) -> dict:
    out = {"definition": "Hit@3 = 상위 3개 원본 ID(조각을 원본 단위로 접음) 중 기대 출처가 하나라도 있으면 1. "
                         "대상: 기대 경로=document, 기대 출처 있음, 기간 만료 의도 제외",
           "modes": {}, "per_question": []}
    sq = [q for q in qs if searchable(q)]
    ari_items = ari_baseline.haystacks(ROOT / "data" / "maru")
    rows = {q["id"]: {"id": q["id"], "project": q["project"], "gold": q["gold_source_ids"]} for q in sq}
    for mode in modes + ["ari_baseline"]:
        hits, n, lat, rr = 0, 0, [], []
        for q in sq:
            if mode == "ari_baseline":
                if q["project"] != "maru":
                    continue
                t = time.perf_counter()
                top = ari_baseline.rank(q["question"], ari_items)[:3]
                lat.append((time.perf_counter() - t) * 1000)
            else:
                ad = engine.adapters[q["project"]]
                part = next((p for p in ad.plan(q["question"], q["language"], ad.validate_context(q["context"]), _ref(q))
                             if p.kind == "document"), None)
                if part is None:
                    top = []
                else:
                    t = time.perf_counter()
                    r = retrieve(engine.store, engine.embedder, engine.settings, project=q["project"], question=part.text,
                                 aliases=ad.aliases, as_of=_ref(q).date(), mode=mode, source_ids=part.source_ids,
                                 collections=part.collections, top_k=20)
                    lat.append((time.perf_counter() - t) * 1000)
                    top = unique_sources(r.rows, 3)
                    top10 = unique_sources(r.rows, 10)
            if mode == "ari_baseline":
                top10 = ari_baseline.rank(q["question"], ari_items)[:10]
            if part is None and mode != "ari_baseline":
                top10 = []
            # MRR(v0.4.0): 상위 10개 원본 중 첫 기대 출처의 역순위(없으면 0). Hit@3 이 같아도 정답 순위 차이를 본다
            rank = next((i for i, sid in enumerate(top10, start=1) if sid in q["gold_source_ids"]), None)
            rr.append(1 / rank if rank else 0.0)
            hit = bool(set(top) & set(q["gold_source_ids"]))
            if q.get("gold_locator") and mode != "ari_baseline" and part is not None:
                rows[q["id"]].setdefault("row_hit", {})[mode] = any(q["gold_locator"] in x["locator"] for x in r.rows[:3])
            hits += hit
            n += 1
            rows[q["id"]][mode] = {"hit": hit, "top3": top}
        out["modes"][mode] = {"hit_at_3": hits, "denominator": n, "rate": round(hits / n, 3) if n else None,
                              "mrr_at_10": round(statistics.mean(rr), 3) if rr else None,
                              "mean_latency_ms": round(statistics.mean(lat), 1) if lat else None}
    loc = [q for q in sq if q.get("gold_locator")]
    out["table_row_hit_at_3"] = {m: sum(rows[q["id"]].get("row_hit", {}).get(m, False) for q in loc) for m in modes}
    out["table_row_hit_at_3"]["denominator"] = len(loc)
    out["table_row_hit_at_3"]["definition"] = "상위 3개 조각 중 기대 행(locator)이 있는지. 장학표 행 섞임 점검용"
    # MARU 하위 집합: Ari 기준선과 같은 분모
    maru = [q for q in sq if q["project"] == "maru"]
    out["maru_subset"] = {m: sum(rows[q["id"]][m]["hit"] for q in maru) for m in modes + ["ari_baseline"]}
    out["maru_subset"]["denominator"] = len(maru)
    ari_comp = [q for q in maru if all(g.startswith(("place:", "course:")) for g in q["gold_source_ids"])]
    out["maru_ari_comparable_subset"] = {m: sum(rows[q["id"]][m]["hit"] for q in ari_comp) for m in modes + ["ari_baseline"]}
    out["maru_ari_comparable_subset"]["denominator"] = len(ari_comp)
    out["maru_ari_comparable_subset"]["note"] = "Ari 기준선 코퍼스(장소·코스)에 기대 출처가 있는 질문만"
    out["per_question"] = list(rows.values())
    return out


def _project_sources(engine, project) -> set[str]:
    return {d["source_id"] for d in engine.store.documents(project)}


def full_eval(engine, qs) -> dict:
    results, review = [], []
    sources = {p: _project_sources(engine, p) for p in engine.adapters}
    for q in qs:
        t = time.perf_counter()
        res = engine.chat(q["project"], q["question"], q["language"], q["context"], _ref(q))
        wall = (time.perf_counter() - t) * 1000
        cited = [c.source_id for c in res.citations]
        blob = res.answer + " " + " ".join(f"{c.quote} {c.note or ''} {c.title}" for c in res.citations)
        facts_ok = all(f in blob for f in q["key_facts"]) if q["key_facts"] else None
        leaks = [s for s in cited if s not in sources[q["project"]] and not s.startswith(f"{q['project']}:")]
        doc_parts = [p for p in res.debug.get("parts", []) if p["kind"] == "document"]
        r = {
            "id": q["id"], "project": q["project"], "tags": q["tags"], "expected_route": q["expected_route"],
            "question": q["question"], "language": q["language"],
            "route": res.route, "expected_status": q["expected_status"], "status": res.status,
            "route_ok": res.route == q["expected_route"], "status_ok": res.status in q["expected_status"],
            "answerable": q["answerable"], "key_facts_ok": facts_ok,
            "gold_cited": bool(set(cited) & set(q["gold_source_ids"])) if q["gold_source_ids"] else None,
            "leaks": leaks, "model_calls": res.debug.get("model_calls", 0), "latency_ms": round(wall, 1),
            "unknown_ids_from_model": sum(p.get("unknown_ids", 0) or 0 for p in doc_parts),
            "quote_misses": sum(p.get("quote_misses", 0) or 0 for p in doc_parts),
            "value_mismatches": sum(p.get("value_mismatches", 0) or 0 for p in doc_parts),
            "echo_enriched": sum(p.get("echo_enriched", 0) or 0 for p in doc_parts),
            "dropped": [d for p in doc_parts for d in p.get("dropped", [])],
            "raw_outputs": [p.get("raw_output") for p in doc_parts if p.get("raw_output")],
            "evidence_ids": [p.get("evidence_ids") for p in doc_parts if p.get("evidence_ids")],
            # 일반 답변 시도 기록(버려진 이유 debug.general.dropped 등)과 오류 — 학교 PC 모델 비교용(2026-11-26)
            "general": res.debug.get("general"), "errors": res.debug.get("errors", []),
            "answer": res.answer, "citations": [{"source_id": c.source_id, "quote": c.quote, "note": c.note,
                                                  "locator": c.locator} for c in res.citations],
        }
        results.append(r)
        if res.status in ("answered", "partial"):
            for line in res.answer.splitlines():
                refs = [res.citations[int(n) - 1] for n in re.findall(r"\[(\d+)\]", line) if 0 < int(n) <= len(res.citations)]
                if not refs or all(c.note for c in refs):
                    continue  # 보류 안내 줄(관련 원문만 있음)은 검토 대상 아님
                review.append({"id": q["id"], "question": q["question"], "language": q["language"],
                               "generated_by": "model" if r["model_calls"] and not line.startswith(("(서버 확인)", "- ")) else "server_template",
                               "claim": line,
                               "cited_quotes(this claim only)": " || ".join(f"{c.source_id} [{c.locator}] {c.quote}" for c in refs),
                               "gold_locator": q.get("gold_locator", ""), "key_facts": "; ".join(q["key_facts"]),
                               "auto_key_facts_ok": facts_ok,
                               "human_supports_claim(Y/N)": "", "human_complete(Y/N)": "", "human_note": ""})

    def rate(xs):
        xs = list(xs)
        return {"ok": sum(xs), "denominator": len(xs), "rate": round(sum(xs) / len(xs), 3) if xs else None}

    lat = [r["latency_ms"] for r in results]
    structured = [r for r in results if r["expected_route"] == "structured"]
    abst = [r for r in results if r["answerable"] == "none"]
    full_ans = [r for r in results if r["answerable"] == "full"]
    answered = [r for r in results if r["status"] in ("answered", "partial") and r["key_facts_ok"] is not None]
    summary = {
        "route_accuracy": rate(r["route_ok"] for r in results),
        "status_accuracy": rate(r["status_ok"] for r in results),
        "structured_accuracy": rate(r["status_ok"] and (r["key_facts_ok"] in (True, None)) for r in structured),
        "abstention_correct": rate(r["status_ok"] for r in abst),
        "false_abstentions": {"count": sum(r["status"] in ("insufficient_evidence", "clarification_needed", "unavailable")
                                           for r in full_ans), "denominator": len(full_ans)},
        "key_facts_in_answer_or_quotes(auto proxy)": rate(r["key_facts_ok"] for r in answered),
        "gold_source_cited_when_answered": rate(r["gold_cited"] for r in answered if r["gold_cited"] is not None),
        "cross_project_leaks": sum(len(r["leaks"]) for r in results),
        "invalid_citation_ids_returned": sum(1 for r in results for c in r["citations"]
                                             if c["source_id"] not in sources[r["project"]]
                                             and not c["source_id"].startswith(f"{r['project']}:")),
        "unknown_ids_produced_by_model(dropped)": sum(r["unknown_ids_from_model"] for r in results),
        "quote_misses(dropped)": sum(r["quote_misses"] for r in results),
        "value_mismatches(dropped)": sum(r["value_mismatches"] for r in results),
        "detail_answers_from_title_only_or_expired": sum(
            1 for r in results if ({"title_only", "expired"} & set(r["tags"])) and r["status"] == "answered"),
        "english_answers_in_english": rate(
            all(len(re.findall(r"[가-힣]", ln)) <= len(re.findall(r"[A-Za-z]", ln)) for ln in r["answer"].splitlines())
            for r in results if "english" in r["tags"] and r["status"] in ("answered", "partial")),
        "echo_like_model_claims": _echo_stats(results),
        "model_echo_claims_enriched": sum(r.get("echo_enriched", 0) for r in results),
        "korean_model_claims_haeyo": _haeyo_stats(results),
        "model_calls_total": sum(r["model_calls"] for r in results),
        "latency_ms": {"mean": round(statistics.mean(lat), 1), "p50": round(statistics.median(lat), 1),
                       "p95": round(sorted(lat)[max(0, int(len(lat) * 0.95) - 1)], 1), "max": max(lat)},
        "failures": [{"id": r["id"], "expected": r["expected_status"], "got": r["status"], "route": r["route"],
                      "key_facts_ok": r["key_facts_ok"], "answer": r["answer"][:200]}
                     for r in results if not r["status_ok"] or r["key_facts_ok"] is False or not r["route_ok"]],
    }
    return {"summary": summary, "results": results, "review": review}


def _model_lines(results):
    """모델이 만든 답변 줄(서버 문장·정형 응답·보류 안내 제외)."""
    for r in results:
        if not r["model_calls"] or r["status"] not in ("answered", "partial"):
            continue
        for line in r["answer"].splitlines():
            if line.startswith(("(서버 확인)", "(Server check)", "[일부", "[Partly", "공지 기준으로", "According to the official notice")) \
                    or "순서로 둘러봐요" in line or " stops: " in line or re.match(r"^\d{4}-\d{2}-\d{2}\(.\) ", line) \
                    or MSG_MARKERS(line):
                continue
            yield r, re.sub(r"\s*(\[\d+\])+\s*$", "", line).strip()


def MSG_MARKERS(line: str) -> bool:
    return line.startswith(("확인된 자료에서", "I couldn't find", "이 공지는 제목만"))


def _echo_stats(results):
    """질문을 거의 되풀이한 주장: 주장 토큰(조사 제거·2-gram 포함)의 60% 이상이 질문에도 있는 경우."""
    from ragcore import textnorm

    n = echo = 0
    examples = []
    for r, line in _model_lines(results):
        a, b = set(textnorm.tokens(line)), set(textnorm.tokens(r["question"]))
        if not a:
            continue
        n += 1
        if len(a & b) / len(a) >= 0.6:
            echo += 1
            examples.append(f"{r['id']}: {line[:60]}")
    return {"echo": echo, "denominator": n, "examples": examples[:6]}


def _haeyo_stats(results):
    n = ok = 0
    for r, line in _model_lines(results):
        if r.get("language") != "ko":
            continue
        n += 1
        ok += bool(re.search(r"요[.!?]?$", line))
    return {"ok": ok, "denominator": n, "rate": round(ok / n, 3) if n else None}


def run(engine, questions_path, modes, generate, out_path=None) -> str:
    qs = _load(questions_path)
    meta = {"run_at": datetime.now(tz=SEOUL).isoformat(timespec="seconds"), "questions": len(qs),
            "by_project": {p: sum(q["project"] == p for q in qs) for p in {q["project"] for q in qs}},
            "embedder": engine.embedder.name, "generator": engine.generator.name, "chunker": CHUNKER_VERSION,
            "settings": {k: getattr(engine.settings, k) for k in ("keyword_top_n", "vector_top_n", "rrf_k", "final_top_k")},
            "vector_min_sim": engine.min_sim,
            "environment": {"python": platform.python_version(), "machine": platform.machine(),
                            "cpus": __import__("os").cpu_count(), "platform": platform.platform()}}
    report = {"meta": meta, "retrieval": retrieval_eval(engine, qs, modes)}
    if generate:
        report["full"] = full_eval(engine, qs)
    tag = f"{engine.embedder.name.split('@')[0]}__{engine.generator.name.replace(':', '-')}"
    out = Path(out_path) if out_path else ROOT / "reports" / f"eval-{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    review = report.get("full", {}).pop("review", None)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    if review:
        with (out.with_suffix(".review.csv")).open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(review[0].keys()))
            w.writeheader()
            w.writerows(review)
    short = {"retrieval": {m: v for m, v in report["retrieval"]["modes"].items()},
             "maru_ari_comparable": report["retrieval"]["maru_ari_comparable_subset"],
             "table_row_hit_at_3": report["retrieval"]["table_row_hit_at_3"]}
    if generate:
        short["full"] = {k: v for k, v in report["full"]["summary"].items() if k != "failures"}
        short["failures"] = report["full"]["summary"]["failures"]
    return json.dumps({"out": str(out)} | short, ensure_ascii=False, indent=1)
