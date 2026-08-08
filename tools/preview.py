"""Render every page and email locally and serve them, with no database, SMTP, or CUNY request.

    python tools/preview.py [--port 8001]

The sample data is the captured Global Search page in tests/fixtures, run through the
real parser. Pages come from the real Jinja templates and static files, and the emails
come from emailer.py itself, so a preview cannot show something production would not.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from bs4 import BeautifulSoup  # noqa: E402
from jinja2 import Environment, FileSystemLoader  # noqa: E402

from cuny_tracker import emailer, main  # noqa: E402
from cuny_tracker.constants import INSTITUTIONS, SESSIONS, TERMS  # noqa: E402
from cuny_tracker.models import CourseParams  # noqa: E402
from cuny_tracker.processor import process  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "cuny_tracker"
FIXTURE = ROOT / "tests" / "fixtures" / "mth3020_detail.html"

env = Environment(loader=FileSystemLoader(str(APP / "templates")))


def sample_lookup() -> dict:
    details, avail = process(BeautifulSoup(FIXTURE.read_text(), "lxml"))
    params = CourseParams(
        details.course_number, "Fall Term", 2026, "Regular Academic Session", "Baruch College"
    )
    return {"ok": True, "found": True, **main._status_dict(params, details, avail)}


def homepage(result: dict | None) -> str:
    page = env.get_template("index.html").render(
        institutions=INSTITUTIONS,
        terms=TERMS,
        sessions=SESSIONS,
        default_term=main.DEFAULT_TERM,
        default_year=main.DEFAULT_YEAR,
        year_options=[main.DEFAULT_YEAR, main.DEFAULT_YEAR + 1],
    )
    if result is None:
        return page

    # Stand in for the network so app.js renders a result without anyone scraping CUNY.
    script_tag = '<script src="/static/app.js"></script>'
    stub = (
        "<script>window.fetch = function () { return Promise.resolve("
        f"{{ json: function () {{ return Promise.resolve({json.dumps(result)}); }} }}"
        "); };</script>"
    )
    driver = f"""<script>
document.getElementById("class_number").value = {json.dumps(result["class_number"])};
document.getElementById("check-btn").click();
</script>"""
    return page.replace(script_tag, stub + script_tag + driver)


def emails(result: dict) -> dict[str, str]:
    captured: dict[str, str] = {}

    async def capture(to_email, subject, text_body, html_body, unsubscribe_url):
        captured[subject] = html_body
        return True

    real_send, emailer.send_email = emailer.send_email, capture
    url = "https://cunytracker.com/unsubscribe?token=preview"
    try:
        asyncio.run(emailer.send_confirmation(result, "student@example.com", url))
        asyncio.run(emailer.send_open_notification(result, "student@example.com", url))
    finally:
        emailer.send_email = real_send
    return captured


def build(out: Path) -> list[tuple[str, str]]:
    shutil.copytree(APP / "static", out / "static")
    result = sample_lookup()

    pages = [
        ("home.html", "Homepage", homepage(None)),
        ("lookup.html", "Homepage after a lookup", homepage(result)),
        ("unsubscribed.html", "Unsubscribe, removed",
         env.get_template("unsubscribe.html").render(removed=True)),
        ("unsubscribe-invalid.html", "Unsubscribe, bad link",
         env.get_template("unsubscribe.html").render(removed=False)),
    ]
    for subject, body in emails(result).items():
        name = "email-" + subject.split()[0].lower() + ".html"
        pages.append((name, f"Email: {subject}", body))

    links = "".join(f'<li><a href="/{f}">{label}</a></li>' for f, label, _ in pages)
    (out / "index.html").write_text(
        '<meta charset="utf-8"><title>cuny-tracker preview</title>'
        '<body style="font:16px/1.7 system-ui;max-width:40rem;margin:3rem auto">'
        f"<h1>cuny-tracker preview</h1><ul>{links}</ul>"
    )
    for name, _, html in pages:
        (out / name).write_text(html)
    return [(name, label) for name, label, _ in pages]


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    port = parser.parse_args().port

    out = Path(tempfile.mkdtemp(prefix="cuny-tracker-preview-"))
    for name, label in build(out):
        print(f"  http://127.0.0.1:{port}/{name:<26} {label}")
    print(f"\nServing {out} on http://127.0.0.1:{port} (ctrl-c to stop)")

    handler = partial(SimpleHTTPRequestHandler, directory=str(out))
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    except OSError as exc:
        shutil.rmtree(out, ignore_errors=True)
        raise SystemExit(f"Could not listen on port {port} ({exc}). Try --port.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        shutil.rmtree(out, ignore_errors=True)


if __name__ == "__main__":
    cli()
