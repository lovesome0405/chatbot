"""v0.6.0 영어 질문용 정형 답 틀. 표·일정의 한국어 값은 그대로 두고(인용 원문도 그대로), 고정 용어집에 있는 값만
영어 설명을 앞에 붙인다. 용어집에 없는 값은 한국어 원문만 보여 준다(번역을 지어내지 않음).

용어집은 공식 장학표(kopo_scholarship_4799.html)와 학사일정 fixture 에 실제로 있는 값만 담았다(2026-11-23).
"""

from __future__ import annotations

import re

SCHOLARSHIP_KIND = {
    "이사장 장학금": "Chairperson's Scholarship",
    "성적우수 장학금": "Academic Excellence Scholarship",
    "보훈 및 북한이탈주민 장학금": "Veterans' Families and North Korean Defectors Scholarship",
    "공로 장학금": "Merit (Service) Scholarship",
    "복지 장학금": "Welfare Scholarship",
    "근로 장학금": "Work-Study Scholarship",
    "국가 장학금": "National Scholarship",
    "부사관 장학금": "Non-commissioned Officer Scholarship",
    "의용소방대 장학금": "Volunteer Fire Brigade Scholarship",
    "장학단체 및 기업체 장학금": "Foundation and Company Scholarship",
}
ELIGIBILITY = {
    "입학성적 전체 수석자 1명": "the one student with the top overall admission score",
    "학과수석 입학자 1명": "the one top-ranked admitted student in each department",
    "직전학기 학과별 성적우수자 학급당 1명": "one top student per class, by previous-semester grades in each department",
    "보훈관계법령에 의한 교육보호 대상자": "students eligible for education support under veterans' laws",
    "북한이탈주민 교육지원 대상자": "North Korean defectors eligible for education support",
    "학생회 간부 또는 학교의 발전에 공헌한 자 중 장학금 지급이 필요하다고 인정된 자":
        "student council officers or students who contributed to the college and are judged to need a scholarship",
    "국가장학금 수혜자": "National Scholarship recipients",
    "대학 운영에 일정기간의 근로를 제공한 자": "students who worked for the college for a set period",
    "한국장학재단에서 장학생으로 승인된 자": "students approved by the Korea Student Aid Foundation",
    "부사관 합격자": "students who passed the non-commissioned officer selection",
    "의용소방대 추천자": "students recommended by the volunteer fire brigade",
    "장학 단체 및 기업체에서 추천한 자": "students recommended by a scholarship foundation or company",
}
AMOUNT_PATTERNS = [
    (re.compile(r"^(\d+)년간 교육비 전액면제$"), lambda m: f"full tuition waiver for {m[1]} year{'s' if m[1] != '1' else ''}"),
    (re.compile(r"^(\d+)개학기 교육비 전액면제$"), lambda m: f"full tuition waiver for {m[1]} semester{'s' if m[1] != '1' else ''}"),
    (re.compile(r"^해당학기 교육비의 반액 지급$"), lambda m: "half of that semester's tuition"),
    (re.compile(r"^해당학기 교육비 내에서 차등 지급$"), lambda m: "a varying amount up to that semester's tuition"),
    (re.compile(r"^해당학기 교육비 내에서 예산범위 내 지급$"), lambda m: "up to that semester's tuition, within the budget"),
    (re.compile(r"^교육비의 액수에 해당관청에서 지급한 장학금의 차액 면제$"),
     lambda m: "waiver of the difference between tuition and the scholarship paid by the government office"),
    (re.compile(r"^별도 규정$"), lambda m: "set by separate rules"),
]
NOTE_PATTERNS = [
    (re.compile(r"^직전학기 성적 (\d\.\d)이상$"), lambda m: f"previous-semester GPA {m[1]} or higher"),
    (re.compile(r"^직전학기 성적 (\d\.\d)이상 신입생은 2학기부터 적용$"),
     lambda m: f"previous-semester GPA {m[1]} or higher; for new students it applies from the 2nd semester"),
    (re.compile(r"^해당관청 성적 기준$"), lambda m: "grade standard of the government office"),
]
EVENT = {
    "기말시험": "final exams", "기말시험(2학년)": "final exams (2nd year)", "중간시험": "midterm exams",
    "1학기 개강": "1st semester starts", "2학기 개강": "2nd semester starts", "2학기 수업 종료": "2nd semester classes end",
    "2학기 종합평가": "2nd semester comprehensive evaluation", "동계방학": "winter vacation",
    "동계방학(1학년)": "winter vacation (1st year)", "동계방학(2학년)": "winter vacation (2nd year)", "하계방학": "summer vacation",
    "수강신청": "course registration", "수강신청 정정": "course registration changes", "성적열람 및 이의신청": "grade viewing and appeals",
    "학위수여식 및 수료식": "graduation and completion ceremony", "신입생 입학식 및 OT": "freshman entrance ceremony and orientation",
    "개교기념일": "college foundation day", "대룡축제": "Daeryong Festival", "휴강": "no classes",
}
COURSE = {"2년제학위과정": "2-year degree program", "전문기술과정": "specialist technical program", "하이테크과정": "high-tech program",
          "공통": "all programs", "P-TECH": "P-TECH"}
MEAL_KIND = {"아침": "breakfast", "점심": "lunch", "저녁": "dinner", "주중": "weekdays", "구분": "type"}


def gloss(value: str, table: dict) -> str:
    """'English (한국어)' 또는 용어집에 없으면 한국어 그대로."""
    v = (value or "").strip()
    en = table.get(v)
    return f"{en} ({v})" if en else v


def gloss_pattern(value: str, patterns) -> str:
    v = (value or "").strip()
    for rx, fn in patterns:
        m = rx.match(v)
        if m:
            return f"{fn(m)} (‘{v}’)"
    return f"‘{v}’" if v else "-"
