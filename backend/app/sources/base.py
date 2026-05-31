"""Единый интерфейс источника данных.

Каждый коннектор (rss, cryptopanic, coingecko, twitter, telegram, mock)
реализует Source.fetch() и возвращает список нормализованных NewsItem.
Благодаря этому контракту источники взаимозаменяемы.
"""
from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from datetime import datetime

from ..models import NewsItem
from .coins import detect_coins


def make_id(*parts: str) -> str:
    """Стабильный id из url/title — для дедупликации между источниками."""
    raw = "|".join(p for p in parts if p)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def build_item(
    *,
    source: str,
    title: str,
    url: str | None,
    body: str,
    published_at: datetime,
    coins: list[str] | None = None,
) -> NewsItem:
    """Фабрика NewsItem с авто-детекцией монет и стабильным id."""
    return NewsItem(
        id=make_id(url or "", title),
        source=source,
        title=title,
        url=url,
        body=body,
        published_at=published_at,
        coins=coins if coins is not None else detect_coins(title, body),
    )


class Source(ABC):
    name: str = "base"

    @abstractmethod
    async def fetch(self, since: datetime) -> list[NewsItem]:
        """Вернуть новости, опубликованные не раньше `since`."""
        raise NotImplementedError
