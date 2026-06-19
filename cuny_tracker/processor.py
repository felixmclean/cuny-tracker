from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from .models import CourseAvailabilities, CourseDetails

# The detail-page shadowbox reads "SUBJECT CATALOG - SECTION Title" (e.g.
# "MTH 3020 - KTRA Calculus III"). CUNY section codes are 3-4 characters of
# uppercase letters and/or digits (KTRA, BMF7, PMR1, PM10, RID, TBA, ...).
# Course titles always begin with a normal mixed-case word, so this never
# matches a real title's first word.
_SECTION_CODE = re.compile(r"^[A-Z0-9]{3,4}$")


class ParseError(ValueError):
    pass

def _safe_find(soup: BeautifulSoup, tag: str, *args: Any, **kwargs: Any) -> Tag | NavigableString:
    result = soup.find(tag, *args, **kwargs)
    if not result:
        raise ParseError(f"Could not find <{tag}> with {kwargs}")
    return result


def _safe_find_next(el: Tag, *args: Any, **kwargs: Any) -> Tag | NavigableString:
    result = el.find_next(*args, **kwargs)
    if not result:
        raise ParseError(f"Could not find next tag from {el} with {kwargs}")
    return result


def _data_label(soup: BeautifulSoup, label: str) -> str:
    td = soup.find("td", attrs={"data-label": label})
    if not td:
        raise ParseError(f"Could not find <td> with data-label {label!r}")
    return td.get_text(strip=True)


_DAY_NAMES = {
    "Mo": "Monday", "Tu": "Tuesday", "We": "Wednesday", "Th": "Thursday",
    "Fr": "Friday", "Sa": "Saturday", "Su": "Sunday",
}


def _expand_days(value: str) -> str:
    parts = value.split(None, 1)
    if not parts:
        return value
    codes = parts[0]
    if len(codes) < 2 or len(codes) % 2 or any(
        codes[i:i + 2] not in _DAY_NAMES for i in range(0, len(codes), 2)
    ):
        return value
    days = "/".join(_DAY_NAMES[codes[i:i + 2]] for i in range(0, len(codes), 2))
    return f"{days} {parts[1]}" if len(parts) > 1 else days


def process(soup: BeautifulSoup) -> tuple[CourseDetails, CourseAvailabilities]:
    div = _safe_find(soup, "div", attrs={"class": "shadowbox"})
    p = div.find("p")
    if not p:
        raise ParseError("Could not find <p> in shadowbox")

    details = p.get_text(strip=True)
    course_name, _, course_title = details.partition(" - ")
    head = course_title.split(None, 1)
    if len(head) == 2 and _SECTION_CODE.match(head[0]):
        course_title = head[1]

    td = _safe_find(soup, "td", string=re.compile("Class Number"))
    course_number = _safe_find_next(td).get_text(strip=True)

    status_img = soup.find("img", title=re.compile("Open|Closed|Wait"))
    if not status_img:
        raise ParseError("Could not find status <img>")
    status_td = status_img.find_parent("td")
    if not status_td:
        raise ParseError("Could not find parent <td> of status <img>")
    status = status_td.get_text(strip=True)

    days_and_times = _expand_days(_data_label(soup, "Days And Times"))
    room = _data_label(soup, "Room")
    instructor = _data_label(soup, "Instructor")
    meeting_dates = _data_label(soup, "Meeting Dates")

    availability_header = soup.find("b", string=re.compile("Class Availability"))
    if not availability_header:
        raise ParseError("Could not find 'Class Availability' header")
    availability_table = availability_header.find_next("table")
    if not availability_table:
        raise ParseError("Could not find availability table")

    spans = availability_table.find_all("span")
    if len(spans) < 5:
        raise ParseError(f"Expected 5 availability spans, found {len(spans)}")
    span_values = [span.get_text(strip=True) for span in spans[:5]]

    course_details = CourseDetails(
        course_number=course_number,
        course_name=course_name,
        course_title=course_title,
        days_and_times=days_and_times,
        room=room,
        instructor=instructor,
        meeting_dates=meeting_dates,
    )
    course_availabilities = CourseAvailabilities(
        status=status,
        course_capacity=span_values[0],
        waitlist_capacity=span_values[1],
        currently_enrolled=span_values[2],
        currently_waitlisted=span_values[3],
        available_seats=span_values[4],
    )
    return course_details, course_availabilities
