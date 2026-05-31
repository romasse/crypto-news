"""RSS-источник: бесплатные ленты профильных изданий (CoinDesk, Cointelegraph).

Targeted ingestion из спеки: тянем только заданные фиды, а не весь веб.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from time import mktime

import feedparser

from ..models import NewsItem
from .base import Source, build_item

DEFAULT_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://decrypt.co/feed",
]


def _parsed_time(entry) -> datetime:
    struct = getattr(entry, "published_parsed", None) or getattr(entry, "updated_parsed", None)
    if struct:
        return datetime.fromtimestamp(mktime(struct), tz=timezone.utc)
    return datetime.now(timezone.utc)


class RSSSource(Source):
    name = "rss"

    def __init__(self, feeds: list[str] | None = None):
        self.feeds = feeds or DEFAULT_FEEDS

    def _fetch_feed_sync(self, url: str, since: datetime) -> list[NewsItem]:
        # feedparser синхронный — оборачиваем в поток, чтобы не блокировать event loop.
        parsed = feedparser.parse(url)
        items: list[NewsItem] = []
        for entry in parsed.entries:
            published = _parsed_time(entry)
            if published < since:
                continue
            title = getattr(entry, "title", "").strip()
            if not title:
                continue
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
            items.append(
                build_item(
                    source=self.name,
                    title=title,
                    url=getattr(entry, "link", None),
                    body=summary,
                    published_at=published,
                )
            )
        return items

    async def fetch(self, since: datetime) -> list[NewsItem]:
        tasks = [asyncio.to_thread(self._fetch_feed_sync, url, since) for url in self.feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[NewsItem] = []
        for res in results:
            if isinstance(res, Exception):
                # один упавший фид не должен валить сбор целиком
                continue
            items.extend(res)
        return items
