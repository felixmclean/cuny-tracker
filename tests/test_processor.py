"""Parser regression tests against a real captured Global Search detail page.

Fixture is class 39314 (MTH 3020, Baruch, Fall 2026), captured 2026-06-28.
Saved offline because class numbers are term-scoped and stop resolving after rollover.
"""
from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup

from cuny_tracker.processor import _expand_days, process

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES / name).read_text(), "lxml")


def test_mth3020_detail_page_parses_correctly():
    details, avail = process(_load("mth3020_detail.html"))

    assert details.course_number == "39314"
    assert details.course_name == "MTH 3020"
    assert details.course_title == "Calculus III"  # "KTRA" section code stripped
    assert details.instructor == "Guy Moshkovitz"
    assert details.days_and_times == "Tuesday/Thursday 2:55PM-4:35PM"
    assert details.room == "B - Vert 4-216"
    assert details.meeting_dates == "08/28/2026-12/21/2026"

    assert avail.status == "Open"
    assert avail.course_capacity == "30"
    assert avail.waitlist_capacity == "0"
    assert avail.currently_enrolled == "15"
    assert avail.currently_waitlisted == "0"
    assert avail.available_seats == "15"


def test_expand_days_leaves_tba_alone():
    # survives only because len 3 fails the even-length check, not by design
    assert _expand_days("TBA") == "TBA"


def test_expand_days_multi_meeting_cell_is_garbled():
    # Known risk pinned as a test: results pages join meeting patterns with <br> and no
    # whitespace, so get_text concatenates them and _expand_days fixes only the leading
    # token. Unconfirmed whether detail pages do this too. Replace with a real fixture if found.
    soup = BeautifulSoup(
        '<td data-label="Days And Times">'
        "Fr 12:50PM - 2:05PM<br>Fr 10:45AM - 12:00PM<br>MoWe 12:50PM - 2:05PM"
        "</td>",
        "lxml",
    )
    raw = soup.find("td").get_text(strip=True)
    assert raw == "Fr 12:50PM - 2:05PMFr 10:45AM - 12:00PMMoWe 12:50PM - 2:05PM"
    assert _expand_days(raw) == "Friday 12:50PM - 2:05PMFr 10:45AM - 12:00PMMoWe 12:50PM - 2:05PM"
