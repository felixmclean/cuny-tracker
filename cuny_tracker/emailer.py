from __future__ import annotations

import asyncio
import html
import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from .config import Settings, get_settings

log = logging.getLogger("cuny_tracker.emailer")


def _send_sync(settings: Settings, msg: EmailMessage) -> None:
    if settings.smtp_use_ssl:
        server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30)
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
    with server:
        server.ehlo()
        if settings.smtp_starttls and not settings.smtp_use_ssl:
            server.starttls()
            server.ehlo()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password or "")
        server.send_message(msg)


async def send_email(
    to_email: str, subject: str, text_body: str, html_body: str | None, unsubscribe_url: str
) -> bool:
    settings = get_settings()
    if not settings.email_configured:
        log.warning("Email not configured (SMTP_HOST / SMTP_FROM_EMAIL); skipping send to %s.", to_email)
        return False

    msg = EmailMessage()
    msg["From"] = formataddr((settings.smtp_from_name, settings.smtp_from_email))  # type: ignore[arg-type]
    msg["To"] = to_email
    msg["Subject"] = subject
    # RFC 8058 one-click unsubscribe
    msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        await asyncio.to_thread(_send_sync, settings, msg)
        log.info("Sent '%s' to %s.", subject, to_email)
        return True
    except Exception as exc:
        log.error("Failed to send email to %s: %s", to_email, exc)
        return False


def _course_line(course: dict) -> str:
    name = course.get("course_name") or "your class"
    title = course.get("course_title") or ""
    full_name = f"{name} {title}".strip()
    return f"{full_name} (#{course['class_number']}) at {course['institution']}"


def _render(
    heading: str,
    intro_text: str,
    intro_html: str,
    course: dict,
    unsubscribe_url: str,
    status: str | None = None,
) -> tuple[str, str]:
    details = [
        ("Instructor", course.get("instructor")),
        ("Room", course.get("room")),
        ("Meets", course.get("days_and_times")),
    ]
    detail_text = "".join(f"{label}: {value}\n" for label, value in details if value)
    detail_html = "".join(
        f'<tr><td style="padding:4px 12px 4px 0;color:#777">{label}</td>'
        f'<td style="padding:4px 0">{html.escape(value)}</td></tr>'
        for label, value in details if value
    )

    status_text = f"Current Status: {status}\n" if status else ""
    status_html = (
        f'<tr><td style="padding:4px 12px 4px 0;color:#777">Current Status</td>'
        f'<td style="padding:4px 0;font-weight:600">{html.escape(status)}</td></tr>\n    '
        if status
        else ""
    )

    text = (
        f"{heading}\n\n"
        f"{intro_text}\n\n"
        f"{status_text}"
        f"{detail_text}"
        f"Term: {course['term']} {course['year']}\n\n"
        f"To unsubscribe, visit:\n{unsubscribe_url}\n"
    )
    html_body = f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:auto;color:#1a1a1a">
  <h2 style="margin:0 0 8px">{heading}</h2>
  <p style="margin:0 0 16px">{intro_html}</p>
  <table style="border-collapse:collapse;font-size:14px;margin-bottom:20px">
    {status_html}{detail_html}
    <tr><td style="padding:4px 12px 4px 0;color:#777">Term</td><td style="padding:4px 0">{html.escape(course['term'])} {course['year']}</td></tr>
  </table>
  <p style="font-size:12px;color:#888">No longer want to track this class?
    <a href="{html.escape(unsubscribe_url)}" style="color:#888">Unsubscribe</a>.
  </p>
</div>"""
    return text, html_body


async def send_confirmation(course: dict, email: str, unsubscribe_url: str) -> bool:
    line = _course_line(course)
    text, html_body = _render(
        "Tracking confirmed",
        f"You're now tracking {line}. We'll email you when a seat opens.",
        f"You're now tracking {html.escape(line)}. We'll email you when a seat opens.",
        course,
        unsubscribe_url,
        status=course.get("status") or "Unknown",
    )
    name = course.get("course_name") or "your class"
    subject = f"Now tracking {name} (#{course['class_number']})"
    return await send_email(email, subject, text, html_body, unsubscribe_url)


async def send_open_notification(course: dict, email: str, unsubscribe_url: str) -> bool:
    line = _course_line(course)
    text, html_body = _render(
        "Available seat",
        f"There's an available seat in {line}. Enroll on CUNYfirst before it fills up.",
        f"There's an available seat in {html.escape(line)}. Enroll on CUNYfirst before it fills up.",
        course,
        unsubscribe_url,
    )
    name = course.get("course_name") or "your class"
    subject = f"Available seat in {name} (#{course['class_number']})"
    return await send_email(email, subject, text, html_body, unsubscribe_url)
