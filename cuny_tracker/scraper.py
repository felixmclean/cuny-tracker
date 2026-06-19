from __future__ import annotations

import asyncio
import logging

import httpx
from bs4 import BeautifulSoup

from .constants import (
    COLLEGE_CODES,
    DEFAULT_INSTITUTION,
    GLOBAL_SEARCH_URL,
    HEADERS,
)
from .models import CourseParams, get_current_term_and_year, get_global_search_term_value

log = logging.getLogger("cuny_tracker.scraper")


class ScrapeError(RuntimeError):
    pass


class Scraper:

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self._timeout = httpx.Timeout(timeout_seconds)
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    async def _bootstrap(self) -> httpx.AsyncClient:
        year, term = get_current_term_and_year()
        term_code = get_global_search_term_value(year, term)
        payload = {
            "selectedInstName": f"{DEFAULT_INSTITUTION} |",
            "inst_selection": COLLEGE_CODES[DEFAULT_INSTITUTION],
            "selectedTermName": f"{year} {term}",
            "term_value": str(term_code),
            "next_btn": "Next",
        }
        client = httpx.AsyncClient(headers=HEADERS, timeout=self._timeout, follow_redirects=True)
        try:
            await client.post(GLOBAL_SEARCH_URL, data=payload)
        except Exception:
            await client.aclose()
            raise
        log.info("Scraper session established.")
        return client

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            async with self._lock:
                if self._client is None:
                    self._client = await self._bootstrap()
        return self._client

    async def _drop_client(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None

    async def refresh(self) -> None:
        async with self._lock:
            await self._drop_client()
            self._client = await self._bootstrap()

    async def close(self) -> None:
        async with self._lock:
            await self._drop_client()

    async def fetch(self, params: CourseParams) -> BeautifulSoup:
        encoded = params.encoded_params()
        try:
            client = await self._ensure_client()
            resp = await client.get(GLOBAL_SEARCH_URL, params=encoded)
            return BeautifulSoup(resp.text, "lxml")
        except Exception as first_err:
            log.warning("Scrape failed (%s); refreshing session and retrying.", first_err)
            try:
                await self.refresh()
                resp = await self._client.get(GLOBAL_SEARCH_URL, params=encoded)  # type: ignore[union-attr]
                return BeautifulSoup(resp.text, "lxml")
            except Exception as second_err:
                raise ScrapeError(str(second_err)) from second_err
