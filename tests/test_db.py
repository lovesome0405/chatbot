"""실제 PostgreSQL+pgvector, fake 임베딩·생성으로 필수 통과 조건을 검증한다."""

import copy
from datetime import date, datetime

import pytest

from ragcore.adapter import SyncBatch
from ragcore.generation import FakeGenerator, GenerationError
from ragcore.ingest import sync
from ragcore.models import Chunk, Document
from ragcore.timeutil import SEOUL


def ref(s):
    return datetime.fromisoformat(s).replace(tzinfo=SEOUL)


def sources(res):
    return [c.source_id for c in res.citations]


# ── 적재 ─────────────────────────────────
def test_repeat_ingest_no_duplicates(engine):
    before = engine.store.counts()
    for a in engine.adapters.values():
        st = sync(a, engine.store, engine.embedder)
        assert st["inserted"] == st["replaced"] == st["deleted"] == 0
    assert engine.store.counts() == before and before["duplicate_chunks"] == 0


def _batch(engine, mutate):
    ad = engine.adapters["lolypoly"]
    b = ad.load()
    docs = copy.deepcopy(b.documents)
    mutate(docs)
    return ad, SyncBatch(docs, dict(b.collections))


def test_replaced_document_old_chunks_not_exposed(engine):
    def m(docs):
        d = next(x for x in docs if x.source_id == "kopo-4799-scholarship")
        for c in d.chunks:
            c.text = c.text.replace("1년간 교육비 전액면제", "갱신된 지급 문구")
    ad, b = _batch(engine, m)
    st = sync(ad, engine.store, engine.embedder, b)
    assert st["replaced"] == 1 and st["unchanged"] >= 100
    rows = engine.store.keyword_search("lolypoly", "'1년간'", 50, date(2026, 11, 17))
    assert not any("1년간 교육비" in r["text"] for r in rows)
    assert engine.store.keyword_search("lolypoly", "'갱신된'", 5, date(2026, 11, 17))


def test_delete_only_when_collection_complete(engine):
    ad, b = _batch(engine, lambda docs: docs.remove(next(x for x in docs if x.source_id == "notice:782263")))
    b.collections["notices"] = "failed"  # 부분 수집 실패 → 삭제로 간주하지 않음
    assert sync(ad, engine.store, engine.embedder, b)["deleted"] == 0
    assert engine.store.doc_state("lolypoly", "notice:782263")
    b.collections["notices"] = "complete"
    assert sync(ad, engine.store, engine.embedder, b)["deleted"] == 1
    assert engine.store.doc_state("lolypoly", "notice:782263") is None
    assert not engine.store.keyword_search("lolypoly", "'국가기술자격검정'", 10, date(2026, 11, 17))


def test_private_transition_removed(engine):
    def m(docs):
        next(x for x in docs if x.source_id == "meal-hours").is_public = False
    ad, b = _batch(engine, m)
    assert sync(ad, engine.store, engine.embedder, b)["private_removed"] == 1
    assert engine.store.doc_state("lolypoly", "meal-hours") is None


def test_allowlist_rejects_private_collections(engine):
    def m(docs):
        docs.append(Document("lolypoly", "community:1", "community", "익명 글", "내용", None, "ko", "body", "repository_data",
                             chunks=[Chunk("c", "c", "익명 커뮤니티 글")]))
        docs.append(Document("lolypoly", "taxi:1", "taxi", "택시방", "방", None, "ko", "body", "repository_data",
                             chunks=[Chunk("c", "c", "택시방")]))
    ad, b = _batch(engine, m)
    assert sync(ad, engine.store, engine.embedder, b)["rejected"] == 2
    assert engine.store.doc_state("lolypoly", "community:1") is None


def test_interrupted_sync_is_safe_to_retry(engine):
    def m(docs):
        for d in docs[:5]:
            d.title += " (개정)"
    ad, b = _batch(engine, m)
    with pytest.raises(RuntimeError):
        sync(ad, engine.store, engine.embedder, b, fail_after=2)
    st = sync(ad, engine.store, engine.embedder, b)
    assert st["replaced"] == 3 and st["deleted"] == 0
    assert engine.store.counts()["duplicate_chunks"] == 0


def test_embedder_change_triggers_reindex(engine):
    class OtherFake(type(engine.embedder)):
        name = "fake-hash-v2"
    st = sync(engine.adapters["campus-library"], engine.store, OtherFake())
    assert st["replaced"] == 2


# ── 범위 ─────────────────────────────────
def test_no_cross_project_evidence(engine):
    lo = engine.chat("lolypoly", "식사시간 알려줘", "ko", {}, ref("2026-11-10T12:00"))
    ma = engine.chat("maru", "식사시간 알려줘", "ko", {}, ref("2026-11-10T12:00"))
    lo_src = {d["source_id"] for d in engine.store.documents("lolypoly")}
    ma_src = {d["source_id"] for d in engine.store.documents("maru")}
    assert set(sources(lo)) <= lo_src and set(sources(ma)) <= ma_src
    assert "meal-hours" in sources(lo) and "synthetic:maru-tour-meal-time" in sources(ma)
    leak = engine.chat("lolypoly", "경복궁 수문장", "ko", {}, ref("2026-11-10T12:00"))
    assert not any(s.startswith(("place:", "course:")) for s in sources(leak))


def test_third_domain_registered_only(engine):
    res = engine.chat("campus-library", "도서 대출은 몇 권까지 돼?", "ko", {}, ref("2026-11-17T12:00"))
    assert res.status == "answered" and "guide:loan" in sources(res)


# ── 정형 조회 ───────────────────────────
def test_meal_present_empty_missing_are_distinct(engine):
    ok = engine.chat("lolypoly", "오늘 점심 뭐야?", "ko", {}, ref("2026-11-10T12:00"))
    empty = engine.chat("lolypoly", "오늘 점심 뭐야?", "ko", {}, ref("2026-11-08T12:00"))
    missing = engine.chat("lolypoly", "오늘 점심 뭐야?", "ko", {}, ref("2026-11-17T12:00"))
    assert ok.status == "answered" and "상하이파스타" in ok.answer and ok.debug["model_calls"] == 0
    assert empty.status == "answered" and "비어" in empty.answer
    assert missing.status == "insufficient_evidence" and "레코드가 없어" in missing.answer
    assert "meal:" not in " ".join(sources(missing))  # 다른 날짜 근사 결과 없음


def test_clarification_single_question(engine):
    res = engine.chat("lolypoly", "오늘 메뉴 뭐야?", "ko", {}, ref("2026-11-10T12:00"))
    assert res.status == "clarification_needed" and res.answer.count("?") == 1


def test_ari_ranking_order_preserved(engine):
    ids = ["rainy-day-indoor-heritage", "palace-history-course", "night-traditional-culture-course"]
    res = engine.chat("maru", "추천 순위 알려줘", "ko", {"ranked_route_ids": ids}, ref("2026-11-17T12:00"))
    assert sources(res) == [f"course:{i}" for i in ids]


# ── 보류 ─────────────────────────────────
def test_title_only_notice_returns_link_not_details(engine):
    res = engine.chat("lolypoly", "국가기술자격검정 수수료 지원 신청 서류가 뭐야?", "ko", {}, ref("2026-11-17T12:00"))
    assert res.status == "insufficient_evidence"
    assert res.citations[0].source_id == "notice:782263" and res.citations[0].url and res.citations[0].note == "제목만 있음"


def test_expired_notice_not_used_for_answer(engine):
    after = engine.chat("maru", "경복궁 근정전 월대 지금 올라갈 수 있어?", "ko", {}, ref("2026-11-17T12:00"))
    assert after.status == "insufficient_evidence"
    exp = [c for c in after.citations if c.source_id == "royal:20260830151817711582"]
    assert exp and all("기간 종료" in c.note for c in exp)
    inside = engine.chat("maru", "경복궁 근정전 월대 출입 제한 기간 지금이야?", "ko", {}, ref("2026-09-15T12:00"))
    assert inside.status == "answered" and "royal:20260830151817711582" in sources(inside)
    assert "synthetic:royal-gbg-special-opening" not in {d["source_id"] for d in engine.store.documents("maru")}
    assert "기간 안" in inside.answer  # 서버가 메타데이터로 계산한 기간 확인 문장


def test_time_sensitive_without_dated_source(engine):
    res = engine.chat("maru", "경복궁 입장료 얼마야?", "ko", {}, ref("2026-11-17T12:00"))
    assert res.status == "insufficient_evidence"


def test_generation_failure_is_unavailable_not_answer(engine):
    engine.generator = FakeGenerator(fail=True)
    res = engine.chat("lolypoly", "학과수석 입학자 장학금 혜택", "ko", {}, ref("2026-11-17T12:00"))
    assert res.status == "unavailable" and "생성된 답변 아님" in res.answer
    assert all(c.note == "검색 결과(생성 실패)" for c in res.citations)


def test_bad_citation_ids_never_returned(engine):
    engine.generator = FakeGenerator(bad_citation=True)
    res = engine.chat("lolypoly", "학과수석 입학자 장학금 혜택", "ko", {}, ref("2026-11-17T12:00"))
    assert res.status == "insufficient_evidence"
    assert res.debug["parts"][0]["unknown_ids"] >= 1
    valid = {d["source_id"] for d in engine.store.documents("lolypoly")}
    assert set(sources(res)) <= valid


def test_composite_partial(engine):
    res = engine.chat("lolypoly", "내일 점심이랑 기숙사 신청 방법 알려줘", "ko", {}, ref("2026-11-13T12:00"))
    assert res.route == "composite" and res.status == "partial"
    assert "간편식" in res.answer and "[일부는 확인하지 못했어요]" in res.answer


def test_unexpected_error_is_unavailable(engine, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(engine.store, "keyword_search", boom)
    res = engine.chat("maru", "경복궁은 어떤 곳이야?", "ko", {}, ref("2026-11-17T12:00"))
    assert res.status == "unavailable" and res.citations == []


# ── API ──────────────────────────────────
def test_api_scope_and_contract(engine, monkeypatch, db_url):
    from fastapi.testclient import TestClient

    from ragcore import api

    engine.settings.app_keys = {"k-lo": "lolypoly", "k-ma": "maru"}
    engine.settings.allow_reference_time = False
    monkeypatch.setattr(api, "engine", lambda: engine)
    c = TestClient(api.app)
    assert c.post("/v1/chat", json={"question": "오늘 점심"}).status_code == 401
    assert c.post("/v1/chat", headers={"Authorization": "Bearer k-lo"},
                  json={"question": "오늘 점심 뭐야?", "project": "maru"}).status_code == 422
    assert c.post("/v1/chat", headers={"Authorization": "Bearer k-lo"},
                  json={"question": "오늘 점심 뭐야?", "reference_time": "2026-11-10T12:00:00"}).status_code == 400
    r = c.post("/v1/chat", headers={"Authorization": "Bearer k-ma"}, json={"question": "경복궁은 어떤 곳이야?"}).json()
    assert set(r) == {"status", "route", "answer", "citations", "as_of", "request_id"}
    assert all(x["source_id"].startswith(("place:", "course:", "synthetic:")) for x in r["citations"])
    pub = c.post("/v1/public/chat", json={"question": "학과수석 입학자 장학금"}).json()
    assert not any(x["source_id"].startswith("kopo-") for x in pub["citations"])  # 공개 엔드포인트는 MARU 범위 고정
    assert c.get("/health").json()["db"] is True


def test_logs_exclude_question_text(engine, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="ragcore.request"):
        engine.chat("lolypoly", "비밀스러운질문문장", "ko", {}, ref("2026-11-17T12:00"))
    assert caplog.records and "비밀스러운질문문장" not in caplog.text and "request_id" in caplog.text


def test_access_restriction_status_decided_by_code(engine):
    """공지의 조치 유형(access_restricted)과 적용 기간으로 출입 상태를 서버가 판정한다. 모델이 보류해도 답한다."""
    engine.generator = FakeGenerator(min_overlap=999)  # 모델이 아무 주장도 내지 않는 상황
    inside = engine.chat("maru", "경복궁 근정전 월대 지금 올라갈 수 있어?", "ko", {}, ref("2026-09-15T12:00"))
    assert inside.status == "answered" and "royal:20260830151817711582" in sources(inside)
    assert "출입이 제한" in inside.answer and "2026-10-31" in inside.answer
    en = engine.chat("maru", "Can I walk up onto the Geunjeongjeon terrace right now?", "en", {}, ref("2026-09-15T12:00"))
    assert en.status == "answered" and "restricted" in en.answer
    after = engine.chat("maru", "경복궁 근정전 월대 지금 올라갈 수 있어?", "ko", {}, ref("2026-11-17T12:00"))
    assert after.status == "insufficient_evidence"   # 종료 후에는 이 공지만으로 현재 출입 가능 여부를 확정하지 않음
    other = engine.chat("maru", "경복궁 입장료 얼마야?", "ko", {}, ref("2026-09-15T12:00"))
    assert "출입이 제한" not in other.answer        # 대상이 다른 질문에는 출입 제한 판정을 붙이지 않음


def test_explicit_place_scope_skips_relevance_gate(engine):
    """장소를 명시적으로 고른 뒤의 막연한 후속 질문도 그 장소 근거를 모델에 전달한다."""
    res = engine.chat("maru", "여기는 어떤 곳이야?", "ko", {"place_id": "jongmyo-shrine"}, ref("2026-11-17T12:00"))
    part = res.debug["parts"][0]
    assert part["kind"] == "document" and part["chunk_ids"]                      # 근거가 관문에서 다 버려지지 않음
    assert {s for s, _, _ in part["ranks"]} == {"place:jongmyo-shrine"}           # 선택한 장소 근거만
