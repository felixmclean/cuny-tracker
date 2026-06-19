# CUNY Seat Tracker

CUNY classes fill quickly and almost never have waitlists. The official tools require manually refreshing to check for open seats and offer no automated notifications. CUNY Tracker lets you enter any class and your email address, and emails you when a seat opens.

Live site: [cunytracker.com](https://cunytracker.com)

<img src="website.png" alt="Screenshot">

## How it works

You can check a class's current availability anytime, or subscribe to get an email when it opens. A scheduler rechecks every tracked class every five minutes, and when a section goes from closed or waitlisted to open, it emails each subscriber with a one-click unsubscribe link. Subscriptions and the latest scraped data are stored in Postgres. The scraper, scheduler, and web server all run in a single process.

![Architecture](diagram.svg)

## Design decisions

- Single async process. FastAPI, httpx, and an AsyncIO scheduler share one event loop, so scraping, polling, and serving all run together without a message broker or separate worker.
- No connection pool. Each query opens its own psycopg connection. This avoids issues with Neon's scale-to-zero behavior and its PgBouncer transaction pooling, which don't work well with long-lived pooled connections.
- Failure isolation. A scrape, parse, or email error is logged and retried on the next cycle. It never takes down the web server.
- Status only advances after a successful send. Emails fire only on a closed-to-open transition, and a subscriber's stored status only updates once the email actually sends. This avoids missed notifications and repeat emails while a class stays open.
- One-click unsubscribe (RFC 8058). Gmail and Outlook render a native unsubscribe button, and every email carries a tokenized link.
  
## Stack

- Python, FastAPI, Uvicorn
- PostgreSQL (Neon) via async psycopg
- APScheduler
- httpx, BeautifulSoup
- Jinja2, vanilla CSS and JS
- Resend (SMTP) for email delivery
- Docker, Nginx, Let's Encrypt on Oracle Cloud ARM

## Run locally

Requires a Postgres connection string (a free Neon database works)

With Docker:
```bash
git clone https://github.com/felixmclean/cuny-tracker
cd cuny-tracker
cp .env.example .env        # set DATABASE_URL and the SMTP values
docker compose up --build
```

With Python:
```bash
pip install -r requirements.txt && python app.py
```

## Limitations

The scraper depends on CUNY Global Search's HTML. A markup change there may break parsing until the selectors are updated. Notifications are also bounded by the poll interval so an open seat might take up to five minutes to be detected. 

## Credit

Endpoint and HTML-parsing logic adapted from [cuny-global-search-bot](https://github.com/mkbhuiyan96/cuny-global-search-bot). The web app, persistence, scheduling, email, and deployment are original.
