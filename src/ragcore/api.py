"""로컬 API.

    uvicorn ragcore.api:app --host 127.0.0.1 --port 8088

- POST /v1/chat            : 앱 자격(Authorization: Bearer <키>)으로 서버가 프로젝트 범위를 결정
- POST /v1/public/chat     : 정적 웹(MARU) 데모 중계. RAG_PUBLIC_PROJECT 하나에만 묶이고 허용 Origin만 CORS
- GET  /health
요청 본문에 project 등 범위 필드를 넣으면 422로 거부한다(extra=forbid). 원문 질문은 기본 로그에 남기지 않는다.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from datetime import datetime
from functools import lru_cache
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from . import __version__
from .config import Settings
from .services import build, load_dotenv
from .timeutil import SEOUL

logging.basicConfig(level=logging.INFO, format="%(message)s")
load_dotenv()


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    language: Literal["ko", "en"] | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    reference_time: datetime | None = None  # RAG_ALLOW_REFERENCE_TIME=1 일 때만 사용(평가·데모)


class CitationOut(BaseModel):
    source_id: str
    title: str
    url: str | None
    quote: str
    locator: str
    as_of: str | None
    source_type: str
    note: str | None = None


class ChatOut(BaseModel):
    status: Literal["answered", "partial", "insufficient_evidence", "clarification_needed", "unavailable"]
    route: str
    answer: str
    citations: list[CitationOut]
    as_of: str
    request_id: str


@lru_cache(maxsize=1)
def engine():
    return build(Settings())


app = FastAPI(title="ragcore", version=__version__)
_settings = Settings()
app.add_middleware(CORSMiddleware, allow_origins=_settings.public_origins, allow_methods=["POST"],
                   allow_headers=["content-type"], allow_credentials=False,
                   expose_headers=["Server-Timing", "X-Request-Id", "Retry-After"])
_hits: dict[str, deque] = defaultdict(deque)


def project_from_key(authorization: str | None = Header(default=None)) -> str:
    key = (authorization or "").removeprefix("Bearer ").strip()
    project = engine().settings.app_keys.get(key) if key else None
    if not project:
        raise HTTPException(status_code=401, detail="invalid app credential")
    return project


def client_ip(request: Request, hops: int) -> str:
    """요청 제한용 클라이언트 주소. hops>0 이면 X-Forwarded-For 의 오른쪽에서 hops 번째(믿는 프록시가 붙인 값)를 쓴다.
    hops=0(기본)이면 헤더를 무시한다 → 방문객이 헤더를 꾸며 제한을 피할 수 없다."""
    peer = request.client.host if request.client else "?"
    if hops <= 0:
        return peer
    chain = [x.strip() for x in request.headers.get("x-forwarded-for", "").split(",") if x.strip()]
    return chain[-hops] if len(chain) >= hops else peer


def _timing(response: Response, res_debug: dict, total_ms: float):
    """구간별 지연을 Server-Timing 헤더로 알린다(앱·프록시가 어느 구간에서 느린지 잴 수 있게). 질문 내용은 넣지 않는다."""
    parts = res_debug.get("parts") or []
    ret = sum(sum((p.get("retrieval_ms") or {}).values()) for p in parts)
    gen = sum(p.get("gen_ms") or 0 for p in parts)
    response.headers["Server-Timing"] = f"retrieval;dur={ret:.0f}, generation;dur={gen:.0f}, total;dur={total_ms:.0f}"


def _run(project: str, body: ChatIn, response: Response | None = None) -> ChatOut:
    t0 = time.perf_counter()
    eng = engine()
    ref = None
    if body.reference_time is not None:
        if not eng.settings.allow_reference_time:
            raise HTTPException(status_code=400, detail="reference_time is disabled on this server")
        ref = body.reference_time if body.reference_time.tzinfo else body.reference_time.replace(tzinfo=SEOUL)
    elif eng.settings.allow_reference_time and eng.settings.fixed_now:
        ref = datetime.fromisoformat(eng.settings.fixed_now).replace(tzinfo=SEOUL)
    res = eng.chat(project, body.question, body.language, body.context, ref)
    if response is not None:
        _timing(response, res.debug, (time.perf_counter() - t0) * 1000)
        response.headers["X-Request-Id"] = res.request_id
    return ChatOut(**res.public_dict())


@app.post("/v1/chat", response_model=ChatOut)
def chat(body: ChatIn, response: Response, project: str = Depends(project_from_key)):
    return _run(project, body, response)


@app.post("/v1/public/chat", response_model=ChatOut)
def public_chat(body: ChatIn, request: Request, response: Response):
    st = engine().settings
    ip = client_ip(request, st.trust_proxy_hops)
    q, now = _hits[ip], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= st.public_rate_per_min:
        raise HTTPException(status_code=429, detail="too many requests", headers={"Retry-After": "60"})
    q.append(now)
    return _run(st.public_project, body, response)


@app.get("/health")
def health():
    eng = engine()
    out = {"db": False, "embedder": eng.embedder.name, "generator": eng.generator.name}
    try:
        out["db"] = eng.store.ping()
        out["counts"] = eng.store.counts()
    except Exception as exc:
        out["db_error"] = type(exc).__name__
    if hasattr(eng.generator, "health"):
        out["generator_ready"] = eng.generator.health()
    out["status"] = "ok" if out["db"] and out.get("generator_ready", True) else "degraded"
    return out
