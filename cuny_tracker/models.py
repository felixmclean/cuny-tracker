from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
from datetime import datetime

from .constants import COLLEGE_BASE64, DEFAULT_INSTITUTION, SESSION_BASE64

STATUS_OPEN = "Open"


def encode_b64(s: str) -> str:
    return b64encode(s.encode()).decode()


def get_current_term_and_year() -> tuple[int, str]:
    now = datetime.now()
    if now.month <= 5:
        term = "Spring Term"
    elif now.month <= 8:
        term = "Summer Term"
    else:
        term = "Fall Term"
    return now.year, term


def get_global_search_term_value(year: int, term: str) -> int:
    # CUNY internal term code (e.g. Fall 2025 -> 1259)
    term_offsets = {"Spring Term": 2, "Summer Term": 6, "Fall Term": 9}
    return (year - 1900) * 10 + term_offsets[term]


def opened_up(previous: str | None, current: str | None) -> bool:
    if not current or current.strip() != STATUS_OPEN:
        return False
    if previous is None:
        return False
    return previous.strip() != STATUS_OPEN


class ParamError(ValueError):
    pass

class CourseParams:
    def __init__(
        self,
        class_number: int | str,
        term: str | None = None,
        year: int | None = None,
        session: str | None = None,
        institution: str | None = None,
    ) -> None:
        self.class_number = str(class_number).strip()

        current_year, current_term = get_current_term_and_year()
        self.year = int(year) if year else current_year
        self.term = (term or current_term).strip()
        self.session = (session or "Regular Academic Session").strip()
        self.institution = (institution or DEFAULT_INSTITUTION).strip()

        if self.term not in {"Spring Term", "Summer Term", "Fall Term"}:
            raise ParamError(f"Unknown term: {self.term!r}")
        if self.institution not in COLLEGE_BASE64:
            raise ParamError(f"Unknown institution: {self.institution!r}")
        if self.session not in SESSION_BASE64:
            raise ParamError(f"Unknown session: {self.session!r}")
        if not self.class_number.isdigit():
            raise ParamError("Class number must be numeric")

        self.term_code = str(get_global_search_term_value(self.year, self.term))

    def encoded_params(self) -> dict[str, str]:
        return {
            "class_number_searched": encode_b64(self.class_number),
            "session_searched": SESSION_BASE64[self.session],
            "term_searched": encode_b64(self.term_code),
            "inst_searched": COLLEGE_BASE64[self.institution],
        }

    def __repr__(self) -> str:
        return (
            f"CourseParams(class_number={self.class_number!r}, institution="
            f"{self.institution!r}, term={self.term!r}, year={self.year}, "
            f"session={self.session!r})"
        )


@dataclass
class CourseDetails:
    course_number: str
    course_name: str
    course_title: str
    days_and_times: str
    room: str
    instructor: str
    meeting_dates: str


@dataclass
class CourseAvailabilities:
    status: str
    course_capacity: str
    waitlist_capacity: str
    currently_enrolled: str
    currently_waitlisted: str
    available_seats: str
