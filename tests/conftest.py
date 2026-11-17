"""테스트 공통 준비. DB 테스트는 별도 데이터베이스(rag_test)를 쓰고, 연결이 안 되면 건너뛴다(사유 표시).
실제 모델 없이 FakeEmbedder/FakeGenerator로 제어 흐름만 검증한다 — 검색 품질 수치로 해석하지 않는다."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

TEST_DB = os.environ.get("TEST_DATABASE_URL", "postgresql://rag:rag@127.0.0.1:54329/rag_test")


def _ensure_db() -> str | None:
    import psycopg

    try:
        psycopg.connect(TEST_DB, connect_timeout=3).close()
        return None
    except Exception:
        pass
    admin = TEST_DB.rsplit("/", 1)[0] + "/rag"
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as c:
            c.execute("create database rag_test")
        return None
    except Exception as exc:  # noqa: BLE001
        return f"PostgreSQL+pgvector 연결 불가({type(exc).__name__}). `docker compose up -d db` 후 다시 실행"


@pytest.fixture(scope="session")
def db_url():
    reason = _ensure_db()
    if reason:
        pytest.skip(reason)
    return TEST_DB


@pytest.fixture()
def engine(db_url):
    from ragcore.config import Settings
    from ragcore.embedding import FakeEmbedder
    from ragcore.engine import Engine
    from ragcore.generation import FakeGenerator
    from ragcore.ingest import sync
    from ragcore.registry import build_adapters
    from ragcore.store import PgStore

    store = PgStore(db_url)
    store.conn.execute("drop table if exists rag_chunk, rag_document, rag_sync_run cascade")
    store.init_schema()
    settings = Settings(database_url=db_url, embedder="fake", generator="fake")
    eng = Engine(settings, store, FakeEmbedder(), FakeGenerator(), build_adapters())
    for a in eng.adapters.values():
        sync(a, store, eng.embedder)
    yield eng
    store.close()
