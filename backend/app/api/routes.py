"""REST API: лента, сбор по требованию, сводка сентимента."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query

from ..aggregator.service import aggregator
from ..config import settings
from ..market.analytics import market_analytics
from ..market.provider import market_provider
from ..models import AnalyzedItem, CollectResult
from ..store.db import store

router = APIRouter(prefix="/api")


@router.get("/health")
async def health() -> dict:
    import os

    return {
        "status": "ok",
        "ai_enabled": settings.ai_enabled,
        "model": settings.model if settings.ai_enabled else "stub",
        "sources": settings.enabled_sources,
        "cryptopanic_configured": bool(os.getenv("CRYPTOPANIC_TOKEN")),
    }


@router.get("/feed", response_model=List[AnalyzedItem])
async def feed(
    coin: Optional[str] = Query(None, description="Фильтр по тикеру, напр. BTC"),
    limit: int = Query(100, ge=1, le=500),
) -> List[AnalyzedItem]:
    """Лента ранее собранных и проанализированных новостей."""
    return store.feed(coin=coin, limit=limit)


@router.post("/collect", response_model=CollectResult)
async def collect(
    hours: float = Query(2.0, ge=0.25, le=48, description="Окно сбора в часах"),
) -> CollectResult:
    """Time-Window: собрать и разобрать новости за последние `hours` часов (синхронно)."""
    return await aggregator.collect(window_hours=hours)


@router.post("/collect/start")
async def collect_start(
    hours: float = Query(2.0, ge=0.25, le=48, description="Окно сбора в часах"),
) -> dict:
    """Запускает сбор в фоне и сразу отвечает (не блокирует UI)."""
    started = aggregator.start_background(window_hours=hours)
    return {"started": started, "status": aggregator.status}


@router.get("/collect/status")
async def collect_status() -> dict:
    """Статус фонового сбора: running/phase/done/total/итоги."""
    return aggregator.status


@router.get("/market")
async def market() -> dict:
    """Текущий срез рынка: цены/объёмы/изменение по монетам + funding rate BTC."""
    return await market_provider.snapshot()


@router.get("/global")
async def global_metrics() -> dict:
    """Капитализации (TOTAL/TOTAL2/OTHERS) и доминирование (BTC.D/ETH.D/OTHERS.D)."""
    return await market_analytics.global_metrics()


@router.get("/indices")
async def indices() -> dict:
    """Индексы настроений: Fear & Greed и Altseason."""
    return await market_analytics.indices()


@router.get("/universe")
async def universe(limit: int = Query(400, ge=1, le=400)) -> dict:
    """Вселенная активов — топ-N по капитализации (жёсткий лимит листинга)."""
    coins = await market_analytics.universe(limit=limit)
    return {"count": len(coins), "coins": coins}


@router.get("/markets")
async def markets(limit: int = Query(100, ge=1, le=100)) -> dict:
    """Топ-N монет с капой/объёмом/изменением/лого — для вкладки «Объём рынка»."""
    return {"coins": await market_analytics.markets(limit=limit)}


@router.get("/coin/chart")
async def coin_chart(
    symbol: str = Query(..., min_length=1),
    days: int = Query(1, ge=1, le=365),
) -> dict:
    """Ряд цены монеты за N дней (для графика в карточке монеты)."""
    return {"symbol": symbol.upper(), "days": days, "prices": await market_analytics.coin_chart(symbol, days)}


@router.get("/coins/search")
async def coins_search(q: str = Query(..., min_length=1), limit: int = Query(10, ge=1, le=50)) -> dict:
    """Поиск монеты по тикеру/имени среди топ-400 (для автодополнения)."""
    return {"results": await market_analytics.search(q, limit=limit)}


@router.get("/coin")
async def coin(symbol: str = Query(..., min_length=1)) -> dict:
    """Котировка монеты по тикеру."""
    quote = await market_analytics.coin_quote(symbol)
    return quote or {"symbol": symbol.upper(), "price": None}


@router.get("/ipo/raw")
async def ipo_raw() -> dict:
    """Debug: сырой ответ Alpha Vantage (первые 500 символов)."""
    import httpx
    key = settings.alpha_vantage_key
    if not key:
        return {"error": "no key"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://www.alphavantage.co/query",
                params={"function": "IPO_CALENDAR", "apikey": key}
            )
        return {
            "status": r.status_code,
            "content_type": r.headers.get("content-type", ""),
            "text_first500": r.text[:500],
            "bytes_hex_first50": r.content[:50].hex(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/ipo")
async def ipo() -> dict:
    """Предстоящие IPO (США) из Alpha Vantage IPO Calendar."""
    from ..market.ipo import ipo_provider
    items = await ipo_provider.upcoming()
    return {"configured": bool(settings.alpha_vantage_key), "items": items}


@router.get("/sentiment")
async def sentiment(hours: float = Query(2.0, ge=0.25, le=48)) -> dict:
    """Средний сентимент по монетам за окно (для графиков)."""
    since_items = [
        a for a in store.feed(limit=500)
    ]
    return aggregator.sentiment_by_coin(since_items)
