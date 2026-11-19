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


def test_royal_notice_extract_real_page_regression():
    """회귀 테스트: 주상 PC가 2026-11-18 저장한 실제 공지 상세 원본(공개 페이지)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("fetch_royal", "scripts/fetch_royal_notice.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    x = mod.extract(open("tests/fixtures/royal_notice_20260830151817711582.raw.html", encoding="utf-8").read())
    assert x["method"] == "board_detail"
    assert x["title"] == "경복궁 근정전 월대 출입 제한 안내(2026.9.2.(수)~10.31.(토))"
    assert x["published_at"] == "2026-08-30"
    assert [d["date"] for d in x["date_candidates"]] == ["2026-09-02", "2026-10-31"]
    assert "근정전 월대 출입을 제한합니다" in x["body"] and "보존 관리에 협조하여 주시기 바랍니다" in x["body"]
    assert not any(w in x["body"] for w in ("통합검색", "관람시간", "공지사항", "보도자료"))  # 메뉴가 섞이지 않음


def test_course_order_added_from_data_when_course_cited():
    from datetime import datetime

    from ragcore.adapter import Claim
    from ragcore.models import Citation
    from ragcore.registry import build_adapters
    from ragcore.timeutil import SEOUL

    ma = build_adapters()["maru"]
    part = ma.plan("북촌 한옥마을이랑 같이 둘러볼 궁궐 코스 있어?", "ko", {}, datetime(2026, 11, 17, tzinfo=SEOUL))[0]
    cit = Citation("course:bukchon-hanok-culture-course", "북촌 한옥 문화 코스", None, "코스 순서: 북촌한옥마을 → 창덕궁 → 운현궁",
                   "북촌 한옥 문화 코스 > 문단 2", None, "repository_data")
    extra = ma.extra_claims(part, [Claim("네, 북촌 한옥마을과 함께 둘러볼 궁궐 코스가 있어요.", [cit])], "ko")
    assert len(extra) == 1 and "북촌한옥마을 → 창덕궁 → 운현궁" in extra[0].text
    assert extra[0].citations[0].quote == "코스 순서: 북촌한옥마을 → 창덕궁 → 운현궁"   # 적재된 문단 원문과 같음
    full = ma.extra_claims(part, [Claim("북촌한옥마을, 창덕궁, 운현궁을 둘러봐요.", [cit])], "ko")
    assert full == []                                                                   # 이미 다 말했으면 붙이지 않음


def test_affirmative_echo_kept_and_enriched_with_quote():
    """질문을 긍정문으로 되풀이한 주장은 버리지 않고, 검증된 근거 발췌를 붙여 설명을 보강한다."""
    from ragcore.citations import enrich_echo

    ev = _ev("E1", "전통 공예, 찻집, 갤러리, 기념품 가게가 모여 있는 서울 대표 전통거리입니다.", title="인사동 (Insadong)")
    q = "인사동에서 전통공예를 볼 수 있어?"
    v = verify([{"text": "인사동에서 전통공예를 볼 수 있어요.",
                 "citations": [{"id": "E1", "quote": "전통 공예, 찻집, 갤러리, 기념품 가게가 모여 있는 서울 대표 전통거리"}]}], [ev], question=q)
    assert len(v.claims) == 1 and v.echo_claims == {0}
    text = enrich_echo(v.claims[0][0], v.claims[0][1][0][1], "ko")
    assert text.startswith("인사동에서 전통공예를 볼 수 있어요.") and "찻집, 갤러리" in text


def test_echo_without_support_for_question_words_is_dropped():
    """v0.3.0 평가 회귀: 질문 되풀이에 무관한 발췌를 붙이면 근거 없는 답이 근거 있어 보인다.
    되풀이 주장 속 질문 단어(축제·주말, 1학기)가 인용 근거에 없으면 버린다."""
    ev = _ev("E1", "복원 한옥과 전통 정원을 한 번에 볼 수 있는 도심 속 전통문화 공간입니다.", title="남산골한옥마을 (Namsangol Hanok Village)")
    v = verify([{"text": "남산골한옥마을 이번 주말에 축제가 열립니다.",
                 "citations": [{"id": "E1", "quote": "복원 한옥과 전통 정원을 한 번에 볼 수 있는 도심 속 전통문화 공간입니다"}]}],
               [ev], question="남산골한옥마을 이번 주말에 축제해?")
    assert v.claims == [] and v.dropped[0]["reason"] == "echo_unsupported"

    row = _ev("E1", "구분: 교내 | 종류: 성적우수 장학금 | 수혜자격: 직전학기 학과별 성적우수자 학급당 1명 | "
                    "비고: 직전학기 성적 3.0이상 신입생은 2학기부터 적용")
    v = verify([{"text": "성적우수장학금은 신입생도 1학기에 받을 수 있습니다.",
                 "citations": [{"id": "E1", "quote": "종류: 성적우수 장학금"}]}], [row], question="성적우수장학금은 신입생도 1학기에 받을 수 있어?")
    assert v.claims == [] and v.dropped[0]["reason"] == "echo_unsupported"


def test_supported_echo_kept_and_pure_copy_dropped():
    row = _ev("E1", "구분: 교외 | 종류: 부사관 장학금 | 수혜자격: 부사관 합격자")
    v = verify([{"text": "부사관 합격하면 부사관 장학금을 받을 수 있습니다.",
                 "citations": [{"id": "E1", "quote": "종류: 부사관 장학금"}]}], [row], question="부사관 합격하면 장학금 받을 수 있어?")
    assert len(v.claims) == 1 and v.echo_claims == {0}

    ev = _ev("E1", "조선 수도 한양을 둘러싸던 성곽으로 서울의 지형과 역사를 함께 보여줍니다.", title="한양도성")
    v = verify([{"text": "도성 성곽을 따라 걷고 싶어", "citations": [{"id": "E1", "quote": "조선 수도 한양을 둘러싸던 성곽"}]}],
               [ev], question="도성 성곽을 따라 걷고 싶어")
    assert v.claims == [] and v.dropped[0]["reason"] == "echoes_question"


def test_non_answer_claims_are_dropped():
    """'알려지지 않았어요'·'not mentioned' 같은 문장은 답이 아니다: 버리고 보류로 처리한다."""
    ev = _ev("E1", "학사일정 성적열람 및 이의신청 | 과정: P-TECH | 기간: 2026-01-15 ~ 2026-01-16")
    for text in ("기숙사 신청 기간은 알려지지 않았어요.", "그 일정은 알려주지 못해요.", "자료에 언급되지 않았어요.",
                 "The evidence does not mention a dormitory.", "No information is available about that."):
        v = verify([{"text": text, "citations": [{"id": "E1", "quote": "성적열람 및 이의신청"}]}], [ev])
        assert v.claims == [] and v.dropped[-1]["reason"] == "non_answer", text
    ok = verify([{"text": "성적열람 및 이의신청은 2026-01-15부터예요.", "citations": [{"id": "E1", "quote": "성적열람 및 이의신청"}]}], [ev])
    assert len(ok.claims) == 1


def test_prompt_is_language_specific():
    from ragcore.generation import build_messages

    en = build_messages("Can I go?", "en", [], "2026-11-18", "")[0]["content"]
    ko = build_messages("가도 돼?", "ko", [], "2026-11-18", "")[0]["content"]
    assert "해요" not in en and "예요" not in en and "Answer in English" in en
    assert "해요체" in ko


def test_topic_particle_follows_final_consonant():
    from ragcore.textnorm import topic
    assert topic("근정전 월대") == "근정전 월대는" and topic("근정전") == "근정전은" and topic("Jongmyo") == "Jongmyo은(는)"


# ── v0.4.0: 영어 주장 검사 ─────────────────
def test_wrong_romanized_district_dropped():
    """M14 회귀: 근거는 '종로구'인데 영어 주장이 'Jungmu-gu'라고 쓰면 버린다. 맞는 표기는 통과."""
    from adapters.maru.adapter import MaruAdapter

    ad = MaruAdapter()
    evs = [_ev("E1", "종묘 (Jongmyo Shrine) — 왕실 유적 / 종로구", "종묘 (Jongmyo Shrine)")]
    bad = {"text": "Jongmyo Shrine is a royal heritage site in Jungmu-gu district of Seoul.",
           "citations": [{"id": "E1", "quote": "종묘 (Jongmyo Shrine) — 왕실 유적 / 종로구"}]}
    good = {"text": "Jongmyo Shrine is a royal heritage site in Jongno-gu.",
            "citations": [{"id": "E1", "quote": "종묘 (Jongmyo Shrine) — 왕실 유적 / 종로구"}]}
    v = verify([bad, good], evs, question="Tell me about Jongmyo Shrine", aliases=ad.aliases,
               glossary=ad.term_glossary, term_pattern=ad.term_pattern)
    assert [t for t, _ in v.claims] == [good["text"]]
    assert v.dropped[0]["reason"] == "term_not_in_cited_source"


def test_english_echo_needs_translated_support():
    """N02·N19 회귀: 질문을 되풀이한 영어 답은 질문 단어를 별칭으로 한국어로 바꿔 근거에서 찾아야 남는다."""
    from adapters.lolypoly.adapter import LolypolyAdapter
    from adapters.maru.adapter import MaruAdapter

    maru, loly = MaruAdapter(), LolypolyAdapter()
    gbg = _ev("E1", "경복궁 (Gyeongbokgung Palace) — 궁궐 / 종로구")
    ghg = _ev("E2", "조선 후기 궁궐 중 하나로 비교적 조용하게 궁궐 분위기를 느낄 수 있습니다.")
    q = "I want a quiet palace without big crowds"
    v = verify([{"text": "Yes, Gyeongbokgung Palace is a quiet palace without big crowds.",
                 "citations": [{"id": "E1", "quote": "경복궁 (Gyeongbokgung Palace) — 궁궐 / 종로구"}]},
                {"text": "Gyeonghuigung is a quiet palace without big crowds.",
                 "citations": [{"id": "E2", "quote": "비교적 조용하게 궁궐 분위기를 느낄 수 있습니다"}]}],
               [gbg, ghg], question=q, aliases=maru.aliases)
    assert [t for t, _ in v.claims] == ["Gyeonghuigung is a quiet palace without big crowds."]
    row1 = _ev("E1", "[장학제도 표] 구분: 교내 | 종류: 이사장 장학금 | 수혜자격: 입학성적 전체 수석자 1명")
    v = verify([{"text": "No, there is no scholarship for students who work for the college.",
                 "citations": [{"id": "E1", "quote": "[장학제도 표] 구분: 교내 | 종류: 이사장 장학금 | 수혜자격: 입학성적 전체 수석자 1명"}]}],
               [row1], question="Is there a scholarship for students who work for the college?", aliases=loly.aliases)
    assert not v.claims and v.dropped[0]["reason"] == "echo_unsupported"


def test_client_ip_ignores_forwarded_header_by_default():
    from types import SimpleNamespace

    from ragcore.api import client_ip

    req = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"), headers={"x-forwarded-for": "1.2.3.4, 9.9.9.9"})
    assert client_ip(req, 0) == "10.0.0.5"          # 헤더를 믿지 않음(꾸민 헤더로 제한 회피 불가)
    assert client_ip(req, 1) == "9.9.9.9"           # 믿는 프록시 1단: 그 프록시가 붙인 마지막 값
    assert client_ip(req, 3) == "10.0.0.5"          # 체인이 짧으면 직접 연결 주소


def test_place_hint_not_counted_as_question_echo():
    """'What is this place?'에 앱이 붙인 장소 힌트 때문에 맞는 답이 '질문 베끼기'로 버려지지 않는다(H07)."""
    evs = [_ev("E1", "창덕궁 (Changdeokgung Palace) — 궁궐 / 종로구")]
    claim = {"text": "This place is Changdeokgung Palace (창덕궁).",
             "citations": [{"id": "E1", "quote": "창덕궁 (Changdeokgung Palace) — 궁궐 / 종로구"}]}
    hinted = "What is this place? (here = Changdeokgung Palace / 창덕궁)"
    assert not verify([claim], evs, question=hinted).claims            # 힌트까지 질문으로 보면 버려짐(이전 동작)
    assert verify([claim], evs, question="What is this place?").claims  # 원래 질문과 비교하면 남음
