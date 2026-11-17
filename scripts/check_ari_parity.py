"""Python 이식 점수 vs app.js 원본 점수 대조. 평가 질문 MARU 전체 × 모든 haystack.

    python scripts/check_ari_parity.py --app-js /path/to/ari/app.js
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters.maru.ari_baseline import haystacks, score  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-js", required=True)
    ap.add_argument("--out", default=str(ROOT / "reports" / "ari-parity.json"))
    a = ap.parse_args()
    qs = [json.loads(l) for l in (ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    msgs = [q["question"] for q in qs if q["project"] == "maru"] + ["Gyeongbokgung palace", "비 오는 날 실내", "시장-음식/food"]
    hs = haystacks(ROOT / "data" / "maru")
    cases = [{"message": m, "id": sid, "haystack": h} for m in msgs for sid, h in hs]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False)
    js = json.loads(subprocess.run(["node", str(ROOT / "scripts" / "ari_parity.mjs"), a.app_js, f.name],
                                   capture_output=True, text=True, check=True).stdout)
    mismatches = [dict(c, py_score=score(c["message"], next(h for s, h in hs if s == c["id"])))
                  for c in js if c["js_score"] != score(c["message"], next(h for s, h in hs if s == c["id"]))]
    nonzero = sum(1 for c in js if c["js_score"] > 0)
    commit = subprocess.run(["git", "-C", str(Path(a.app_js).parent), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    rep = {"ari_commit": commit, "cases": len(js), "nonzero_js_scores": nonzero, "mismatches": len(mismatches),
           "examples": mismatches[:5]}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(rep, ensure_ascii=False))
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
