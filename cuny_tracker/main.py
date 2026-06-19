from __future__ import annotations

import logging
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.events import EVENT_JOB_ERROR
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, field_validator

from . import db
from .config import get_settings
from .constants import INSTITUTIONS, SESSIONS, TERMS
from .emailer import send_confirmation
from .models import (
    CourseAvailabilities,
    CourseDetails,
    CourseParams,
    ParamError,
)
from .processor import ParseError, process
from .scheduler import poll_once
from .scraper import ScrapeError, Scraper

log = logging.getLogger("cuny_tracker")

_BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(_BASE_DIR / "templates"))

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    _configure_logging(settings.log_level)
    log.info("Starting CUNY Tracker (poll every %d min).", settings.poll_interval_minutes)

    app.state.scraper = Scraper(timeout_seconds=settings.http_timeout_seconds)

    if settings.db_configured:
        try:
            await db.init_db()
        except Exception as exc:
            log.error("Could not initialize database (continuing): %s", exc)
    else:
        log.warning("DATABASE_URL not set — subscriptions are disabled until it is.")

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_listener(
        lambda e: log.error("Scheduled job error: %s", e.exception), EVENT_JOB_ERROR
    )
    scheduler.add_job(
        poll_once,
        trigger="interval",
        minutes=settings.poll_interval_minutes,
        args=[app.state.scraper, settings.base_url],
        id="poll",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=120,
        next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
    )
    scheduler.start()
    app.state.scheduler = scheduler

    try:
        yield
    finally:
        log.info("Shutting down.")
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass
        await app.state.scraper.close()


app = FastAPI(title="CUNY Tracker", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(_BASE_DIR / "static")), name="static")


def _status_dict(params: CourseParams, details: CourseDetails, avail: CourseAvailabilities) -> dict:
    return {
        "class_number": params.class_number,
        "institution": params.institution,
        "term": params.term,
        "year": params.year,
        "session": params.session,
        "course_name": details.course_name,
        "course_title": details.course_title,
        "course_number": details.course_number,
        "instructor": details.instructor,
        "days_and_times": details.days_and_times,
        "room": details.room,
        "meeting_dates": details.meeting_dates,
        "status": avail.status,
        "course_capacity": avail.course_capacity,
        "waitlist_capacity": avail.waitlist_capacity,
        "currently_enrolled": avail.currently_enrolled,
        "currently_waitlisted": avail.currently_waitlisted,
        "available_seats": avail.available_seats,
    }


async def _live_lookup(scraper: Scraper, params: CourseParams) -> tuple[CourseDetails, CourseAvailabilities]:
    soup = await scraper.fetch(params)
    return process(soup)


def get_default_term_and_year() -> tuple[str, int]:
    # Nov-Jan/Aug-Oct -> upcoming Spring, Feb-Jul -> upcoming Fall
    now = datetime.now()
    m = now.month
    if m >= 11 or m == 1:
        return "Spring Term", now.year + 1
    if 2 <= m <= 7:
        return "Fall Term", now.year
    return "Spring Term", now.year + 1


class SubscribeRequest(BaseModel):
    class_number: str
    institution: str
    term: str
    year: int
    session: str = "Regular Academic Session"
    email: str

    @field_validator("class_number")
    @classmethod
    def _digits(cls, v: str) -> str:
        v = v.strip()
        if not v.isdigit():
            raise ValueError("Class number must be numeric.")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError("That doesn't look like a valid email address.")
        return v


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    default_term, default_year = get_default_term_and_year()
    current_year = datetime.now().year
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "institutions": INSTITUTIONS,
            "terms": TERMS,
            "sessions": SESSIONS,
            "default_year": default_year,
            "default_term": default_term,
            "year_options": [current_year, current_year + 1],
        },
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status(
    request: Request,
    class_number: str = Query(...),
    institution: str = Query(...),
    term: str = Query(...),
    year: int = Query(...),
    session: str = Query("Regular Academic Session"),
):
    try:
        params = CourseParams(class_number, term, year, session, institution)
    except ParamError as exc:
        return JSONResponse({"ok": False, "found": False, "error": str(exc)}, status_code=400)

    scraper: Scraper = request.app.state.scraper
    try:
        details, avail = await _live_lookup(scraper, params)
    except ParseError:
        return {
            "ok": True,
            "found": False,
            "error": "No class found for those details. Double-check the class number, "
            "institution, term, and session.",
        }
    except ScrapeError as exc:
        log.warning("Status lookup scrape failed: %s", exc)
        return JSONResponse(
            {"ok": False, "found": False, "error": "Couldn't reach CUNY Global Search. Try again in a moment."},
            status_code=502,
        )

    if details.course_number != params.class_number:
        return {
            "ok": True,
            "found": False,
            "error": "No class found for those details. Double-check the class number, "
            "institution, term, and session.",
        }

    return {"ok": True, "found": True, **_status_dict(params, details, avail)}


@app.post("/subscribe")
async def subscribe(request: Request, payload: SubscribeRequest):
    settings = get_settings()
    if not settings.db_configured:
        return JSONResponse(
            {"ok": False, "error": "Subscriptions are temporarily unavailable. Try again later."},
            status_code=503,
        )

    try:
        params = CourseParams(
            payload.class_number, payload.term, payload.year, payload.session, payload.institution
        )
    except ParamError as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    scraper: Scraper = request.app.state.scraper
    try:
        details, avail = await _live_lookup(scraper, params)
    except ParseError:
        return JSONResponse(
            {"ok": False, "error": "No class found for those details, so there's nothing to track. "
             "Double-check the class number, institution, term, and session."},
            status_code=404,
        )
    except ScrapeError:
        return JSONResponse(
            {"ok": False, "error": "Couldn't reach CUNY Global Search to verify that class. Try again shortly."},
            status_code=502,
        )

    if details.course_number != params.class_number:
        return JSONResponse(
            {"ok": False, "error": "No class found for those details, so there's nothing to track."},
            status_code=404,
        )

    token = secrets.token_urlsafe(32)
    try:
        async with db.get_conn() as conn:
            course_id = await db.ensure_course(conn, params, details, avail)
            created = await db.create_subscription(
                conn, course_id, payload.email, token, avail.status
            )
            course_row = _status_dict(params, details, avail)
    except Exception as exc:
        log.error("Subscribe DB error: %s", exc)
        return JSONResponse(
            {"ok": False, "error": "Something went wrong saving your subscription. Try again."},
            status_code=500,
        )

    full_name = f"{details.course_name} {details.course_title}".strip()

    if not created:
        return {
            "ok": True,
            "already": True,
            "message": f"You're already tracking {full_name} (#{params.class_number}). We'll email you when a seat opens.",
            "status": avail.status,
        }

    unsubscribe_url = f"{settings.base_url}/unsubscribe?token={token}"
    emailed = await send_confirmation(course_row, payload.email, unsubscribe_url)
    message = (
        f"You're now tracking {full_name} (#{params.class_number}). "
        + ("Check your inbox for a confirmation email." if emailed
           else "We'll email you when a seat opens. (A confirmation email couldn't be sent — "
                "check that the address is correct.)")
    )
    return {"ok": True, "already": False, "message": message, "status": avail.status, "emailed": emailed}


async def _do_unsubscribe(token: str) -> bool:
    if not token:
        return False
    try:
        async with db.get_conn() as conn:
            row = await db.delete_subscription_by_token(conn, token)
        return row is not None
    except Exception as exc:
        log.error("Unsubscribe error: %s", exc)
        return False


@app.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_page(request: Request, token: str = Query("")):
    removed = await _do_unsubscribe(token)
    return templates.TemplateResponse(
        request, "unsubscribe.html", {"removed": removed}, status_code=200 if removed else 404
    )


@app.post("/unsubscribe")
async def unsubscribe_oneclick(token: str = Query("")):
    removed = await _do_unsubscribe(token)
    return {"ok": removed}
