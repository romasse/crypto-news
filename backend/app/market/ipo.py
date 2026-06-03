"""IPO Calendar: Alpha Vantage — ближайшие IPO на рынке США.

Ключ бесплатный, получить за 1 мин на alphavantage.co.
Без ключа возвращает пустой список (не ломает сайт).
Данные кэшируются на 1 час — IPO-расписание меняется редко.
"""
from __future__ import annotations

import csv
import io
import time

import httpx

from ..config import settings

_CACHE_TTL = 3600.0  # 1 час


class IPOProvider:
    def __init__(self):
        self._cache: list[dict] = []
        self._cache_at: float = 0.0

    async def upcoming(self) -> list[dict]:
        if self._cache and (time.monotonic() - self._cache_at) < _CACHE_TTL:
            return self._cache
        data = await self._fetch()
        if data:
            self._cache = data
            self._cache_at = time.monotonic()
        return self._cache or data

    async def _fetch(self) -> list[dict]:
        if not settings.alpha_vantage_key:
            return []
        url = "https://www.alphavantage.co/query"
        params = {"function": "IPO_CALENDAR", "apikey": settings.alpha_vantage_key}
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
            reader = csv.DictReader(io.StringIO(r.text))
            result = []
            for row in reader:
                result.append({
                    "symbol": row.get("symbol", "").strip(),
                    "name": row.get("name", "").strip(),
                    "ipo_date": row.get("ipoDate", "").strip(),
                    "price_low": _float(row.get("priceRangeLow")),
                    "price_high": _float(row.get("priceRangeHigh")),
                    "currency": row.get("currency", "USD").strip(),
                    "exchange": row.get("exchange", "").strip(),
                    "shares": _int(row.get("shares")),
                })
            # сортируем по дате, ближайшие сначала
            result.sort(key=lambda x: x["ipo_date"] or "9999")
            return result
        except Exception:
            return []


def _float(v) -> float | None:
    try:
        return float(v) if v and str(v).strip() else None
    except (ValueError, TypeError):
        return None


def _int(v) -> int | None:
    try:
        return int(v) if v and str(v).strip() else None
    except (ValueError, TypeError):
        return None


ipo_provider = IPOProvider()
