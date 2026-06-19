from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import psycopg
from psycopg.rows import dict_row

from .config import get_settings
from .models import CourseAvailabilities, CourseDetails, CourseParams

log = logging.getLogger("cuny_tracker.db")


class DBNotConfigured(RuntimeError):
    pass 


SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id                    SERIAL PRIMARY KEY,
    class_number          TEXT NOT NULL,
    institution           TEXT NOT NULL,
    term                  TEXT NOT NULL,
    year                  INTEGER NOT NULL,
    session               TEXT NOT NULL,
    term_code             TEXT NOT NULL,
    course_name           TEXT,
    course_title          TEXT,
    instructor            TEXT,
    days_and_times        TEXT,
    room                  TEXT,
    meeting_dates         TEXT,
    status                TEXT,
    course_capacity       TEXT,
    waitlist_capacity     TEXT,
    currently_enrolled    TEXT,
    currently_waitlisted  TEXT,
    available_seats       TEXT,
    last_checked          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (class_number, institution, term_code, session)
);

ALTER TABLE courses ADD COLUMN IF NOT EXISTS course_title TEXT;

CREATE TABLE IF NOT EXISTS subscriptions (
    id                 SERIAL PRIMARY KEY,
    course_id          INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    email              TEXT NOT NULL,
    unsubscribe_token  TEXT NOT NULL UNIQUE,
    last_status        TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    notified_at        TIMESTAMPTZ,
    UNIQUE (course_id, email)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_course ON subscriptions(course_id);
"""


@asynccontextmanager
async def get_conn() -> AsyncIterator[psycopg.AsyncConnection]:
    settings = get_settings()
    if not settings.database_url:
        raise DBNotConfigured("DATABASE_URL is not set")
    # prepare_threshold=None enables PgBouncer compatibility
    conn = await psycopg.AsyncConnection.connect(
        settings.database_url,
        autocommit=True,
        prepare_threshold=None,
        row_factory=dict_row,
    )
    try:
        yield conn
    finally:
        await conn.close()


async def init_db() -> None:
    async with get_conn() as conn:
        await conn.execute(SCHEMA)
    log.info("Database schema ready.")


async def ensure_course(
    conn: psycopg.AsyncConnection,
    params: CourseParams,
    details: CourseDetails,
    availability: CourseAvailabilities,
) -> int:
    row = await (
        await conn.execute(
            """
            INSERT INTO courses (
                class_number, institution, term, year, session, term_code,
                course_name, course_title, instructor, days_and_times, room, meeting_dates,
                status, course_capacity, waitlist_capacity, currently_enrolled,
                currently_waitlisted, available_seats, last_checked
            ) VALUES (
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, now()
            )
            ON CONFLICT (class_number, institution, term_code, session) DO UPDATE SET
                course_name = EXCLUDED.course_name,
                course_title = EXCLUDED.course_title,
                instructor = EXCLUDED.instructor,
                days_and_times = EXCLUDED.days_and_times,
                room = EXCLUDED.room,
                meeting_dates = EXCLUDED.meeting_dates,
                status = EXCLUDED.status,
                course_capacity = EXCLUDED.course_capacity,
                waitlist_capacity = EXCLUDED.waitlist_capacity,
                currently_enrolled = EXCLUDED.currently_enrolled,
                currently_waitlisted = EXCLUDED.currently_waitlisted,
                available_seats = EXCLUDED.available_seats,
                last_checked = now()
            RETURNING id
            """,
            (
                params.class_number, params.institution, params.term, params.year,
                params.session, params.term_code,
                details.course_name, details.course_title, details.instructor, details.days_and_times,
                details.room, details.meeting_dates,
                availability.status, availability.course_capacity,
                availability.waitlist_capacity, availability.currently_enrolled,
                availability.currently_waitlisted, availability.available_seats,
            ),
        )
    ).fetchone()
    return int(row["id"])


async def create_subscription(
    conn: psycopg.AsyncConnection,
    course_id: int,
    email: str,
    token: str,
    baseline_status: str | None,
) -> bool:
    row = await (
        await conn.execute(
            """
            INSERT INTO subscriptions (course_id, email, unsubscribe_token, last_status)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (course_id, email) DO NOTHING
            RETURNING id
            """,
            (course_id, email, token, baseline_status),
        )
    ).fetchone()
    return row is not None


async def fetch_pollable_courses(conn: psycopg.AsyncConnection) -> list[dict[str, Any]]:
    cur = await conn.execute(
        """
        SELECT * FROM courses c
        WHERE EXISTS (SELECT 1 FROM subscriptions s WHERE s.course_id = c.id)
        ORDER BY c.id
        """
    )
    return await cur.fetchall()


async def fetch_subscriptions_for_course(
    conn: psycopg.AsyncConnection, course_id: int
) -> list[dict[str, Any]]:
    cur = await conn.execute(
        "SELECT id, email, unsubscribe_token, last_status FROM subscriptions WHERE course_id = %s",
        (course_id,),
    )
    return await cur.fetchall()


async def update_course_cache(
    conn: psycopg.AsyncConnection,
    course_id: int,
    details: CourseDetails,
    availability: CourseAvailabilities,
) -> None:
    await conn.execute(
        """
        UPDATE courses SET
            course_name = %s, course_title = %s, instructor = %s, days_and_times = %s, room = %s,
            meeting_dates = %s, status = %s, course_capacity = %s,
            waitlist_capacity = %s, currently_enrolled = %s,
            currently_waitlisted = %s, available_seats = %s, last_checked = now()
        WHERE id = %s
        """,
        (
            details.course_name, details.course_title, details.instructor, details.days_and_times,
            details.room, details.meeting_dates, availability.status,
            availability.course_capacity, availability.waitlist_capacity,
            availability.currently_enrolled, availability.currently_waitlisted,
            availability.available_seats, course_id,
        ),
    )


async def touch_course(conn: psycopg.AsyncConnection, course_id: int) -> None:
    await conn.execute("UPDATE courses SET last_checked = now() WHERE id = %s", (course_id,))


async def update_subscription(
    conn: psycopg.AsyncConnection, sub_id: int, status: str, notified: bool = False
) -> None:
    await conn.execute(
        "UPDATE subscriptions SET last_status = %s, "
        "notified_at = CASE WHEN %s THEN now() ELSE notified_at END WHERE id = %s",
        (status, notified, sub_id),
    )


async def delete_subscription_by_token(conn: psycopg.AsyncConnection, token: str) -> dict | None:
    async with conn.transaction():
        row = await (
            await conn.execute(
                "DELETE FROM subscriptions WHERE unsubscribe_token = %s RETURNING course_id, email",
                (token,),
            )
        ).fetchone()
        if row is None:
            return None
        await conn.execute(
            """
            DELETE FROM courses c
            WHERE c.id = %s
              AND NOT EXISTS (SELECT 1 FROM subscriptions s WHERE s.course_id = c.id)
            """,
            (row["course_id"],),
        )
        return row
