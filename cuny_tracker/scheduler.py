from __future__ import annotations

import logging

from . import db
from .emailer import send_open_notification
from .models import CourseParams, ParamError, opened_up
from .processor import ParseError, process
from .scraper import ScrapeError, Scraper

log = logging.getLogger("cuny_tracker.scheduler")


def _params_from_row(row: dict) -> CourseParams:
    return CourseParams(
        class_number=row["class_number"],
        term=row["term"],
        year=row["year"],
        session=row["session"],
        institution=row["institution"],
    )


async def _process_course(conn, scraper: Scraper, base_url: str, course: dict) -> None:
    course_id = course["id"]
    label = f"#{course['class_number']} @ {course['institution']}"

    try:
        params = _params_from_row(course)
    except ParamError as exc:
        log.error("Skipping course %s: bad stored params (%s).", label, exc)
        return

    try:
        soup = await scraper.fetch(params)
        details, availability = process(soup)
    except (ScrapeError, ParseError) as exc:
        log.warning("Could not refresh %s: %s", label, exc)
        try:
            await db.touch_course(conn, course_id)
        except Exception:
            pass
        return

    new_status = availability.status

    try:
        await db.update_course_cache(conn, course_id, details, availability)
    except Exception as exc:
        log.error("Failed to update cache for %s: %s", label, exc)
        return

    course_view = {**course}
    course_view.update(
        course_name=details.course_name,
        course_title=details.course_title,
        instructor=details.instructor,
        days_and_times=details.days_and_times,
        room=details.room,
        meeting_dates=details.meeting_dates,
        status=new_status,
        available_seats=availability.available_seats,
    )

    try:
        subscribers = await db.fetch_subscriptions_for_course(conn, course_id)
    except Exception as exc:
        log.error("Failed to load subscribers for %s: %s", label, exc)
        return

    for sub in subscribers:
        old_status = sub["last_status"]
        if opened_up(old_status, new_status):
            unsubscribe_url = f"{base_url}/unsubscribe?token={sub['unsubscribe_token']}"
            sent = await send_open_notification(course_view, sub["email"], unsubscribe_url)
            if sent:
                await db.update_subscription(conn, sub["id"], new_status, notified=True)
                log.info("Notified %s that %s opened.", sub["email"], label)
            else:
                # skip update to retry on next cycle
                log.warning("Notification to %s for %s failed; will retry.", sub["email"], label)
        elif old_status != new_status:
            await db.update_subscription(conn, sub["id"], new_status)


async def poll_once(scraper: Scraper, base_url: str) -> None:
    try:
        async with db.get_conn() as conn:
            courses = await db.fetch_pollable_courses(conn)
            if not courses:
                log.info("No tracked classes; nothing to poll.")
                return
            log.info("Polling %d tracked class(es).", len(courses))
            for course in courses:
                try:
                    await _process_course(conn, scraper, base_url, course)
                except Exception as exc:
                    log.exception("Unexpected error polling course id=%s: %s", course.get("id"), exc)
    except db.DBNotConfigured:
        log.warning("DATABASE_URL not set; poll skipped.")
    except Exception as exc:
        log.exception("Poll cycle failed: %s", exc)
