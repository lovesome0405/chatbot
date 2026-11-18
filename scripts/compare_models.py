"""같은 질문셋의 여러 평가 JSON(생성 모델별)을 나란히 비교 → Markdown.

    python scripts/compare_models.py reports/v2/eval-e5__qwen2.5-3b.json reports/v2/eval-e5__qwen2.5-7b.json --out reports/v2/COMPARE.md
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KEYS = [("route_accuracy", "경로 일치"), ("status_accuracy", "상태 일치"), ("structured_accuracy", "정형 정답"),
        ("abstention_correct", "보류 적중"), ("key_facts_in_answer_or_quotes(auto proxy)", "핵심 사실(자동)"),
        ("gold_source_cited_when_answered", "기대 출처 인용"), ("english_answers_in_english", "영어→영어")]


def f(v):
    return f"{v['ok']}/{v['denominator']}" if isinstance(v, dict) and "ok" in v else str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--labels", help="쉼표로 구분한 열 이름(기본: 생성 모델 이름)")
    a = ap.parse_args()
    runs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.files]
    names = a.labels.split(",") if a.labels else [r["meta"]["generator"] for r in runs]
    qs = {json.loads(l)["id"]: json.loads(l) for l in (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    L = [f"# 생성 모델 비교 ({runs[0]['meta']['questions']}문항, 임베딩 {runs[0]['meta']['embedder']})", "",
         f"환경: {runs[0]['meta']['environment']['cpus']} CPU, GPU 없음. 검색 단계는 모델과 무관하게 동일하다.", "",
         "| 지표 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k, label in KEYS:
        L.append(f"| {label} | " + " | ".join(f(r["full"]["summary"].get(k, "-")) for r in runs) + " |")
    for k, label in [("echo_like_model_claims", "질문 되풀이 주장"), ("korean_model_claims_haeyo", "한국어 주장 해요체")]:
        L.append(f"| {label} | " + " | ".join(
            (f"{r['full']['summary'][k].get('echo', r['full']['summary'][k].get('ok'))}/{r['full']['summary'][k]['denominator']}"
             if k in r["full"]["summary"] else "-") for r in runs) + " |")
    L.append("| 되풀이 주장을 근거로 보강한 수 | " + " | ".join(str(r["full"]["summary"].get("model_echo_claims_enriched", "-")) for r in runs) + " |")
    for k, label in [("false_abstentions", "답할 수 있는데 보류")]:
        L.append(f"| {label} | " + " | ".join(f"{r['full']['summary'][k]['count']}/{r['full']['summary'][k]['denominator']}" for r in runs) + " |")
    for k, label in [("cross_project_leaks", "프로젝트 간 노출"), ("invalid_citation_ids_returned", "없는 인용 ID 반환"),
                     ("detail_answers_from_title_only_or_expired", "제목만·만료 공지 세부 답변"), ("model_calls_total", "모델 호출")]:
        L.append(f"| {label} | " + " | ".join(str(r["full"]["summary"][k]) for r in runs) + " |")
    L.append("| 지연 평균/p95 (초) | " + " | ".join(
        f"{r['full']['summary']['latency_ms']['mean'] / 1000:.1f} / {r['full']['summary']['latency_ms']['p95'] / 1000:.1f}" for r in runs) + " |")
    L += ["", "## 서버가 버린 모델 주장 (사유별)", "", "| 사유 | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    reasons = [collections.Counter(d["reason"] for x in r["full"]["results"] for d in x["dropped"]) for r in runs]
    for reason in sorted(set().union(*reasons)):
        L.append(f"| {reason} | " + " | ".join(str(c.get(reason, 0)) for c in reasons) + " |")
    L += ["", "## 문항별 상태 (기대와 다른 칸에 ✗)", "", "| 문항 | 기대 | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
    by = [{x["id"]: x for x in r["full"]["results"]} for r in runs]
    for qid, q in qs.items():
        cells = []
        for b in by:
            x = b.get(qid)
            if not x:
                cells.append("-")
                continue
            mark = "" if x["status_ok"] and x["key_facts_ok"] is not False else " ✗"
            cells.append(f"{x['status']}{mark}")
        if any("✗" in c for c in cells):
            L.append(f"| {qid} | {q['expected_status'][0]} | " + " | ".join(cells) + " |")
    L += ["", "(모든 모델이 기대대로 처리한 문항은 표에서 생략)", "", "## 원문에 없는 발췌 예시 (원인 분석용)", ""]
    for name, r in zip(names, runs):
        ex = [(x["id"], d) for x in r["full"]["results"] for d in x["dropped"] if d["reason"] == "quote_not_in_source"][:4]
        for qid, d in ex:
            L.append(f"- [{name}] {qid}: 발췌 “{d.get('quote', '')[:90]}” ↔ 원문 “{d.get('source_text', '')[:90]}”")
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
