"""롤리폴리 공개 데이터 갱신 경로 재현 (운영 DB 접속 없음, v0.4.0).

실제 운영 경로:  LOLYPOLY `manage.py collect_all --rag-export <파일>`  →  엔진 `RAG_LOLYPOLY_EXPORT=<파일> ragcore.cli ingest --project lolypoly`
이 스크립트는 같은 코드(LOLYPOLY 수집기 + export_rag 명령 + 엔진 적재기)를 **임시 SQLite DB** 에서 두 번 돌린다.

  1차 갱신: 저장소 fixture(공식 홈페이지 2026-11-02 저장본)로 식단·학사일정·공지 수집 → export → 엔진 적재 → 질문
  2차 갱신: 식단 fixture 한 칸을 '[재현용 변경]' 메뉴로 바꾼 사본 + 공지 수집 실패 → export → 엔진 재적재 → 같은 질문
  확인: 답변이 바뀌는지, 실패한 공지는 마지막 성공 데이터·원래 수집일이 그대로인지

실행(엔진 venv에서. LOLYPOLY 의존성은 별도 venv 에 있어야 한다):
    .venv/bin/python scripts/lolypoly_refresh.py --repo ../LOLYPOLY --lolypoly-python ../.venv-loly/bin/python \\
        --out-dir reports/v0.4.0/lolypoly-refresh [--write-default data/lolypoly/export.json]
엔진 DB 는 DATABASE_URL(.env) 을 쓴다. 생성 모델은 부르지 않는다(식단·공지 목록은 정형 조회).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

CAPTURED_ON = "2026-11-02"   # LOLYPOLY campus/tests/fixtures 의 저장일(fixture 문서 기준). 시각은 미상

# LOLYPOLY 쪽에서 실행할 코드(LOLYPOLY venv). 수집기는 fixture HTML 을 fetcher 로 받는다.
LOLY_STEP = r'''
import json, os, sys
from pathlib import Path
repo, step, out, modified = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, repo)
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
import django
django.setup()
from django.core.management import call_command
from django.utils import timezone
from campus.collectors.events import collect_events
from campus.collectors.meals import collect_meals
from campus.collectors.notices import collect_notices
from campus.models import AcademicEvent, Meal, Notice
from campus.tests.helpers import fake_fetcher, failing_fetcher, fixture
call_command("migrate", verbosity=0)
runs = {}
if step == "1":
    runs["meals"] = collect_meals(weeks=2, fetcher=fake_fetcher(fixture("meals_2026-11-02.html"), fixture("meals_2026-11-09.html")))
    runs["events"] = collect_events(years=[2026, 2027], fetcher=fake_fetcher(fixture("events_2026_all.html"), fixture("events_2027_all.html")))
    runs["notices"] = collect_notices(pages=2, fetcher=fake_fetcher(fixture("notices_p1.html"), fixture("notices_p2.html")))
    # 저장본의 원래 수집일로 되돌린다(오늘로 보이지 않게). 시각은 모르므로 날짜 00:00 KST
    when = timezone.datetime.fromisoformat("%sT00:00:00+09:00")
    for m in (Meal, AcademicEvent, Notice):
        m.objects.update(collected_at=when)
    label = "fixture"
else:
    runs["meals"] = collect_meals(weeks=1, fetcher=fake_fetcher(Path(modified).read_text(encoding="utf-8")))
    runs["notices"] = collect_notices(pages=1, fetcher=failing_fetcher())
    label = "fixture-modified"
call_command("export_rag", out=out, source_label=label)
data = json.loads(Path(out).read_text(encoding="utf-8"))
if label == "fixture":
    data["provenance"]["fixture_captured_on"] = "%s"
data["provenance"]["meal_hours_note"] = "LOLYPOLY 모델에는 식사시간표가 없어 fixture 표를 그대로 붙임"
Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: [r.status, r.item_count] for k, r in runs.items()}, ensure_ascii=False))
''' % (CAPTURED_ON, CAPTURED_ON)


def meal_hours() -> list[dict]:
    """식사시간표: LOLYPOLY 모델에 없는 표라 저장소 기본 자료(fixture 표를 읽은 것)를 그대로 쓴다."""
    base = json.loads((ROOT / "data/lolypoly/export.json").read_text(encoding="utf-8")).get("meal_hours", [])
    return [t | {"collected_at": f"{CAPTURED_ON}T00:00:00+09:00"} for t in base]


def run_loly(py: str, repo: Path, tmp: Path, step: str, out: Path, modified: Path) -> dict:
    env = os.environ | {"DJANGO_SQLITE_PATH": str(tmp / "test.sqlite3"), "LOLYPOLY_MEDIA_ROOT": str(tmp / "media"),
                        "DJANGO_SECRET_KEY": "refresh-repro-only", "DJANGO_DEBUG": "1"}
    env.pop("DATABASE_URL", None)
    r = subprocess.run([py, "-c", LOLY_STEP, str(repo), step, str(out), str(modified)], cwd=tmp, env=env,
                       capture_output=True, text=True, timeout=300)
    if r.returncode:
        raise SystemExit(f"LOLYPOLY step {step} failed:\n{r.stderr[-3000:]}")
    return json.loads(r.stdout.strip().splitlines()[-1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--lolypoly-python", required=True)
    ap.add_argument("--out-dir", default="reports/v0.4.0/lolypoly-refresh")
    ap.add_argument("--write-default", help="1차 export 를 저장소 기본 자료로 복사(예: data/lolypoly/export.json)")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    out_dir = (ROOT / a.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="lolypoly-refresh-"))
    hours = meal_hours()

    # 2차용 식단: 11-10 중식 첫 메뉴를 바꾼 사본(실제 데이터 아님을 메뉴 이름에 표시)
    modified = tmp / "meals_2026-11-09.modified.html"
    src = (repo / "campus/tests/fixtures/meals_2026-11-09.html").read_text(encoding="utf-8")
    assert "상하이파스타" in src
    modified.write_text(src.replace("상하이파스타", "[재현용 변경] 김치볶음밥", 1), encoding="utf-8")

    from ragcore.ingest import sync
    from ragcore.services import build
    from ragcore.timeutil import SEOUL

    from adapters.lolypoly.adapter import LolypolyAdapter

    eng = build()
    ref = datetime(2026, 11, 10, 12, 0, tzinfo=SEOUL)
    report = {"run_at": datetime.now(tz=SEOUL).isoformat(timespec="seconds"), "lolypoly_commit": subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(), "steps": []}
    for step in ("1", "2"):
        out = out_dir / f"export-step{step}.json"
        runs = run_loly(a.lolypoly_python, repo, tmp, step, out, modified)
        data = json.loads(out.read_text(encoding="utf-8"))
        data["meal_hours"] = hours
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        ad = LolypolyAdapter(ROOT / "data/lolypoly", export_path=out)
        stats = sync(ad, eng.store, eng.embedder)
        eng.adapters["lolypoly"] = ad
        lunch = eng.chat("lolypoly", "오늘 점심 뭐야?", "ko", {}, ref)
        notices = eng.chat("lolypoly", "최근 공지 목록 알려줘", "ko", {}, ref)
        report["steps"].append({
            "step": step, "lolypoly_runs": runs, "export": str(out.relative_to(ROOT)),
            "export_collections": data["provenance"]["collections"], "ingest": stats,
            "lunch": {"status": lunch.status, "answer": lunch.answer, "as_of": [c.as_of for c in lunch.citations]},
            "notices_first": {"answer": notices.answer.splitlines()[0], "as_of": notices.citations[0].as_of if notices.citations else None},
        })
        if step == "1" and a.write_default:
            shutil.copy(out, ROOT / a.write_default)
    s1, s2 = report["steps"]
    report["checks"] = {
        "answer_changed": s1["lunch"]["answer"] != s2["lunch"]["answer"] and "[재현용 변경]" in s2["lunch"]["answer"],
        "failed_notices_kept": s2["notices_first"] == s1["notices_first"] and s2["ingest"]["deleted"] == 0,
        "notices_failed_status": s2["export_collections"]["notices"]["last_run_status"] == "failed",
    }
    # 저장소 기본 자료(1차)로 되돌려 둔다
    sync(LolypolyAdapter(ROOT / "data/lolypoly", export_path=out_dir / "export-step1.json"), eng.store, eng.embedder)
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(json.dumps(report["checks"], ensure_ascii=False))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
