"""롤리폴리(Django) → RAG 엔진 호출 예제. LOLYPOLY 저장소에 바로 넣지 말고 후속 작업에서 검토 후 반영한다.

서버 측에서만 호출한다(앱 키는 Django 설정/환경변수, 브라우저에 노출하지 않음). 표준 라이브러리만 사용.
    RAG_API_URL=http://127.0.0.1:8088   RAG_APP_KEY=<RAG_APP_KEYS의 lolypoly 키>

views.py 예:
    from django.http import JsonResponse
    from .rag_client import ask_rag
    def rag_answer(request):
        q = (request.GET.get("q") or "")[:500]
        return JsonResponse(ask_rag(q, language="ko"), json_dumps_params={"ensure_ascii": False})
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

UNAVAILABLE = {"status": "unavailable", "route": "none", "answer": "지금은 답변 서버에 연결할 수 없어. 원문 페이지를 확인해줘.",
               "citations": [], "as_of": "", "request_id": ""}


def ask_rag(question: str, language: str | None = None, context: dict | None = None, timeout: float = 120) -> dict:
    url = os.environ.get("RAG_API_URL", "http://127.0.0.1:8088").rstrip("/") + "/v1/chat"
    key = os.environ.get("RAG_APP_KEY", "")
    body = json.dumps({"question": question, "language": language, "context": context or {}}).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # 401(앱 키 오류)·422(요청 형식) 등은 연결 장애와 구분해 운영자가 보게 한다
        return dict(UNAVAILABLE, answer=f"답변 서버가 요청을 거부했어(HTTP {exc.code}). 관리자 설정을 확인해줘.")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        # 장애 시 로컬 문구를 RAG 답변처럼 보이지 않게 status=unavailable 로 돌려준다
        return dict(UNAVAILABLE)
