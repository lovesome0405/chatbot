"""멱등 적재.

- 키: (project, source_id). 내용 해시·메타데이터 해시·임베딩 모델·분할 버전이 모두 같으면 건너뛴다.
- 내용이 바뀌면 그 문서의 조각만 한 트랜잭션에서 교체한다(중단 시 이전 버전 유지 → 재실행 안전).
- 메타데이터만 바뀌면 문서 행만 갱신한다.
- 삭제·비공개 전환은 "complete"로 끝난 컬렉션에서만 실행 마지막에 반영한다. 수집 실패 컬렉션은 삭제로 보지 않는다.
- allowlist 밖 컬렉션(계정·커뮤니티·사진·택시방·학생 의견 등)은 거부한다.
"""

from __future__ import annotations

import logging
import time

from . import textnorm
from .adapter import Adapter, SyncBatch
from .chunking import CHUNKER_VERSION

log = logging.getLogger("ragcore.ingest")


def sync(adapter: Adapter, store, embedder, batch: SyncBatch | None = None, fail_after: int | None = None) -> dict:
    """fail_after: 테스트용. n개 문서 처리 후 예외를 내 중단 상황을 재현한다."""
    t0 = time.perf_counter()
    batch = batch or adapter.load()
    run_id = store.start_run(adapter.project)
    stats = {"inserted": 0, "replaced": 0, "meta_updated": 0, "unchanged": 0, "rejected": 0, "private_removed": 0,
             "deleted": 0, "chunks_embedded": 0}
    try:
        processed = 0
        for doc in batch.documents:
            if doc.project != adapter.project or doc.collection not in adapter.allowed_collections:
                stats["rejected"] += 1
                log.warning("rejected document outside allowlist", extra={"collection": doc.collection})
                continue
            state = store.doc_state(doc.project, doc.source_id)
            if not doc.is_public:
                if state:
                    store.delete_document(doc.project, doc.source_id)
                    stats["private_removed"] += 1
                continue
            same_index = state and state.embed_model == embedder.name and state.chunker_version == CHUNKER_VERSION
            if same_index and state.content_hash == doc.content_hash():
                if state.meta_hash != doc.meta_hash():
                    store.update_meta(state.id, doc, run_id)
                    stats["meta_updated"] += 1
                else:
                    store.touch(state.id, run_id)
                    stats["unchanged"] += 1
            else:
                texts = [textnorm.search_text(doc.title, c.locator, c.text) for c in doc.chunks]
                embs = embedder.embed_passages([f"{doc.title}\n{c.text}" for c in doc.chunks])
                store.replace_document(doc, texts, embs, embedder.name, CHUNKER_VERSION, run_id)
                stats["replaced" if state else "inserted"] += 1
                stats["chunks_embedded"] += len(doc.chunks)
            processed += 1
            if fail_after is not None and processed >= fail_after:
                raise RuntimeError("simulated interruption")
        complete = [c for c, s in batch.collections.items() if s == "complete" and c in adapter.allowed_collections]
        deleted = store.delete_unseen(adapter.project, complete, run_id)
        stats["deleted"] = len(deleted)
        status = "success" if all(s == "complete" for s in batch.collections.values()) else "partial"
        store.finish_run(run_id, status, batch.collections, stats)
    except Exception:
        store.finish_run(run_id, "failed", batch.collections, stats)
        raise
    stats["status"] = status
    stats["seconds"] = round(time.perf_counter() - t0, 2)
    return stats
