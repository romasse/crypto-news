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
    """Time-Window: собрать и разобрать новости за последние `hours` часов."""
    return await aggregator.collect(window_hours=hours)


@router.get("/market")
async def market() -> dict:
    """Текущий срез рынка: цены/объёмы/изменение по монетам + funding rate BTC."""
    return await market_provider.snapshot()


@router.get("/sentiment")
async def sentiment(hours: float = Query(2.0, ge=0.25, le=48)) -> dict:
    """Средний сентимент по монетам за окно (для графиков)."""
    since_items = [
        a for a in store.feed(limit=500)
    ]
    return aggregator.sentiment_by_coin(since_items)
