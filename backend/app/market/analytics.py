"""Рыночная аналитика: капитализации, доминирование, индексы, вселенная активов.

Источники в спеке (CMC, TradingView) платные/без открытого API, поэтому берём
бесплатные эквиваленты:
- CoinGecko /global + /coins/markets — total/total2/others, доминирование, топ-N.
- alternative.me — Fear & Greed Index.
- Altseason — считаем по методике blockchaincenter (доля топ-альтов, обогнавших BTC).
"""
from __future__ import annotations

import time
from typing import Optional

import httpx

_GLOBAL_URL = "https://api.coingecko.com/api/v3/global"
_MARKETS_URL = "https://api.coingecko.com/api/v3/coins/markets"
_FNG_URL = "https://api.alternative.me/fng/"

# стейблкоины исключаем из altseason-расчёта (их не сравниваем с BTC)
_STABLES = {"usdt", "usdc", "dai", "tusd", "fdusd", "usde", "busd", "usdd", "pyusd", "gusd"}


class _TTLCache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self._v = None
        self._at = 0.0

    def get(self):
        if self._v is not None and (time.monotonic() - self._at) < self.ttl:
            return self._v
        return None

    def set(self, v):
        self._v = v
        self._at = time.monotonic()
        return v


class MarketAnalytics:
    def __init__(self):
        self._global = _TTLCache(120)
        self._indices = _TTLCache(300)
        self._universe = _TTLCache(3600)
        self._markets100 = _TTLCache(120)

    async def _get_json(self, url: str, params: dict | None = None):
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(url, params=params or {})
            r.raise_for_status()
            return r.json()

    async def _markets_top100(self) -> list[dict]:
        cached = self._markets100.get()
        if cached is not None:
            return cached
        data = await self._get_json(
            _MARKETS_URL,
            {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "90d,30d,1y",
            },
        )
        return self._markets100.set(data)

    # --- Капитализации и доминирование (раздел 3-4 спеки) ----------------------

    async def global_metrics(self) -> dict:
        cached = self._global.get()
        if cached is not None:
            return cached
        try:
            g = (await self._get_json(_GLOBAL_URL))["data"]
            markets = await self._markets_top100()
        except Exception:
            return {}

        total = g["total_market_cap"]["usd"]
        pct = g.get("market_cap_percentage", {})
        btc_pct = pct.get("btc", 0.0)
        eth_pct = pct.get("eth", 0.0)
        btc_mcap = total * btc_pct / 100

        def mcap(c):
            return c.get("market_cap") or 0

        top10 = sum(mcap(c) for c in markets[:10])
        top100_ex_btc = sum(mcap(c) for c in markets[1:100])  # ранги 2..100
        others = max(total - top10, 0.0)  # конвенция TradingView: всё, кроме топ-10

        result = {
            "TOTAL": total,
            "TOTAL2": max(total - btc_mcap, 0.0),  # всё, кроме BTC
            "top100_ex_btc": top100_ex_btc,
            "OTHERS": others,
            "dominance": {
                "BTC": round(btc_pct, 2),
                "ETH": round(eth_pct, 2),
                "OTHERS": round(others / total * 100, 2) if total else None,
            },
        }
        return self._global.set(result)

    # --- Индексы настроений (раздел 2 спеки) -----------------------------------

    async def indices(self) -> dict:
        cached = self._indices.get()
        if cached is not None:
            return cached
        result = {"fear_greed": await self._fear_greed(), "altseason": await self._altseason()}
        return self._indices.set(result)

    async def _fear_greed(self) -> Optional[dict]:
        try:
            d = (await self._get_json(_FNG_URL, {"limit": 1}))["data"][0]
            return {"value": int(d["value"]), "classification": d["value_classification"]}
        except Exception:
            return None

    async def _altseason(self) -> Optional[dict]:
        """Доля топ-50 альтов (без стейблов), обогнавших BTC за 90д. >=75 → альтсезон."""
        try:
            markets = await self._markets_top100()
        except Exception:
            return None

        def perf(c):
            return (
                c.get("price_change_percentage_90d_in_currency")
                or c.get("price_change_percentage_30d_in_currency")
                or c.get("price_change_percentage_1y_in_currency")
            )

        btc = next((c for c in markets if c.get("symbol", "").lower() == "btc"), None)
        btc_perf = perf(btc) if btc else None
        if btc_perf is None:
            return None  # нет исторических данных у источника — индекс недоступен

        alts = [
            c
            for c in markets[:55]
            if c.get("symbol", "").lower() not in _STABLES
            and c.get("symbol", "").lower() != "btc"
            and perf(c) is not None
        ][:50]
        if not alts:
            return None
        beating = sum(1 for c in alts if perf(c) > btc_perf)
        index = round(beating / len(alts) * 100)
        phase = "altseason" if index >= 75 else "bitcoin" if index <= 25 else "neutral"
        return {"value": index, "phase": phase, "sample": len(alts)}

    # --- Вселенная активов: жёсткий лимит топ-400 (раздел 1 спеки) -------------

    async def universe(self, limit: int = 400) -> list[dict]:
        cached = self._universe.get()
        if cached is not None:
            return cached[:limit]
        coins: list[dict] = []
        try:
            for page in (1, 2):  # 2 страницы по 200 = топ-400
                data = await self._get_json(
                    _MARKETS_URL,
                    {
                        "vs_currency": "usd",
                        "order": "market_cap_desc",
                        "per_page": 200,
                        "page": page,
                    },
                )
                for c in data:
                    coins.append(
                        {
                            "rank": c.get("market_cap_rank"),
                            "symbol": (c.get("symbol") or "").upper(),
                            "id": c.get("id"),
                            "name": c.get("name"),
                        }
                    )
        except Exception:
            return coins[:limit]
        return self._universe.set(coins)[:limit]


market_analytics = MarketAnalytics()
