"""PostgreSQL + pgvector 저장소. 모든 SQL은 매개변수 바인딩만 사용한다(문자열 조립 없음)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Document

SCHEMA = Path(__file__).resolve().parents[2] / "sql" / "schema.sql"

_CHUNK_COLS = """
    c.id as chunk_id, c.document_id, c.project, c.chunk_key, c.locator, c.text, c.structured,
    d.source_id, d.title, d.url, d.content_level, d.source_type, d.published_at, d.checked_at,
    d.valid_from, d.valid_to, d.metadata, d.collection, d.language
"""

# 범위 → 공개 → 적용 기간 → (선택) 원본 ID 제한. 검색 전에 항상 적용.
_SCOPE = """
    c.project = %(project)s and d.project = %(project)s and d.is_public
    and (%(include_expired)s or ((d.valid_from is null or d.valid_from <= %(as_of)s)
                                 and (d.valid_to is null or d.valid_to >= %(as_of)s)))
    and (%(source_ids)s::text[] is null or d.source_id = any(%(source_ids)s::text[]))
    and (%(collections)s::text[] is null or d.collection = any(%(collections)s::text[]))
"""


@dataclass
class DocState:
    id: int
    content_hash: str
    meta_hash: str
    embed_model: str
    chunker_version: str


class PgStore:
    def __init__(self, dsn: str):
        self.dsn = dsn
        # Supabase 트랜잭션 풀러(포트 6543)는 연결을 공유하므로 서버측 prepared statement를 끈다
        # (Supabase best practices: conn-prepared-statements). 세션 모드(5432)·로컬은 psycopg 기본값 유지.
        pooled = ":6543/" in dsn or "pgbouncer=true" in dsn
        self.conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row,
                                    **({"prepare_threshold": None} if pooled else {}))
        self.conn.execute("create extension if not exists vector")
        register_vector(self.conn)

    def close(self):
        self.conn.close()

    def init_schema(self):
        self.conn.execute(SCHEMA.read_text(encoding="utf-8"))

    def ping(self) -> bool:
        return self.conn.execute("select 1 as ok").fetchone()["ok"] == 1

    # ── 동기화 ─────────────────────────────
    def start_run(self, project: str) -> int:
        return self.conn.execute("insert into rag_sync_run (project) values (%s) returning id", (project,)).fetchone()["id"]

    def finish_run(self, run_id: int, status: str, collections: dict, stats: dict):
        self.conn.execute(
            "update rag_sync_run set finished_at = now(), status = %s, collections = %s, stats = %s where id = %s",
            (status, Jsonb(collections), Jsonb(stats), run_id),
        )

    def doc_state(self, project: str, source_id: str) -> DocState | None:
        row = self.conn.execute(
            "select id, content_hash, meta_hash, embed_model, chunker_version from rag_document where project=%s and source_id=%s",
            (project, source_id),
        ).fetchone()
        return DocState(**row) if row else None

    def touch(self, doc_id: int, run_id: int):
        self.conn.execute("update rag_document set last_seen_run = %s where id = %s", (run_id, doc_id))

    def update_meta(self, doc_id: int, doc: Document, run_id: int):
        self.conn.execute(
            """update rag_document set url=%s, language=%s, content_level=%s, source_type=%s, published_at=%s, checked_at=%s,
               valid_from=%s, valid_to=%s, is_public=%s, metadata=%s, collection=%s, meta_hash=%s, last_seen_run=%s,
               updated_at=now() where id=%s""",
            (doc.url, doc.language, doc.content_level, doc.source_type, doc.published_at, doc.checked_at, doc.valid_from,
             doc.valid_to, doc.is_public, Jsonb(doc.metadata), doc.collection, doc.meta_hash(), run_id, doc_id),
        )

    def replace_document(self, doc: Document, search_texts: list[str], embeddings: np.ndarray, embed_model: str,
                         chunker_version: str, run_id: int) -> int:
        """문서 행 upsert + 해당 문서 조각 전체 교체를 한 트랜잭션으로. 중단되면 이전 버전이 그대로 남는다."""
        with self.conn.transaction():
            row = self.conn.execute(
                """insert into rag_document (project, source_id, collection, title, body, url, language, content_level,
                       source_type, published_at, checked_at, valid_from, valid_to, is_public, metadata, version,
                       content_hash, meta_hash, embed_model, chunker_version, last_seen_run)
                   values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   on conflict (project, source_id) do update set
                       collection=excluded.collection, title=excluded.title, body=excluded.body, url=excluded.url,
                       language=excluded.language, content_level=excluded.content_level, source_type=excluded.source_type,
                       published_at=excluded.published_at, checked_at=excluded.checked_at, valid_from=excluded.valid_from,
                       valid_to=excluded.valid_to, is_public=excluded.is_public, metadata=excluded.metadata,
                       version=excluded.version, content_hash=excluded.content_hash, meta_hash=excluded.meta_hash,
                       embed_model=excluded.embed_model, chunker_version=excluded.chunker_version,
                       last_seen_run=excluded.last_seen_run, updated_at=now()
                   returning id""",
                (doc.project, doc.source_id, doc.collection, doc.title, doc.body, doc.url, doc.language, doc.content_level,
                 doc.source_type, doc.published_at, doc.checked_at, doc.valid_from, doc.valid_to, doc.is_public,
                 Jsonb(doc.metadata), doc.version, doc.content_hash(), doc.meta_hash(), embed_model, chunker_version, run_id),
            ).fetchone()
            doc_id = row["id"]
            self.conn.execute("delete from rag_chunk where document_id = %s", (doc_id,))
            with self.conn.cursor() as cur:
                cur.executemany(
                    """insert into rag_chunk (document_id, project, chunk_key, locator, text, search_text, structured, embedding)
                       values (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [(doc_id, doc.project, c.chunk_key, c.locator, c.text, st, Jsonb(c.structured), emb)
                     for c, st, emb in zip(doc.chunks, search_texts, embeddings)],
                )
        return doc_id

    def delete_document(self, project: str, source_id: str) -> int:
        return self.conn.execute("delete from rag_document where project=%s and source_id=%s", (project, source_id)).rowcount

    def delete_unseen(self, project: str, collections: list[str], run_id: int) -> list[str]:
        """성공적으로 전체 수집된 컬렉션에서만, 이번 실행에 보이지 않은 문서를 삭제한다."""
        if not collections:
            return []
        rows = self.conn.execute(
            """delete from rag_document where project=%s and collection = any(%s)
               and (last_seen_run is null or last_seen_run <> %s) returning source_id""",
            (project, collections, run_id),
        ).fetchall()
        return [r["source_id"] for r in rows]

    def delete_project(self, project: str):
        self.conn.execute("delete from rag_document where project=%s", (project,))

    # ── 검색 ───────────────────────────────
    def _params(self, project, as_of, include_expired, source_ids, collections, **extra) -> dict[str, Any]:
        return {"project": project, "as_of": as_of, "include_expired": include_expired,
                "source_ids": list(source_ids) if source_ids else None,
                "collections": list(collections) if collections else None} | extra

    def keyword_search(self, project: str, tsquery: str, limit: int, as_of: date, include_expired=False,
                       source_ids: Iterable[str] | None = None, collections: Iterable[str] | None = None) -> list[dict]:
        if not tsquery:
            return []
        p = self._params(project, as_of, include_expired, source_ids, collections, q=tsquery, limit=limit)
        return self.conn.execute(
            f"""select {_CHUNK_COLS}, ts_rank(c.tsv, q) as kw_score
                from rag_chunk c join rag_document d on d.id = c.document_id, to_tsquery('simple', %(q)s) q
                where {_SCOPE} and c.tsv @@ q
                order by kw_score desc, c.id limit %(limit)s""",
            p,
        ).fetchall()

    def vector_search(self, project: str, vec: np.ndarray, embed_model: str, limit: int, as_of: date,
                      include_expired=False, source_ids=None, collections=None) -> list[dict]:
        p = self._params(project, as_of, include_expired, source_ids, collections, v=vec, m=embed_model, limit=limit)
        return self.conn.execute(
            f"""select {_CHUNK_COLS}, (c.embedding <=> %(v)s) as distance
                from rag_chunk c join rag_document d on d.id = c.document_id
                where {_SCOPE} and d.embed_model = %(m)s
                order by c.embedding <=> %(v)s, c.id limit %(limit)s""",
            p,
        ).fetchall()

    def structured_lookup(self, project: str, collection: str, filters: dict[str, str], allowed: set[str],
                          limit: int = 50) -> list[dict]:
        """허용된 메타데이터 키에 대한 동등 비교만. 키는 allowlist로 검사하고 값은 바인딩한다."""
        bad = set(filters) - allowed
        if bad:
            raise ValueError(f"허용되지 않은 조회 키: {sorted(bad)}")
        return self.conn.execute(
            """select d.id as document_id, d.source_id, d.title, d.body, d.url, d.metadata, d.published_at, d.checked_at,
                      d.valid_from, d.valid_to, d.content_level, d.source_type
               from rag_document d
               where d.project=%s and d.collection=%s and d.is_public and d.metadata @> %s
               order by d.source_id limit %s""",
            (project, collection, Jsonb(filters), limit),
        ).fetchall()

    def date_overlap(self, project: str, collection: str, start: date, end: date, limit: int = 30) -> list[dict]:
        """metadata.start_date/end_date(고정 키)가 [start, end]와 겹치는 문서."""
        return self.conn.execute(
            """select d.id as document_id, d.source_id, d.title, d.body, d.url, d.metadata, d.published_at, d.checked_at,
                      d.valid_from, d.valid_to, d.content_level, d.source_type
               from rag_document d
               where d.project=%s and d.collection=%s and d.is_public
                 and (d.metadata->>'start_date')::date <= %s and (d.metadata->>'end_date')::date >= %s
               order by (d.metadata->>'start_date')::date, d.source_id limit %s""",
            (project, collection, end, start, limit),
        ).fetchall()

    def documents(self, project: str, collection: str | None = None) -> list[dict]:
        return self.conn.execute(
            """select id, source_id, collection, title, url, content_level, valid_from, valid_to, metadata, published_at,
                      checked_at, source_type
               from rag_document where project=%s and is_public and (%s::text is null or collection=%s) order by source_id""",
            (project, collection, collection),
        ).fetchall()

    def chunks(self, project: str, collection: str) -> list[dict]:
        """한 컬렉션의 공개 조각(정형 행 조회용). 표 행처럼 조각 단위 구조가 있는 자료에서 쓴다."""
        return self.conn.execute(
            """select c.id as chunk_id, c.locator, c.text, c.structured, d.id as document_id, d.source_id, d.title, d.url,
                      d.metadata, d.published_at, d.checked_at, d.valid_from, d.valid_to, d.content_level, d.source_type
               from rag_chunk c join rag_document d on d.id = c.document_id
               where d.project=%s and d.collection=%s and d.is_public order by d.source_id, c.chunk_key""",
            (project, collection),
        ).fetchall()

    # ── 미리 만든 답(v0.5.0) ───────────────
    def data_version(self, project: str) -> str:
        """프로젝트 공개 문서 전체의 내용 버전. 적재로 문서가 바뀌면 값이 바뀌어 이전 캐시를 쓰지 않는다."""
        row = self.conn.execute(
            "select md5(coalesce(string_agg(source_id || ':' || version, ',' order by source_id), '')) as v "
            "from rag_document where project=%s and is_public", (project,)).fetchone()
        return row["v"]

    def cache_get(self, project: str, key: str, version: str) -> dict | None:
        row = self.conn.execute(
            "update rag_answer_cache set hits = hits + 1 where project=%s and cache_key=%s and data_version=%s returning payload",
            (project, key, version)).fetchone()
        return row["payload"] if row else None

    def cache_put(self, project: str, key: str, version: str, payload: dict, source: str = "live"):
        self.conn.execute(
            """insert into rag_answer_cache (project, cache_key, data_version, payload, source) values (%s, %s, %s, %s, %s)
               on conflict (project, cache_key) do update set data_version=excluded.data_version, payload=excluded.payload,
                 source=excluded.source, created_at=now(), hits=0""",
            (project, key, version, Jsonb(payload), source))

    def cache_clear(self, project: str | None = None) -> int:
        cur = self.conn.execute("delete from rag_answer_cache where %s::text is null or project=%s", (project, project))
        return cur.rowcount

    def first_chunk(self, document_id: int) -> dict | None:
        return self.conn.execute(
            "select id as chunk_id, locator, text, structured from rag_chunk where document_id=%s order by chunk_key limit 1",
            (document_id,),
        ).fetchone()

    def counts(self, project: str | None = None) -> dict:
        row = self.conn.execute(
            """select (select count(*) from rag_document where %(p)s::text is null or project=%(p)s) as documents,
                      (select count(*) from rag_chunk where %(p)s::text is null or project=%(p)s) as chunks,
                      (select count(*) from (select document_id, chunk_key from rag_chunk
                          group by document_id, chunk_key having count(*) > 1) x) as duplicate_chunks""",
            {"p": project},
        ).fetchone()
        return dict(row)


def dumps(o) -> str:
    return json.dumps(o, ensure_ascii=False, default=str)
