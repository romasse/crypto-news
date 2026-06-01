"""Time-Window Aggregator: сбор данных по требованию за последние N часов.

Конвейер: источники -> дедуп -> AI-анализ новых -> сохранение ->
агрегация сентимента по монетам для Visualization Engine.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from ..inference.analyzer import Analyzer
from ..market.analytics import market_analytics
from ..market.provider import market_provider
from ..models import AnalyzedItem, CollectResult, NewsItem
from ..sources import coins as coins_mod
from ..sources.registry import get_enabled_sources
from ..store.db import store

# Ограничение одновременных вызовов Claude: всплеск из 20+ запросов разом ловит
# rate-limit (429), и часть новостей молча откатывается в stub. Семафор держит
# параллельность в разумных рамках — SDK сам ретраит, до стаба почти не доходит.
_MAX_CONCURRENT_ANALYSES = 5


class Aggregator:
    def __init__(self):
        self.analyzer = Analyzer()

    async def collect(self, window_hours: float = 2.0) -> CollectResult:
        since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

        # 0. Прогреваем вселенную топ-400 и регистрируем имена для детекта монет,
        #    чтобы новости тегировались по любой из 400 (нужно для поиска).
        try:
            coins_mod.set_universe(await market_analytics.universe(limit=400))
        except Exception:
            pass

        # 1. Сбор из всех включённых источников параллельно
        sources = get_enabled_sources()
        fetched = await asyncio.gather(
            *(s.fetch(since) for s in sources), return_exceptions=True
        )
        raw: list[NewsItem] = []
        for res in fetched:
            if isinstance(res, Exception):
                continue
            raw.extend(res)

        # 2. Дедуп по id (между источниками и внутри окна)
        unique: dict[str, NewsItem] = {}
        for item in raw:
            unique.setdefault(item.id, item)

        # 3. AI-анализ только новых (ещё не разобранных) событий.
        #    Correlation Check — объективные макро-данные, одинаковые для всего окна:
        #    считаем срез рынка один раз и проставляем всем новым событиям.
        new_items = [it for it in unique.values() if not store.has(it.id)]
        snapshot = await market_provider.snapshot()
        correlation = await market_provider.correlation_check()
        market_context = self._market_context(snapshot)
        sem = asyncio.Semaphore(_MAX_CONCURRENT_ANALYSES)

        async def _analyze(it: NewsItem):
            async with sem:
                return await self.analyzer.analyze(it, market_context=market_context)

        analyses = await asyncio.gather(*(_analyze(it) for it in new_items))
        for item, analysis in zip(new_items, analyses):
            analysis.correlation_check = correlation
            store.upsert(item, analysis)

        # 4. Достаём все события окна (новые + ранее сохранённые) для ответа
        window_items = [
            a for a in store.feed(limit=500) if a.item.published_at >= since
        ]
        window_items.sort(key=lambda a: a.item.published_at, reverse=True)

        return CollectResult(
            window_hours=window_hours,
            collected=len(unique),
            analyzed=len(new_items),
            items=window_items,
            sentiment_by_coin=self.sentiment_by_coin(window_items),
            market=await market_provider.snapshot(),
        )

    @staticmethod
    def _market_context(snapshot: dict) -> str:
        """Компактная строка рыночного среза для промпта Claude."""
        parts = []
        for coin in ("BTC", "ETH", "SOL"):
            p = snapshot.get("prices", {}).get(coin)
            if p and p.get("price") is not None:
                ch = p.get("change_24h")
                ch_str = f" ({ch:+.1f}% 24h)" if isinstance(ch, (int, float)) else ""
                parts.append(f"{coin} ${p['price']:,.0f}{ch_str}")
        funding = snapshot.get("btc_funding_rate")
        if isinstance(funding, (int, float)):
            parts.append(f"BTC funding {funding * 100:.4f}%")
        return "; ".join(parts)

    @staticmethod
    def sentiment_by_coin(items: list[AnalyzedItem]) -> dict[str, float]:
        """Средний сентимент по каждой монете — вход для графиков."""
        buckets: dict[str, list[float]] = defaultdict(list)
        for a in items:
            for coin in a.item.coins:
                buckets[coin].append(a.analysis.sentiment)
        return {
            coin: round(sum(vals) / len(vals), 3)
            for coin, vals in sorted(buckets.items())
            if vals
        }


aggregator = Aggregator()
