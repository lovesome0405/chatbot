"""어댑터 계약.

공통 엔진은 프로젝트 이름을 모른다. 어댑터가
  1) 원본 → 표준 Document 변환 (load)
  2) 질문 → 처리 계획(Part 목록) 규칙 (plan)
  3) 정형 조회 실행 (run_structured) — 허용된 매개변수 조회만
  4) 요청 context 검증(허용된 ID만 통과)
  5) 동의어·한영 별칭 사전
을 제공한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .models import Citation, Document

DETAIL_TERMS = [
    "서류", "자격", "방법", "절차", "조건", "대상", "금액", "얼마", "어떻게", "기간", "내용", "필요", "준비", "제출", "신청",
    "documents", "document", "requirements", "required", "eligib", "how to", "procedure", "amount", "apply",
]
TIME_SENSITIVE_TERMS = [
    "운영시간", "운영 시간", "몇 시", "몇시", "입장료", "요금", "가격", "얼마", "마감", "휴무", "휴궁", "휴관", "열려", "열어", "개방",
    "영업", "지금", "현재", "opening hours", "hours", "open", "fee", "price", "ticket", "admission", "closed", "deadline",
    "currently", "right now",
]
_SPLIT = re.compile(r"\s*(?:그리고|그리고요|또한|,\s*and|\band also\b|\balso\b|\band\b|이랑|(?<=[가-힣])랑(?=\s)|하고(?=\s)|[?？])\s*")


@dataclass
class Part:
    kind: str                      # structured | document | clarify
    text: str
    intent: str = "doc"
    params: dict[str, Any] = field(default_factory=dict)
    clarify: str | None = None
    needs_detail: bool = False
    time_sensitive: bool = False
    source_ids: list[str] | None = None      # 검색 범위를 특정 원본으로 제한(명시적으로 전달된 ID)
    collections: list[str] | None = None
    keep_order: list[str] | None = None      # 앱이 이미 계산한 순서를 보존할 원본 ID 순서
    user_text: str | None = None              # 힌트를 붙이기 전 사용자 질문(되풀이 검사는 이것과 비교)


@dataclass
class Claim:
    text: str
    citations: list[Citation]


@dataclass
class PartResult:
    status: str                    # answered | insufficient_evidence | unavailable | clarification_needed
    claims: list[Claim] = field(default_factory=list)
    message: str = ""              # 보류·오류 시 안내 문장
    related: list[Citation] = field(default_factory=list)
    model_calls: int = 0
    debug: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncBatch:
    documents: list[Document]
    collections: dict[str, str]   # collection → "complete" | "failed" (failed면 삭제 반영 안 함)


class Adapter:
    project: str = ""
    allowed_collections: set[str] = set()
    aliases: dict[str, list[str]] = {}
    structured_keys: dict[str, set[str]] = {}     # collection → 허용된 조회 키

    def load(self) -> SyncBatch:
        raise NotImplementedError

    def validate_context(self, context: dict | None) -> dict:
        return {}

    def classify(self, text: str, lang: str, ctx: dict, now: datetime) -> Part:
        return Part(kind="document", text=text, needs_detail=has_any(text, DETAIL_TERMS),
                    time_sensitive=has_any(text, TIME_SENSITIVE_TERMS))

    def plan(self, question: str, lang: str, ctx: dict, now: datetime) -> list[Part]:
        whole = self.classify(question, lang, ctx, now)
        pieces = [p for p in _SPLIT.split(question) if p and len(p.strip()) >= 3]
        if len(pieces) >= 2:
            parts = [self.classify(p, lang, ctx, now) for p in pieces]
            kinds = {(p.kind, p.intent) for p in parts}
            if len(kinds) >= 2:
                return parts
        return [whole]

    def run_structured(self, part: Part, store, now: datetime, lang: str) -> PartResult:
        raise NotImplementedError(part.intent)


def has_any(text: str, terms: list[str]) -> bool:
    t = (text or "").lower()
    return any(term in t for term in terms)
