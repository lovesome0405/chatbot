"""평가 JSON → reports/EVAL.md (숫자는 JSON에서만 가져온다).

    python scripts/make_eval_md.py reports/eval-multilingual-e5-small__ollama-qwen2.5-3b.json [--fake reports/eval-...fake...json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FULL_LABELS = [
    ("route_accuracy", "경로 일치"), ("status_accuracy", "상태 일치"), ("structured_accuracy", "정형 조회 정답(상태+핵심값)"),
    ("abstention_correct", "근거 부족·되묻기 보류 적중"), ("key_facts_in_answer_or_quotes(auto proxy)", "핵심 사실 포함(자동 대리지표)"),
    ("gold_source_cited_when_answered", "답변 시 기대 출처 인용"), ("english_answers_in_english", "영어 질문 → 영어 답변"),
]


def frac(v):
    if isinstance(v, dict) and "ok" in v:
        return f"{v['ok']}/{v['denominator']}" + (f" ({v['rate']:.0%})" if v.get("rate") is not None else "")
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("real")
    ap.add_argument("--fake")
    ap.add_argument("--out", default=str(ROOT / "reports" / "EVAL.md"))
    a = ap.parse_args()
    r = json.loads(Path(a.real).read_text(encoding="utf-8"))
    m, ret, full = r["meta"], r["retrieval"], r["full"]["summary"]
    L = [f"# 평가 결과 ({m['run_at']})", "",
         f"- 질문 {m['questions']}개: " + ", ".join(f"{k} {v}" for k, v in sorted(m["by_project"].items())),
         f"- 임베딩 `{m['embedder']}`, 생성 `{m['generator']}`, 분할 `{m['chunker']}`, 시작값 {m['settings']}, 벡터 최소 유사도 {m['vector_min_sim']}",
         f"- 측정 환경: Python {m['environment']['python']}, {m['environment']['cpus']} CPU({m['environment']['machine']}), "
         f"GPU 없음, {m['environment']['platform']}. 지연은 이 컨테이너의 CPU 추론 기준",
         "- 원본 JSON·사람 검토 시트(CSV)가 같은 폴더에 있다. RRF 점수는 정답 확률이 아니다.", "",
         "## 1. 검색 비교 (같은 자료·같은 질문, 원본 ID 기준 Hit@3)", "",
         f"정의: {ret['definition']}", "",
         "| 방식 | Hit@3 | 평균 지연(ms) |", "|---|---|---|"]
    for mode, v in ret["modes"].items():
        name = {"ari_baseline": "기존 Ari scoreAriTextMatch (MARU만)", "hybrid": "RRF(k=60)"}.get(mode, mode)
        L.append(f"| {name} | {v['hit_at_3']}/{v['denominator']} | {v['mean_latency_ms']} |")
    ms, ac, tr = ret["maru_subset"], ret["maru_ari_comparable_subset"], ret["table_row_hit_at_3"]
    L += ["", f"- MARU 질문만(분모 {ms['denominator']}): keyword {ms['keyword']}, vector {ms['vector']}, RRF {ms['hybrid']}, Ari {ms['ari_baseline']}",
          f"- Ari 코퍼스(장소·코스)에 정답이 있는 질문만(분모 {ac['denominator']}): keyword {ac['keyword']}, vector {ac['vector']}, "
          f"RRF {ac['hybrid']}, Ari {ac['ari_baseline']}",
          f"- 장학표 기대 행 Hit@3(분모 {tr['denominator']}): keyword {tr['keyword']}, vector {tr['vector']}, RRF {tr['hybrid']}", "",
          "검색 실패 사례:", ""]
    for q in ret["per_question"]:
        miss = [k for k in ("keyword", "vector", "hybrid", "ari_baseline") if k in q and not q[k]["hit"]]
        if miss:
            L.append(f"- {q['id']} 기대 {q['gold']}: " + "; ".join(f"{k} → {q[k]['top3'] or '결과 없음'}" for k in miss))
    L += ["", "## 2. 전체 응답 (hybrid + 생성 + 인용 검증)", "", "| 지표 | 값 |", "|---|---|"]
    for key, label in FULL_LABELS:
        if key in full:
            L.append(f"| {label} | {frac(full[key])} |")
    fa = full["false_abstentions"]
    L += [f"| 답할 수 있는데 보류 | {fa['count']}/{fa['denominator']} |",
          f"| 다른 프로젝트 근거 노출 | {full['cross_project_leaks']} |",
          f"| 반환된 인용 중 없는 ID | {full['invalid_citation_ids_returned']} |",
          f"| 모델이 낸 없는 인용 ID(서버가 폐기) | {full['unknown_ids_produced_by_model(dropped)']} |",
          f"| 원문에 없는 발췌(서버가 폐기) | {full['quote_misses(dropped)']} |",
          f"| 근거와 다른 날짜·숫자(서버가 폐기) | {full['value_mismatches(dropped)']} |",
          f"| 제목만 있는/기간 만료 공지로 세부 답변 | {full['detail_answers_from_title_only_or_expired']} |",
          f"| 모델 호출 수(37문항 합계) | {full['model_calls_total']} |",
          f"| 지연 ms (평균/p50/p95/최대) | {full['latency_ms']['mean']} / {full['latency_ms']['p50']} / {full['latency_ms']['p95']} / {full['latency_ms']['max']} |",
          "", "### 실패·불일치 사례 (그대로 기록)", ""]
    for f in full["failures"]:
        L.append(f"- **{f['id']}** 기대 {f['expected']} → {f['got']} (경로 {f['route']}, 핵심사실 {f['key_facts_ok']}): {f['answer'][:160].replace(chr(10), ' / ')}")
    res = {x["id"]: x for x in r["full"]["results"]}
    drops = [(i, [d["reason"] for d in x["dropped"]]) for i, x in res.items() if x["dropped"]]
    if drops:
        L += ["", "서버 검증에서 버린 모델 주장: " + ", ".join(f"{i} {d}" for i, d in drops)]
    if a.fake:
        fk = json.loads(Path(a.fake).read_text(encoding="utf-8"))["full"]["summary"]
        L += ["", "## 3. 참고: fake 생성기(CI용) 같은 질문 결과", "",
              "제어 흐름 확인용이며 답변 품질 수치가 아니다.", "",
              f"- 경로 {frac(fk['route_accuracy'])}, 상태 {frac(fk['status_accuracy'])}, 정형 {frac(fk['structured_accuracy'])}, "
              f"보류 {frac(fk['abstention_correct'])}, 누출 {fk['cross_project_leaks']}, 없는 ID {fk['invalid_citation_ids_returned']}"]
    Path(a.out).write_text("\n".join(L) + "\n", encoding="utf-8")
    print(a.out)


if __name__ == "__main__":
    main()
