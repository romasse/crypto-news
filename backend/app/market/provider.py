"""Рыночные данные: CoinGecko (цены/объёмы/изменение) + Binance (funding rate).

Питает реальный Correlation Check и панель цен на дашборде. Результат кэшируется
на короткий TTL, чтобы повторные /collect не упирались в rate-limit бесплатных API.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

from ..models import CorrelationCheck

# наш тикер -> id в CoinGecko
_COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "XRP": "ripple",
    "BNB": "binancecoin",
    "DOGE": "dogecoin",
    "ADA": "cardano",
}
_ID_TO_TICKER = {v: k for k, v in _COINGECKO_IDS.items()}

_COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
_BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"

_CACHE_TTL = 60.0  # сек


class MarketProvider:
    def __init__(self):
        self._cache: dict = {}
        self._cache_at: float = 0.0

    async def _fetch_prices(self) -> dict:
        ids = ",".join(_COINGECKO_IDS.values())
        params = {
            "ids": ids,
            "vs_currencies": "usd",
            "include_24hr_vol": "true",
            "include_24hr_change": "true",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(_COINGECKO_URL, params=params)
            resp.raise_for_status()
            raw = resp.json()
        out: dict[str, dict] = {}
        for cg_id, data in raw.items():
            ticker = _ID_TO_TICKER.get(cg_id, cg_id.upper())
            out[ticker] = {
                "price": data.get("usd"),
                "vol_24h": data.get("usd_24h_vol"),
                "change_24h": data.get("usd_24h_change"),
            }
        return out

    async def _fetch_btc_funding(self) -> Optional[float]:
        try:
            async with httpx.AsyncClient(timeout=12) as client:
                resp = await client.get(_BINANCE_FUNDING_URL, params={"symbol": "BTCUSDT"})
                resp.raise_for_status()
                return float(resp.json().get("lastFundingRate"))
        except Exception:
            return None

    async def snapshot(self) -> dict:
        """Кэшированный срез рынка: {prices: {...}, btc_funding_rate: float}."""
        if self._cache and (time.monotonic() - self._cache_at) < _CACHE_TTL:
            return self._cache
        try:
            prices = await self._fetch_prices()
        except Exception:
            prices = {}
        funding = await self._fetch_btc_funding()
        self._cache = {"prices": prices, "btc_funding_rate": funding}
        self._cache_at = time.monotonic()
        return self._cache

    async def correlation_check(self) -> CorrelationCheck:
        """Реальный чек-лист макро-сверки на основе рыночных данных."""
        snap = await self.snapshot()
        prices = snap.get("prices", {})
        btc = prices.get("BTC", {})

        vol = btc.get("vol_24h")
        btc_volume = f"${vol / 1e9:.1f}B (24h)" if isinstance(vol, (int, float)) else None

        change = btc.get("change_24h")
        # DXY/Nasdaq бесплатно не достаём — вместо них даём контекст по самому BTC.
        btc_ctx = f"BTC 24h: {change:+.2f}%" if isinstance(change, (int, float)) else None

        funding = snap.get("btc_funding_rate")
        funding_rate = f"{funding * 100:.4f}% (BTC perp)" if isinstance(funding, (int, float)) else None

        return CorrelationCheck(
            btc_volume=btc_volume,
            dxy=None,        # нет бесплатного источника
            nasdaq=btc_ctx,  # заглушка контекста до подключения макро-API
            funding_rate=funding_rate,
        )


market_provider = MarketProvider()
