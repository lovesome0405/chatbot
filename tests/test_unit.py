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
