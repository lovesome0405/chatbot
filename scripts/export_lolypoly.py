"""롤리폴리 공개 필드 export (운영 DB 접속 없음).

LOLYPOLY 체크아웃의 실제 수집 파이프라인(collect_meals/collect_events/collect_notices)에
저장소에 들어 있는 공개 HTML fixture를 fetcher로 주입해 **임시 SQLite 테스트 DB**에 적재한 뒤,
Meal / AcademicEvent / Notice 의 공개 필드만 JSON으로 내보낸다.

실행 (LOLYPOLY requirements.txt로 만든 별도 venv):
    .venv-export/bin/python scripts/export_lolypoly.py --repo /path/to/lolypoly --out data/lolypoly/export.json

LOLYPOLY 저장소 파일은 읽기만 한다. 임시 DB와 media 폴더는 임시 디렉터리에 만든다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PUBLIC_FIELDS = {
    "meal": ["date", "meal_type", "items", "source_url", "collected_at"],
    "event": ["title", "course", "start_date", "end_date", "source_year", "source_url", "collected_at"],
    "notice": ["post_id", "title", "category", "author", "posted_on", "is_pinned", "source_url", "collected_at"],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    repo = Path(args.repo).resolve()
    out_path = Path(args.out).resolve()
    commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    tmp = Path(tempfile.mkdtemp(prefix="lolypoly-testdb-"))
    os.environ["DJANGO_SQLITE_PATH"] = str(tmp / "test.sqlite3")
    os.environ["LOLYPOLY_MEDIA_ROOT"] = str(tmp / "media")
    os.environ.setdefault("DJANGO_SECRET_KEY", "export-only-not-secret")
    os.environ.setdefault("DJANGO_DEBUG", "1")
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    sys.path.insert(0, str(repo))
    os.chdir(tmp)  # .env 로딩 등 부수효과가 저장소에 쓰지 않도록 작업 위치를 임시 폴더로

    import django

    django.setup()
    from django.core.management import call_command

    call_command("migrate", verbosity=0)

    from campus.collectors.events import collect_events
    from campus.collectors.meals import collect_meals
    from campus.collectors.notices import collect_notices
    from campus.models import AcademicEvent, Meal, Notice
    from campus.tests.helpers import fake_fetcher, fixture

    runs = {
        "meals": collect_meals(weeks=2, fetcher=fake_fetcher(fixture("meals_2026-11-02.html"), fixture("meals_2026-11-09.html"))),
        "events": collect_events(years=[2026, 2027], fetcher=fake_fetcher(fixture("events_2026_all.html"), fixture("events_2027_all.html"))),
        "notices": collect_notices(pages=2, fetcher=fake_fetcher(fixture("notices_p1.html"), fixture("notices_p2.html"))),
    }

    def dump(qs, fields):
        rows = []
        for obj in qs:
            row = {}
            for f in fields:
                v = getattr(obj, f)
                row[f] = v.isoformat() if hasattr(v, "isoformat") else v
            rows.append(row)
        return rows

    out = {
        "provenance": {
            "kind": "repository_data",
            "description": "LOLYPOLY 저장소 campus/tests/fixtures 의 공개 HTML(공식 홈페이지에서 2026-11-02 수집해 저장된 것)을 "
                           "LOLYPOLY 자체 수집 코드로 임시 테스트 DB에 적재한 뒤 공개 필드만 export",
            "lolypoly_commit": commit,
            "collection_runs": {k: {"status": r.status, "item_count": r.item_count, "message": r.message} for k, r in runs.items()},
            "schema": PUBLIC_FIELDS,
            "excluded": ["accounts", "community", "taxi", "feedback", "bus", "photos"],
        },
        "meals": dump(Meal.objects.all(), PUBLIC_FIELDS["meal"]),
        "events": dump(AcademicEvent.objects.all(), PUBLIC_FIELDS["event"]),
        "notices": dump(Notice.objects.all(), PUBLIC_FIELDS["notice"]),
        "meal_hours": _meal_hours(fixture("meals_2026-11-09.html")),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: len(v) for k, v in out.items() if isinstance(v, list)} | {"commit": commit,
          "runs": out["provenance"]["collection_runs"]}, ensure_ascii=False))
    return 0


def _meal_hours(html: str) -> list[dict]:
    """식단 페이지 fixture의 식사시간표(table.tbl_table.time). LOLYPOLY 모델에는 없는 표라 별도로 읽는다."""
    from bs4 import BeautifulSoup

    table = BeautifulSoup(html, "html.parser").select_one("table.tbl_table.time")
    if table is None:
        return []
    heads = [th.get_text(strip=True) for th in table.select("thead th")]
    rows = []
    for tr in table.select("tbody tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
        rows.append(dict(zip([h or "구분" for h in heads], cells)))
    return [{"source_url": "https://www.kopo.ac.kr/chuncheon/content.do?menu=4819", "caption": "식사시간표",
             "headers": [h or "구분" for h in heads], "rows": rows}]


if __name__ == "__main__":
    raise SystemExit(main())
