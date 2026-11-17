"""키워드 / 벡터 / RRF 결합.

RRF: 등장한 순위 목록마다 1/(k + rank)를 더한다(rank는 1부터). 순위 합산 점수이며 정답 확률이 아니다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date

from . import textnorm


@dataclass
class Retrieved:
    rows: list[dict]                    # 최종 순서의 조각 행
    keyword_ids: list[int] = field(default_factory=list)
    vector_ids: list[int] = field(default_factory=list)
    latency_ms: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


def rrf(rank_lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for r, cid in enumerate(ranks, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + r)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def retrieve(store, embedder, settings, *, project: str, question: str, aliases: dict, as_of: date, mode: str | None = None,
             source_ids=None, collections=None, include_expired=False, top_k: int | None = None) -> Retrieved:
    mode = mode or settings.retrieval_mode
    top_k = top_k or settings.final_top_k
    out = Retrieved(rows=[])
    by_id: dict[int, dict] = {}

    if mode in ("keyword", "hybrid"):
        t = time.perf_counter()
        q = textnorm.to_tsquery(textnorm.expand_query(question, aliases))
        kw = store.keyword_search(project, q, settings.keyword_top_n, as_of, include_expired, source_ids, collections)
        out.latency_ms["keyword"] = round((time.perf_counter() - t) * 1000, 1)
        out.keyword_ids = [r["chunk_id"] for r in kw]
        for r in kw:
            by_id[r["chunk_id"]] = r
    if mode in ("vector", "hybrid"):
        t = time.perf_counter()
        try:
            vec = embedder.embed_queries([question])[0]
            vs = store.vector_search(project, vec, embedder.name, settings.vector_top_n, as_of, include_expired,
                                     source_ids, collections)
            out.vector_ids = [r["chunk_id"] for r in vs]
            for r in vs:
                by_id.setdefault(r["chunk_id"], r)["distance"] = r["distance"]
        except Exception as exc:  # 임베딩 장애 → 키워드 결과만으로 계속, 오류 종류는 로그에 남김
            out.errors.append(f"vector:{type(exc).__name__}")
        out.latency_ms["vector"] = round((time.perf_counter() - t) * 1000, 1)

    if mode == "keyword":
        order = out.keyword_ids
    elif mode == "vector":
        order = out.vector_ids
    else:
        order = [cid for cid, _ in rrf([out.keyword_ids, out.vector_ids], settings.rrf_k)]
    fused = dict(rrf([out.keyword_ids, out.vector_ids], settings.rrf_k))
    for cid in order[:top_k]:
        row = by_id[cid]
        row["rrf"] = round(fused.get(cid, 0.0), 5)
        row["kw_rank"] = out.keyword_ids.index(cid) + 1 if cid in out.keyword_ids else None
        row["vec_rank"] = out.vector_ids.index(cid) + 1 if cid in out.vector_ids else None
        out.rows.append(row)
    return out


def unique_sources(rows: list[dict], n: int) -> list[str]:
    """조각 순위를 원본 ID 순위로 접는다(같은 원본의 여러 조각은 첫 등장 위치만)."""
    return list(dict.fromkeys(r["source_id"] for r in rows))[:n]
