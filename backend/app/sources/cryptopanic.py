"""CryptoPanic — агрегатор крипто-новостей. Бесплатный API требует auth_token.

Токен берётся из CRYPTOPANIC_TOKEN. Без токена источник тихо отдаёт пустой
список (а не падает), чтобы остальной конвейер продолжал работать.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from ..models import NewsItem
from .base import Source, build_item
from .coins import detect_coins

_API_URL = "https://cryptopanic.com/api/v1/posts/"


def _parse_time(value: str) -> datetime:
    try:
        # формат вида 2026-05-31T21:16:23Z
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


class CryptoPanicSource(Source):
    name = "cryptopanic"

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("CRYPTOPANIC_TOKEN")

    @property
    def configured(self) -> bool:
        return bool(self.token)

    async def fetch(self, since: datetime) -> list[NewsItem]:
        if not self.configured:
            return []
        params = {"auth_token": self.token, "public": "true"}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(_API_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        items: list[NewsItem] = []
        for post in data.get("results", []):
            published = _parse_time(post.get("published_at", ""))
            if published < since:
                continue
            title = (post.get("title") or "").strip()
            if not title:
                continue
            # CryptoPanic отдаёт валюты явно — используем их + дочищаем детектором
            currencies = [c.get("code", "").upper() for c in post.get("currencies", []) or []]
            coins = sorted(set(currencies) | set(detect_coins(title))) or detect_coins(title)
            items.append(
                build_item(
                    source=self.name,
                    title=title,
                    url=post.get("url"),
                    body=post.get("title", ""),
                    published_at=published,
                    coins=coins,
                )
            )
        return items
