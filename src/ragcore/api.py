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

from fastapi import Depends, FastAPI, Header, HTTPException, Request
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
                   allow_headers=["content-type"], allow_credentials=False)
_hits: dict[str, deque] = defaultdict(deque)


def project_from_key(authorization: str | None = Header(default=None)) -> str:
    key = (authorization or "").removeprefix("Bearer ").strip()
    project = engine().settings.app_keys.get(key) if key else None
    if not project:
        raise HTTPException(status_code=401, detail="invalid app credential")
    return project


def _run(project: str, body: ChatIn) -> ChatOut:
    eng = engine()
    ref = None
    if body.reference_time is not None:
        if not eng.settings.allow_reference_time:
            raise HTTPException(status_code=400, detail="reference_time is disabled on this server")
        ref = body.reference_time if body.reference_time.tzinfo else body.reference_time.replace(tzinfo=SEOUL)
    res = eng.chat(project, body.question, body.language, body.context, ref)
    return ChatOut(**res.public_dict())


@app.post("/v1/chat", response_model=ChatOut)
def chat(body: ChatIn, project: str = Depends(project_from_key)):
    return _run(project, body)


@app.post("/v1/public/chat", response_model=ChatOut)
def public_chat(body: ChatIn, request: Request):
    ip = request.client.host if request.client else "?"
    q, now = _hits[ip], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= 20:
        raise HTTPException(status_code=429, detail="too many requests")
    q.append(now)
    return _run(engine().settings.public_project, body)


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
