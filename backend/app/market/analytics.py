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

from .coingecko import coingecko

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

    async def _markets_top100(self, force: bool = False) -> list[dict]:
        if not force:
            cached = self._markets100.get()
            if cached is not None:
                return cached
        data = await coingecko.get(
            "/coins/markets",
            {
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": 100,
                "page": 1,
                "price_change_percentage": "7d,30d,90d,1y",
            },
        )
        return self._markets100.set(data)

    # --- Капитализации и доминирование (раздел 3-4 спеки) ----------------------

    async def global_metrics(self) -> dict:
        cached = self._global.get()
        if cached is not None:
            return cached
        try:
            g = (await coingecko.get("/global"))["data"]
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
        # не кэшируем полностью пустой ответ (rate-limit) — чтобы быстро повторить
        if result["fear_greed"] is None and result["altseason"] is None:
            return result
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
            # предпочитаем 30д/7д (надёжнее заполнены на free-tier), затем 90д/1г
            return (
                c.get("price_change_percentage_30d_in_currency")
                or c.get("price_change_percentage_7d_in_currency")
                or c.get("price_change_percentage_90d_in_currency")
                or c.get("price_change_percentage_1y_in_currency")
            )

        btc = next((c for c in markets if c.get("symbol", "").lower() == "btc"), None)
        btc_perf = perf(btc) if btc else None
        if btc_perf is None:
            # в кэше markets нет данных об изменении (CoinGecko отдаёт их непостоянно)
            # — пробуем один свежий запрос в обход кэша
            try:
                markets = await self._markets_top100(force=True)
            except Exception:
                return None
            btc = next((c for c in markets if c.get("symbol", "").lower() == "btc"), None)
            btc_perf = perf(btc) if btc else None
            if btc_perf is None:
                return None

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
                data = await coingecko.get(
                    "/coins/markets",
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

    # --- Поиск и котировка по любой монете из топ-400 --------------------------

    async def search(self, q: str, limit: int = 10) -> list[dict]:
        """Поиск монеты по тикеру/имени среди топ-400 (вселенная rank-упорядочена)."""
        coins = await self.universe(400)
        ql = q.strip().lower()
        if not ql:
            return []
        starts = [c for c in coins if c["symbol"].lower().startswith(ql)]
        contains = [
            c for c in coins
            if c not in starts and (ql in c["symbol"].lower() or ql in (c["name"] or "").lower())
        ]
        return (starts + contains)[:limit]

    async def coin_quote(self, symbol: str) -> Optional[dict]:
        """Текущая котировка монеты по тикеру.

        Сначала пробуем уже закэшированные данные топ-100 (без доп. запроса к API —
        бережём rate-limit), для монет вне топ-100 — одиночный simple/price.
        """
        coins = await self.universe(400)
        c = next((x for x in coins if x["symbol"] == symbol.upper()), None)
        if not c:
            return None

        # 1) из кэша топ-100 — без обращения к сети
        try:
            m = next((x for x in await self._markets_top100() if x.get("id") == c["id"]), None)
        except Exception:
            m = None
        if m:
            return {
                "symbol": c["symbol"], "name": c["name"], "rank": c["rank"],
                "price": m.get("current_price"),
                "change_24h": m.get("price_change_percentage_24h"),
                "vol_24h": m.get("total_volume"),
            }

        # 2) монета вне топ-100 — одиночный запрос (может упереться в rate-limit)
        try:
            data = await coingecko.get(
                "/simple/price",
                {"ids": c["id"], "vs_currencies": "usd",
                 "include_24hr_change": "true", "include_24hr_vol": "true"},
            )
            d = data.get(c["id"], {})
        except Exception:
            d = {}
        return {
            "symbol": c["symbol"], "name": c["name"], "rank": c["rank"],
            "price": d.get("usd"),
            "change_24h": d.get("usd_24h_change"),
            "vol_24h": d.get("usd_24h_vol"),
        }


market_analytics = MarketAnalytics()
