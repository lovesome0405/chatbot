"""상대 날짜 해석. 기준 시각은 항상 Asia/Seoul로 바꾼 뒤 계산한다."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

SEOUL = ZoneInfo("Asia/Seoul")
KO_WEEKDAYS = "월화수목금토일"
EN_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EN_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def seoul_now(ref: datetime | None = None) -> datetime:
    ref = ref or datetime.now(tz=SEOUL)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=SEOUL)
    return ref.astimezone(SEOUL)


def fmt_day(d: date, lang: str = "ko") -> str:
    if lang == "ko":
        return f"{d.isoformat()}({KO_WEEKDAYS[d.weekday()]})"
    return f"{d.isoformat()} ({EN_WEEKDAYS[d.weekday()].title()})"


def resolve_date(text: str, now: datetime) -> date | None:
    """질문에서 단일 날짜를 찾는다. 없으면 None."""
    t = text.lower()
    today = seoul_now(now).date()
    if m := re.search(r"(20\d{2})[-./](\d{1,2})[-./](\d{1,2})", t):
        return _safe(int(m[1]), int(m[2]), int(m[3]))
    if m := re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", t):
        return _safe(today.year, int(m[1]), int(m[2]))
    if m := re.search(r"\b(\d{1,2})/(\d{1,2})\b", t):
        return _safe(today.year, int(m[1]), int(m[2]))
    if m := re.search(r"\b(" + "|".join(EN_MONTHS) + r")[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", t):
        return _safe(today.year, EN_MONTHS.index(m[1]) + 1, int(m[2]))
    for words, delta in ((("모레", "day after tomorrow"), 2), (("내일", "tomorrow"), 1), (("어제", "yesterday"), -1),
                         (("오늘", "today", "tonight"), 0)):
        if any(w in t for w in words):
            return today + timedelta(days=delta)
    week_shift = 7 if re.search(r"다음\s*주|next week", t) else -7 if re.search(r"지난\s*주|last week", t) else 0
    if m := re.search(r"([월화수목금토일])요일", t):
        return _week_day(today, KO_WEEKDAYS.index(m[1]), week_shift)
    for i, name in enumerate(EN_WEEKDAYS):
        if re.search(rf"\b{name}\b", t):
            return _week_day(today, i, week_shift)
    return None


def resolve_range(text: str, now: datetime) -> tuple[date, date] | None:
    t = text.lower()
    today = seoul_now(now).date()
    monday = today - timedelta(days=today.weekday())
    if re.search(r"이번\s*주|this week", t):
        return monday, monday + timedelta(days=6)
    if re.search(r"다음\s*주|next week", t):
        return monday + timedelta(days=7), monday + timedelta(days=13)
    if re.search(r"이번\s*달|this month", t):
        return _month(today.year, today.month)
    if m := re.search(r"(?<!\d)(\d{1,2})\s*월(?!\s*\d{1,2}\s*일)", t):
        month = int(m[1])
        if 1 <= month <= 12:
            year = today.year if month >= today.month - 6 else today.year + 1
            return _month(year, month)
    return None


def _month(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    end = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
    return start, end


def _week_day(today: date, weekday: int, shift: int) -> date:
    monday = today - timedelta(days=today.weekday())
    return monday + timedelta(days=weekday + shift)


def _safe(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None
