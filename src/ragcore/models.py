"""표준 문서·조각·요청·응답 계약."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal

ContentLevel = Literal["body", "title_only"]
SourceType = Literal["public_original", "repository_data", "synthetic"]
Status = Literal["answered", "partial", "insufficient_evidence", "clarification_needed", "unavailable"]
Route = Literal["structured", "document", "composite", "clarify", "none"]


@dataclass
class Chunk:
    chunk_key: str          # 문서 안에서 안정적인 키 (예: "row-02", "sec-1-p-3")
    locator: str            # 사람이 읽는 위치 표시 (예: "장학표 > 성적우수 장학금 > 행 2")
    text: str               # 검색·인용에 사용한 원문
    structured: dict[str, Any] = field(default_factory=dict)  # 날짜·끼니·장소 ID 등


@dataclass
class Document:
    project: str
    source_id: str          # 프로젝트 안에서 안정적인 원본 ID
    collection: str         # 어댑터 allowlist 단위 (meals, notices, scholarship, places ...)
    title: str
    body: str | None
    url: str | None
    language: str
    content_level: ContentLevel
    source_type: SourceType
    published_at: date | None = None
    checked_at: datetime | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    is_public: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)

    def content_hash(self) -> str:
        payload = {"title": self.title, "body": self.body, "chunks": [asdict(c) for c in self.chunks]}
        return _hash(payload)

    def meta_hash(self) -> str:
        payload = {
            "url": self.url, "language": self.language, "content_level": self.content_level,
            "source_type": self.source_type, "published_at": self.published_at, "valid_from": self.valid_from,
            "valid_to": self.valid_to, "is_public": self.is_public, "metadata": self.metadata,
            "collection": self.collection,
        }
        return _hash(payload)

    @property
    def version(self) -> str:
        return self.content_hash()[:12]


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class Evidence:
    """검색으로 선택된 근거 조각. 생성 모델에는 eid·text만 전달된다."""
    eid: str                 # 요청 안에서만 유효한 인용 ID (E1, E2 ...)
    chunk_id: int
    document_id: int
    project: str
    source_id: str
    title: str
    url: str | None
    text: str
    locator: str
    content_level: str
    source_type: str
    published_at: date | None
    checked_at: datetime | None
    valid_from: date | None
    valid_to: date | None
    structured: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, Any] = field(default_factory=dict)


@dataclass
class Citation:
    source_id: str
    title: str
    url: str | None
    quote: str
    locator: str
    as_of: str | None        # 게시일/확인 시각/적용 기간 중 해당 근거의 기준
    source_type: str
    note: str | None = None  # "기간 종료", "제목만 있음" 등


@dataclass
class ChatResult:
    status: Status
    route: Route
    answer: str
    citations: list[Citation]
    as_of: str
    request_id: str
    # 아래는 로그·평가용 (API 응답에는 debug 옵션일 때만)
    debug: dict[str, Any] = field(default_factory=dict)

    def public_dict(self, include_debug: bool = False) -> dict[str, Any]:
        out = {
            "status": self.status, "route": self.route, "answer": self.answer,
            "citations": [asdict(c) for c in self.citations], "as_of": self.as_of, "request_id": self.request_id,
        }
        if include_debug:
            out["debug"] = self.debug
        return out
