"""IPO Calendar: Alpha Vantage — ближайшие IPO на рынке США.

Ключ бесплатный, получить за 1 мин на alphavantage.co.
Без ключа возвращает пустой список (не ломает сайт).
Данные кэшируются на 1 час — IPO-расписание меняется редко.

Alpha Vantage при ошибке/лимите возвращает JSON вместо CSV
({"Information": "..."} или {"Note": "..."}). Определяем это по первому символу.
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
                # явно декодируем байты через utf-8-sig чтобы снять BOM
                raw = r.content.decode('utf-8-sig', errors='replace').strip()

            # Alpha Vantage при rate-limit/ошибке возвращает JSON вместо CSV
            if raw.startswith('{') or raw.startswith('['):
                return []

            reader = csv.DictReader(io.StringIO(raw))
            # нормализуем имена колонок — убираем пробелы на случай нестандартного формата
            if reader.fieldnames:
                reader.fieldnames = [f.strip() for f in reader.fieldnames]

            result = []
            for row in reader:
                sym = _str(row, "symbol", "Symbol")
                name = _str(row, "name", "Name")
                if not sym and not name:
                    continue  # пропускаем пустые строки
                result.append({
                    "symbol": sym,
                    "name": name,
                    "ipo_date": _str(row, "ipoDate", "IPO Date", "ipo_date"),
                    "price_low": _float(_str(row, "priceRangeLow", "Price Range Low")),
                    "price_high": _float(_str(row, "priceRangeHigh", "Price Range High")),
                    "currency": _str(row, "currency", "Currency") or "USD",
                    "exchange": _str(row, "exchange", "Exchange"),
                    "shares": None,
                })

            result.sort(key=lambda x: x["ipo_date"] or "9999")
            return result
        except Exception:
            return []


def _str(row: dict, *keys: str) -> str:
    """Возвращает первое непустое значение по списку ключей."""
    for k in keys:
        v = row.get(k)
        if v is not None:
            return str(v).strip()
    return ""


def _float(v: str) -> float | None:
    try:
        return float(v) if v and v.strip() else None
    except (ValueError, TypeError):
        return None


ipo_provider = IPOProvider()
