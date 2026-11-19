"""저장된 모델 출력을 다시 넣어 검증 규칙만 바꾼 효과를 잰다(모델 호출 없음).

    python scripts/replay_eval.py reports/v0.3.0/eval-e5__qwen2.5-3b.json --out reports/v0.3.0/replay/eval-e5__qwen2.5-3b.json

같은 질문·같은 검색 결과에서 원래 평가가 받은 raw 출력을 순서대로 돌려준다. 검색 근거가 원래와 다르면
(근거 ID 목록 불일치) 그 문항은 'evidence_changed'로 표시한다. 지연 시간은 원래 실행 값을 그대로 옮긴다.
원래 실행에서 생성이 실패한 부분(raw 없음)은 그대로 실패시켜 unavailable을 재현한다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from ragcore.generation import GenerationError, GenOutput  # noqa: E402
from ragcore.services import build  # noqa: E402


class ReplayGenerator:
    def __init__(self, original: dict, name: str):
        self.name = name
        # 같은 질문 문장이 여러 문항(기준 시각·맥락만 다름)에 있으므로 문항 순서대로 하나씩 꺼낸다
        self.rows = [(r["question"], list(r.get("raw_outputs") or []), list(r.get("evidence_ids") or []))
                     for r in original["full"]["results"]]
        self.queue, self.ev_ids = [], []
        self.changed: set[str] = set()

    def start(self, question):
        q, raws, evs = self.rows.pop(0)
        assert q == question, (q, question)
        self.queue, self.ev_ids = raws, evs

    def generate(self, question, language, evidences, today=None, persona=""):
        t = time.perf_counter()
        want = self.ev_ids
        got = [[ev.eid, ev.source_id, ev.locator] for ev in evidences]
        q = self.queue
        if not q:
            raise GenerationError("replay: original run had no model output for this part")
        expected = want.pop(0) if want else None
        if expected is not None and [list(e) for e in expected] != got:
            self.changed.add(question)
        raw = q.pop(0)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:   # 저장 시 2000자로 잘린 출력
            self.changed.add(question)
            raise GenerationError(f"replay: stored output not parseable ({exc})") from exc
        claims = data.get("claims") if isinstance(data, dict) else None
        claims = [c for c in claims if isinstance(c, dict)] if isinstance(claims, list) else []
        return GenOutput(abstain=not claims, claims=claims, model=self.name,
                         latency_ms=(time.perf_counter() - t) * 1000, raw=raw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("original")
    ap.add_argument("--out", required=True)
    ap.add_argument("--questions", default="eval/questions.jsonl")
    a = ap.parse_args()
    original = json.loads(Path(a.original).read_text(encoding="utf-8"))
    engine = build(generator="fake")
    engine.generator = gen = ReplayGenerator(original, original["meta"]["generator"])
    chat = engine.chat

    def chat_with_replay(project, question, *args, **kw):
        gen.start(question)
        return chat(project, question, *args, **kw)

    engine.chat = chat_with_replay
    from eval.run_eval import run

    run(engine, str(ROOT / a.questions), ["hybrid"], True, a.out)
    out = Path(a.out)
    rep = json.loads(out.read_text(encoding="utf-8"))
    lat = {r["id"]: r["latency_ms"] for r in original["full"]["results"]}
    for r in rep["full"]["results"]:
        r["latency_ms"] = lat.get(r["id"], r["latency_ms"])
        r["evidence_changed"] = r["question"] in engine.generator.changed
    rep["full"]["summary"]["latency_ms"] = original["full"]["summary"].get("latency_ms")
    rep["meta"]["replay_of"] = a.original
    rep["meta"]["evidence_changed"] = sorted(engine.generator.changed)
    out.write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps({"out": a.out, "evidence_changed": sorted(engine.generator.changed)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
