"""DB 없이 도는 단위 테스트."""

from datetime import date, datetime, timezone

from adapters.maru import ari_baseline
from ragcore import textnorm
from ragcore.citations import key_values, quote_in_source, verify
from ragcore.embedding import FakeEmbedder
from ragcore.html_table import parse_tables, squash_spaced
from ragcore.models import Evidence
from ragcore.retrieval import rrf
from ragcore.timeutil import SEOUL, resolve_date, resolve_range


def test_josa_and_spacing_tokens():
    a = set(textnorm.tokens("학과수석 입학자는"))
    b = set(textnorm.tokens("학과 수석입학자"))
    assert "입학자" in a and "학과" in a and "수석" in a          # 조사 제거 + 2-gram
    assert {"학과", "수석"} <= b
    assert "뭐야" not in textnorm.tokens("장학금 뭐야?", query=True)


def test_english_fts_not_used_and_alias_expansion():
    toks = textnorm.expand_query("Tell me about Gyeongbokgung Palace", {"gyeongbokgung palace": ["경복궁"]})
    assert "경복궁" in toks and "the" not in toks
    assert textnorm.to_tsquery(["경복궁", "x'; drop"]) == "'경복궁'"  # 허용 문자 외 토큰은 버림


def test_relative_dates_use_seoul():
    utc_late = datetime(2026, 11, 9, 16, 30, tzinfo=timezone.utc)  # = 2026-11-10 01:30 KST
    assert resolve_date("오늘 점심", utc_late) == date(2026, 11, 10)
    assert resolve_date("tomorrow lunch", utc_late) == date(2026, 11, 11)
    assert resolve_date("11월 3일 저녁", utc_late) == date(2026, 11, 3)
    assert resolve_range("이번 주 일정", datetime(2026, 11, 12, tzinfo=SEOUL)) == (date(2026, 11, 9), date(2026, 11, 15))


def test_rrf_formula():
    fused = dict(rrf([[1, 2, 3], [3, 1]], k=60))
    assert abs(fused[1] - (1 / 61 + 1 / 62)) < 1e-12
    assert abs(fused[3] - (1 / 63 + 1 / 61)) < 1e-12
    assert abs(fused[2] - 1 / 62) < 1e-12


def _ev(eid, text, title="t"):
    return Evidence(eid, 1, 1, "p", "s", title, None, text, "loc", "body", "public_original", None, None, None, None)


def test_citation_verification_rules():
    evs = [_ev("E1", "구분: 교내 | 종류: 성적우수 장학금 | 수혜자격: 학과수석 입학자 1명 | 지급액 및 기간: 1년간 교육비 전액면제")]
    v = verify([
        {"text": "1년간 전액면제", "citations": [{"id": "E1", "quote": "1년간 교육비 전액면제"}]},          # 통과
        {"text": "없는 ID", "citations": [{"id": "E9", "quote": "1년간"}]},                          # unknown id
        {"text": "발췌 불일치", "citations": [{"id": "E1", "quote": "2년간 교육비"}]},                 # quote miss
        {"text": "2년간 면제", "citations": [{"id": "E1", "quote": "교육비 전액면제"}]},               # 값 불일치? (2년 X) — 한 자리 수는 검사 제외
        {"text": "2026-09-01부터", "citations": [{"id": "E1", "quote": "교육비 전액면제"}]},           # 날짜 불일치
    ], evs)
    assert [c[0] for c in v.claims] == ["1년간 전액면제", "2년간 면제"]
    assert v.unknown_ids == 1 and v.quote_misses == 1 and v.value_mismatches == 1
    assert quote_in_source("종류: 성적우수 장학금 | 지급액 및 기간: 1년간 교육비 전액면제", evs[0].text)
    assert not quote_in_source("지급액 및 기간: 1년간 | 종류: 성적우수 장학금", evs[0].text)  # 순서 뒤바뀜 거부
    assert key_values("2026-9-1, 3.0, 11:50") == ["2026-09-01", "3.0", "11:50"]


def test_rowspan_table_keeps_rows_separate():
    html = open("data/lolypoly/kopo_scholarship_4799.html", encoding="utf-8").read()
    t = parse_tables(html)[0]
    rows = {r[2]: r for r in t["rows"]}
    assert rows["학과수석 입학자 1명"][1] == "성적우수 장학금" and rows["학과수석 입학자 1명"][3] == "1년간 교육비 전액면제"
    assert rows["직전학기 학과별 성적우수자 학급당 1명"][3] == "1개학기 교육비 전액면제"
    assert "자 중" in rows["학생회 간부 또는 학교의 발전에 공헌한 자 중 장학금 지급이 필요하다고 인정된 자"][2]
    assert squash_spaced("공 로 장학금") == "공로 장학금" and squash_spaced("지급액 및 기간") == "지급액 및 기간"


def test_fake_embedder_deterministic_and_normalized():
    e = FakeEmbedder()
    a, b = e.embed_queries(["경복궁 의례"])[0], e.embed_queries(["경복궁 의례"])[0]
    assert (a == b).all() and abs(float((a * a).sum()) - 1) < 1e-5


def test_ari_baseline_port_basic():
    assert ari_baseline.tokenize("Gyeongbokgung, 궁궐/역사") == ["gyeongbokgung", "궁궐", "역사"]
    assert ari_baseline.score("궁궐", "조선 궁궐 역사") == 4
    assert ari_baseline.score("궁궐", "궁궐 역사") == 3
    assert ari_baseline.score("궁궐", "조선궁궐역사") == 2


def test_router_rules():
    from ragcore.registry import build_adapters

    ads = build_adapters()
    lo, ma = ads["lolypoly"], ads["maru"]
    now = datetime(2026, 11, 10, 12, tzinfo=SEOUL)
    assert lo.plan("오늘 메뉴 뭐야?", "ko", {}, now)[0].kind == "clarify"
    p = lo.plan("오늘 점심 뭐야?", "ko", {}, now)[0]
    assert (p.kind, p.params) == ("structured", {"date": "2026-11-10", "meal_type": "lunch"})
    parts = lo.plan("오늘 점심 메뉴랑 학과수석 입학자 장학금 혜택 알려줘", "ko", {}, now)
    assert [x.kind for x in parts] == ["structured", "document"]
    ctx = ma.validate_context({"course_id": "palace-history-course", "ranked_route_ids": ["bogus", "palace-history-course"],
                               "project": "lolypoly"})
    assert ctx == {"course_id": "palace-history-course", "ranked_route_ids": ["palace-history-course"], "ranked_place_ids": []}
    part = ma.plan("이 코스에서 궁궐 의식을 볼 수 있었던 곳은?", "ko", ctx, now)[0]
    assert part.keep_order == ["course:palace-history-course", "place:national-palace-museum", "place:gyeongbokgung-palace",
                               "place:national-folk-museum"]
    assert ma.plan("이 코스에서 궁궐 의식을 볼 수 있었던 곳은?", "ko", {}, now)[0].kind == "clarify"


def test_claim_that_echoes_question_is_dropped():
    evs = [_ev("E1", "비고: 직전학기 성적 3.0이상 신입생은 2학기부터 적용")]
    q = "성적우수장학금은 신입생도 1학기에 받을 수 있어?"
    v = verify([{"text": "성적우수장학금은 신입생도 1학기에 받을 수 있어?", "citations": [{"id": "E1", "quote": "신입생은 2학기부터 적용"}]},
                {"text": "신입생은 2학기부터 적용돼.", "citations": [{"id": "E1", "quote": "신입생은 2학기부터 적용"}]}], evs, question=q)
    assert [c[0] for c in v.claims] == ["신입생은 2학기부터 적용돼."]
    assert any(d["reason"] == "echoes_question" for d in v.dropped)


def test_real_royal_notice_replaces_synthetic_only_after_review(tmp_path):
    import json
    import shutil

    from adapters.maru.adapter import MaruAdapter

    d = tmp_path / "maru"
    shutil.copytree("data/maru", d)
    shutil.rmtree(d / "royal_notices", ignore_errors=True)  # 저장소의 실제 공지와 분리해 검토 전 상태를 재현
    (d / "royal_notices").mkdir()
    rec = {"source_id": "royal:1", "title": "실제 공지", "body": "개방 기간 2026. 9. 1. ~ 2026. 10. 31.", "url": "https://example.invalid/n",
           "published_at": "2026-08-30", "valid_from": "2026-09-01", "valid_to": "2026-10-31",
           "replaces_synthetic": "synthetic:royal-gbg-special-opening", "needs_review": True, "checked_at": "2026-11-18T00:00:00+00:00"}
    (d / "royal_notices" / "1.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    ids = {x.source_id: x for x in MaruAdapter(d).load().documents}
    assert "royal:1" not in ids and "synthetic:royal-gbg-special-opening" in ids   # 검토 전: 적재 안 함
    rec["needs_review"] = False
    (d / "royal_notices" / "1.json").write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    ids = {x.source_id: x for x in MaruAdapter(d).load().documents}
    assert ids["royal:1"].source_type == "public_original" and "synthetic:royal-gbg-special-opening" not in ids


def test_quote_normalization_is_punctuation_only():
    src = "전통시장 미식 코스: 서울 사람들의 일상 속 전통을 체험하는 코스입니다."
    assert quote_in_source("서울 사람들의 일상 속 전통을 체험하는 코스입니다。", src)      # 전각 마침표
    assert quote_in_source("체험하는 코스입니다", src)                                     # 끝 문장부호 생략
    assert not quote_in_source("서울 시민의 일상 속 전통을 체험하는 코스입니다.", src)       # 내용이 다르면 거부
    ev = _ev("E1", src)
    ev.locator = "전통시장 미식 코스 > 문단 1"
    v = verify([{"text": "시장 코스", "citations": [{"id": "E1", "quote": "'전통시장 미식 코스 > 문단 1': 체험하는 코스입니다"}]}], [ev])
    assert len(v.claims) == 1 and v.quote_misses == 0



def test_negative_claim_kept_for_restriction_notice_in_period():
    """출입 제한 공지 기간 안에 '올라갈 수 없다'는 정답이다. 공지를 '개방'으로 가정해 부정문을 버리면 안 된다."""
    from datetime import date

    from ragcore.engine import Engine

    assert not hasattr(Engine, "_drop_period_contradictions")  # 극성 가정 규칙 제거(v0.2.2)
    ev = _ev("E1", "2026년 9월 2일(수)부터 2026년 10월 31일(토)까지 근정전 월대 출입을 제한합니다.")
    ev.valid_from, ev.valid_to = date(2026, 9, 2), date(2026, 10, 31)
    v = verify([{"text": "지금은 근정전 월대에 올라갈 수 없어요.", "citations": [{"id": "E1", "quote": "근정전 월대 출입을 제한합니다"}]}], [ev])
    assert [t for t, _ in v.claims] == ["지금은 근정전 월대에 올라갈 수 없어요."]


def test_korean_and_iso_dates_match_in_value_check():
    ev = _ev("E1", "2026년 9월 2일(수)부터 2026년 10월 31일(토)까지 근정전 월대 출입을 제한합니다.")
    ok = verify([{"text": "2026-10-31까지 올라갈 수 없어요.", "citations": [{"id": "E1", "quote": "근정전 월대 출입을 제한합니다"}]}], [ev])
    bad = verify([{"text": "2026-11-30까지 올라갈 수 없어요.", "citations": [{"id": "E1", "quote": "근정전 월대 출입을 제한합니다"}]}], [ev])
    assert len(ok.claims) == 1 and len(bad.claims) == 0 and bad.value_mismatches == 1


def test_royal_notice_extract_uses_board_detail_classes():
    import importlib.util

    spec = importlib.util.spec_from_file_location("fetch_royal", "scripts/fetch_royal_notice.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    x = mod.extract(open("tests/fixtures/royal_notice_structure_mock.html", encoding="utf-8").read())
    assert x["method"] == "board_detail" and x["title"] == "시험용 공지 제목"
    assert x["published_at"] == "2026-08-30"
    assert "통합검색" not in x["body"] and "관람시간" not in x["body"] and "개인정보" not in x["body"]  # 메뉴·하단 제외
    assert "안쪽 문단도 포함" in x["body"] and "시험용 문장 석조물의손상이우려되어" in x["body"]  # 중첩, 글자 공백만 정리
    assert [d["date"] for d in x["date_candidates"]] == ["2026-09-02", "2026-10-31"]
