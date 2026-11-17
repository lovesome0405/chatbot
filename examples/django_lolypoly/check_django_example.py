"""Django RequestFactory로 예제 view를 실제 호출해 본다(LOLYPOLY와 같은 Django 5.2.19, 별도 최소 설정).

    RAG_API_URL=http://127.0.0.1:8088 RAG_APP_KEY=local-demo-lolypoly .venv-export/bin/python examples/django_lolypoly/check_django_example.py
"""

import json
import sys
from pathlib import Path

import django
from django.conf import settings

sys.path.insert(0, str(Path(__file__).parent))
settings.configure(DEBUG=True, ROOT_URLCONF=__name__, ALLOWED_HOSTS=["*"], SECRET_KEY="example-only")
django.setup()

from django.http import JsonResponse  # noqa: E402
from django.test import RequestFactory  # noqa: E402

from rag_client import ask_rag  # noqa: E402

urlpatterns = []


def rag_answer(request):
    q = (request.GET.get("q") or "")[:500]
    return JsonResponse(ask_rag(q, language="ko"), json_dumps_params={"ensure_ascii": False})


resp = rag_answer(RequestFactory().get("/rag", {"q": sys.argv[1] if len(sys.argv) > 1 else "최근 학사 공지 뭐 있어?"}))
data = json.loads(resp.content)
print(resp.status_code, data["status"], data["route"], data["answer"][:160].replace("\n", " / "))
print([c["source_id"] for c in data["citations"]][:3])
