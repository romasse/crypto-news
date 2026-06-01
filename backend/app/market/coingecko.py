"""Единый клиент CoinGecko: ключ (demo/pro), троттлинг и ретраи на 429.

Все обращения к CoinGecko идут через него, чтобы:
- при наличии ключа подниматься на demo/pro-лимиты (заголовок + домен);
- не превышать публичный rate-limit (минимальный интервал между запросами);
- мягко переживать 429 (ретрай с бэкоффом), а не падать в null.
"""
from __future__ import annotations

import asyncio
import time

import httpx

from ..config import settings

_PUBLIC = "https://api.coingecko.com/api/v3"
_PRO = "https://pro-api.coingecko.com/api/v3"


class CoinGeckoClient:
    def __init__(self):
        self.key = settings.coingecko_api_key
        self.pro = settings.coingecko_pro and bool(self.key)
        self.base = _PRO if self.pro else _PUBLIC
        self._lock = asyncio.Lock()
        # минимальный интервал между запросами: с ключом можно чаще
        self._min_interval = 0.3 if self.key else 1.3
        self._last = 0.0

    def _headers(self) -> dict:
        if not self.key:
            return {}
        return {("x-cg-pro-api-key" if self.pro else "x-cg-demo-api-key"): self.key}

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    async def get(self, path: str, params: dict | None = None, retries: int = 2):
        """GET к CoinGecko с троттлингом и ретраями на 429. Бросает при провале."""
        url = self.base + path
        last_exc: Exception | None = None
        for attempt in range(retries + 1):
            await self._throttle()
            try:
                async with httpx.AsyncClient(timeout=20) as client:
                    r = await client.get(url, params=params or {}, headers=self._headers())
                if r.status_code == 429 and attempt < retries:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:  # noqa: BLE001 — пробуем ещё раз, иначе пробрасываем
                last_exc = e
                if attempt < retries:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise
        if last_exc:
            raise last_exc


coingecko = CoinGeckoClient()
