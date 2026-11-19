"""CLI: 적재 / 한 건 질의 / 일괄 평가.

    python -m ragcore.cli ingest [--project lolypoly|maru|campus-library|all]
    python -m ragcore.cli ask --project lolypoly "오늘 점심 뭐야?" [--as-of 2026-11-10T12:00] [--language en] [--context '{...}']
    python -m ragcore.cli eval [--modes keyword,vector,hybrid] [--generate] [--out reports/eval-....json]
    python -m ragcore.cli stats
    python -m ragcore.cli warm [--project maru|lolypoly|all] [--refresh]   # 자주 묻는 질문 답을 미리 만들어 저장(v0.5.0)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime

from .engine import to_json
from .ingest import sync
from .services import build
from .timeutil import SEOUL


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="ragcore")
    ap.add_argument("--embedder")
    ap.add_argument("--generator")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest")
    p.add_argument("--project", default="all")
    p.add_argument("--reset", action="store_true", help="해당 프로젝트 색인을 지우고 다시 적재")
    p = sub.add_parser("ask")
    p.add_argument("question")
    p.add_argument("--project", required=True)
    p.add_argument("--language")
    p.add_argument("--as-of", help="기준 시각(Asia/Seoul). 평가·데모용")
    p.add_argument("--context", default="{}")
    p.add_argument("--mode")
    p.add_argument("--debug", action="store_true")
    p = sub.add_parser("eval")
    p.add_argument("--questions", default="eval/questions.jsonl")
    p.add_argument("--modes", default="keyword,vector,hybrid")
    p.add_argument("--generate", action="store_true", help="hybrid 모드로 전체 응답(생성 포함)까지 실행")
    p.add_argument("--out")
    sub.add_parser("stats")
    p = sub.add_parser("warm", help="data/<project>/warm_questions.json 의 질문 답을 시간 상한 없이 만들어 저장")
    p.add_argument("--project", default="all")
    p.add_argument("--refresh", action="store_true", help="저장된 답을 지우고 다시 만듦")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING, format="%(message)s")

    overrides = {k: v for k, v in {"embedder": a.embedder, "generator": a.generator}.items() if v}
    engine = build(**overrides)

    if a.cmd == "ingest":
        projects = list(engine.adapters) if a.project == "all" else [a.project]
        for pr in projects:
            if a.reset:
                engine.store.delete_project(pr)
            stats = sync(engine.adapters[pr], engine.store, engine.embedder)
            print(json.dumps({"project": pr, "embedder": engine.embedder.name} | stats, ensure_ascii=False))
        print(json.dumps(engine.store.counts(), ensure_ascii=False))
    elif a.cmd == "ask":
        ref = datetime.fromisoformat(a.as_of).replace(tzinfo=SEOUL) if a.as_of else None
        res = engine.chat(a.project, a.question, a.language, json.loads(a.context), ref, a.mode)
        print(json.dumps(res.public_dict(include_debug=a.debug), ensure_ascii=False, indent=1, default=str))
    elif a.cmd == "eval":
        sys.path.insert(0, str(__import__("ragcore.registry", fromlist=["ROOT"]).ROOT))
        from eval.run_eval import run

        out = run(engine, a.questions, a.modes.split(","), a.generate, a.out)
        print(out)
    elif a.cmd == "warm":
        from .registry import ROOT

        engine.settings.gen_budget_s = 0      # 미리 만드는 답은 시간 상한 없이(밤 작업)
        if engine.settings.generator == "ollama" and engine.settings.warm_model:
            from .generation import build_generator

            engine.settings.ollama_model = engine.settings.warm_model    # 더 큰 모델로 미리 만든다
            engine.generator = build_generator(engine.settings)
        projects = list(engine.adapters) if a.project == "all" else [a.project]
        for pr in projects:
            f = ROOT / "data" / pr / "warm_questions.json"
            if not f.exists():
                continue
            if a.refresh:
                engine.store.cache_clear(pr)
            items = json.loads(f.read_text(encoding="utf-8"))["items"]
            done = {"stored": 0, "already": 0, "not_cacheable": 0}
            for it in items:
                res = engine.chat(pr, it["question"], it.get("language"), it.get("context") or {}, ask_as=it.get("ask_as"),
                                  cache_source="warm")
                kind = "already" if res.debug.get("cache_hit") else (
                    "stored" if res.status in ("answered", "partial") and res.debug.get("model_calls") else "not_cacheable")
                done[kind] += 1
            print(json.dumps({"project": pr, "items": len(items)} | done, ensure_ascii=False))
    elif a.cmd == "stats":
        print(json.dumps(engine.store.counts(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
