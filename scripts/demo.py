"""3분 시연: 같은 API 서버 하나로 두 프로젝트를 차례로 호출한다.

    (API 실행 중, .env의 RAG_ALLOW_REFERENCE_TIME=1)  python scripts/demo.py [--api http://127.0.0.1:8088]
순서: 오늘 점심 → 장학표의 한 행 인용 → 같은 서버로 영어 문화 질문 → 낡은 공지에 답변 보류
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPE = {"public_original": "실제 공개 원문", "repository_data": "저장소 데이터", "synthetic": "합성 데이터"}

STEPS = [
    ("1. 오늘 점심 (정형 조회, 모델 호출 없음)", "lolypoly", "오늘 점심 뭐야?", "ko", "2026-11-10T12:00:00",
     "기준 시각을 식단 fixture가 있는 2026-11-10으로 고정. 실제 오늘(11-17)은 레코드가 없어 '레코드 없음'을 돌려준다"),
    ("2. 장학표의 한 행 인용 (문서 검색 + 생성 + 인용 검증)", "lolypoly", "학과수석 입학자는 장학금 얼마나 받아?", "ko", None,
     "'학과수석 입학자' 행과 '직전학기 성적우수자' 행이 섞이지 않는지 locator로 확인"),
    ("3. 같은 서버, MARU 키로 영어 문화 질문 (한국어 원문 검색)", "maru", "Tell me about Jongmyo Shrine", "en", None,
     "영어 질문 → 한국어 근거 검색 → 영어 답변, 지명·출처 링크 보존"),
    ("4. 기간이 끝난 공지 → 답변 보류", "maru", "Is the Gyeongbokgung special opening open now?", "en", "2026-11-17T12:00:00",
     "공지(합성)의 적용 기간 2026-09-01~10-31이 지났으므로 현재 개방 여부를 확정하지 않는다"),
]


def env(name, default=""):
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines() if (ROOT / ".env").exists() else []:
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return os.environ.get(name, default)


def keys():
    out = {}
    for part in env("RAG_APP_KEYS").split(","):
        p, _, k = part.partition(":")
        out[p] = k
    return out


def call(api, key, body):
    req = urllib.request.Request(f"{api}/v1/chat", data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://127.0.0.1:8088")
    a = ap.parse_args()
    k = keys()
    health = json.loads(urllib.request.urlopen(f"{a.api}/health", timeout=10).read())
    print(f"서버: embedder={health['embedder']} generator={health['generator']} db={health['db']}")
    print("데이터 표시: 장학표=실제 공개 원문 / 식단·공지·MARU 장소=저장소 데이터 / 경복궁 특별 개방 공지=합성 데이터\n")
    for title, project, q, lang, ref, note in STEPS:
        body = {"question": q, "language": lang}
        if ref:
            body["reference_time"] = ref
        t = time.perf_counter()
        d = call(a.api, k[project], body)
        print(f"── {title}\n   [{project}] Q: {q}" + (f"  (기준 {ref})" if ref else ""))
        print(f"   → {d['status']} / {d['route']} / {time.perf_counter() - t:.1f}s")
        for line in d["answer"].splitlines():
            print(f"   {line}")
        for i, c in enumerate(d["citations"], 1):
            print(f"   [{i}] {c['title']} · {TYPE.get(c['source_type'], c['source_type'])} · {c['locator']}"
                  + (f" · {c['note']}" if c.get("note") else ""))
            print(f"       “{c['quote'][:110]}” {c['url'] or ''} ({c['as_of']})")
        print(f"   메모: {note}\n")


if __name__ == "__main__":
    main()
