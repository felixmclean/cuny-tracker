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


async def send_confirmation(course: dict, email: str, unsubscribe_url: str) -> bool:
    name = course.get("course_name") or "your class"
    title = course.get("course_title") or ""
    full_name = f"{name} {title}".strip()
    tracking_line = f"{full_name} (#{course['class_number']}) at {course['institution']}"
    status = course.get("status") or "Unknown"
    subject = f"Tracking {name} (#{course['class_number']})"

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

    text = (
        f"Tracking confirmed\n\n"
        f"You're now tracking {tracking_line}. We'll email you when a seat opens.\n\n"
        f"Current Status: {status}\n"
        f"{detail_text}"
        f"Term: {course['term']} {course['year']}\n\n"
        f"To unsubscribe, visit:\n{unsubscribe_url}\n"
    )
    html_body = f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:auto;color:#1a1a1a">
  <h2 style="margin:0 0 8px">Tracking confirmed</h2>
  <p style="margin:0 0 16px">You're now tracking {html.escape(tracking_line)}. We'll email you when a seat opens.</p>
  <table style="border-collapse:collapse;font-size:14px;margin-bottom:20px">
    <tr><td style="padding:4px 12px 4px 0;color:#777">Current Status</td><td style="padding:4px 0;font-weight:600">{html.escape(status)}</td></tr>
    {detail_html}
    <tr><td style="padding:4px 12px 4px 0;color:#777">Term</td><td style="padding:4px 0">{html.escape(course['term'])} {course['year']}</td></tr>
  </table>
  <p style="font-size:12px;color:#888">Not you, or no longer want to track this class?
    <a href="{html.escape(unsubscribe_url)}" style="color:#888">Unsubscribe</a>.
  </p>
</div>"""
    return await send_email(email, subject, text, html_body, unsubscribe_url)


async def send_open_notification(course: dict, email: str, unsubscribe_url: str) -> bool:
    name = course.get("course_name") or "your class"
    title = course.get("course_title") or ""
    full_name = f"{name} {title}".strip()
    course_line = f"{full_name} (#{course['class_number']}) at {course['institution']}"
    subject = f"Seat available {name} (#{course['class_number']})"

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

    text = (
        f"Seat available\n\n"
        f"There's an available seat for {course_line}. Enroll on CUNYfirst before it fills up.\n\n"
        f"{detail_text}"
        f"Term: {course['term']} {course['year']}\n\n"
        f"To unsubscribe, visit:\n{unsubscribe_url}\n"
    )
    html_body = f"""\
<div style="font-family:system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:auto;color:#1a1a1a">
  <h2 style="margin:0 0 8px">Seat available</h2>
  <p style="margin:0 0 16px">There's an available seat for {html.escape(course_line)}. Enroll on CUNYfirst before it fills up.</p>
  <table style="border-collapse:collapse;font-size:14px;margin-bottom:20px">
    {detail_html}
    <tr><td style="padding:4px 12px 4px 0;color:#777">Term</td><td style="padding:4px 0">{html.escape(course['term'])} {course['year']}</td></tr>
  </table>
  <p style="font-size:12px;color:#888">Not you, or no longer want to track this class?
    <a href="{html.escape(unsubscribe_url)}" style="color:#888">Unsubscribe</a>.
  </p>
</div>"""
    return await send_email(email, subject, text, html_body, unsubscribe_url)
