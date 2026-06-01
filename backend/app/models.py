"""Доменные модели. Единый NewsItem и схема AI-вывода из спецификации."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class Bias(str, Enum):
    bullish = "Bullish"
    neutral = "Neutral"
    bearish = "Bearish"


class EventType(str, Enum):
    """Тип события (раздел 5 ТЗ): апгрейды, коллаборации, анонсы и пр."""

    upgrade = "upgrade"            # технологическое обновление, хардфорк, миграция
    collaboration = "collaboration"  # партнёрство, совместная инициатива
    announcement = "announcement"  # официальный анонс команды/фонда
    listing = "listing"            # листинг/делистинг, новый рынок
    regulation = "regulation"      # регуляторика, иски, законы
    market = "market"              # рыночное движение, макро, ликвидность
    other = "other"


class NewsItem(BaseModel):
    """Нормализованная единица данных — общая для всех источников.

    Любой Source (RSS, CryptoPanic, CoinGecko, X, Telegram, mock) обязан
    приводить свои данные к этой форме. AI-слой и фронт зависят только отсюда.
    """

    id: str = Field(..., description="Стабильный идентификатор (хэш url+title)")
    source: str = Field(..., description="Имя источника: rss, mock, ...")
    title: str
    url: Optional[str] = None
    body: str = ""
    published_at: datetime
    coins: list[str] = Field(default_factory=list, description="Тикеры: BTC, ETH, ...")


class DirectionalBias(BaseModel):
    """Ожидаемое движение топ-активов (раздел 3 спеки)."""

    BTC: Bias = Bias.neutral
    ETH: Bias = Bias.neutral
    SOL: Bias = Bias.neutral


class CorrelationCheck(BaseModel):
    """Чек-лист сверки с макро-индикаторами для подтверждения тренда."""

    btc_volume: Optional[str] = None
    dxy: Optional[str] = None
    nasdaq: Optional[str] = None
    funding_rate: Optional[str] = None


class Analysis(BaseModel):
    """Результат AI-обработки одного события по жёсткой схеме вывода."""

    summary: str = Field(..., description="Executive Summary — суть события")
    ai_analysis: str = Field(..., description="Вектор влияния + Daily Outlook")
    event_type: EventType = Field(EventType.other, description="Тип события")
    sentiment: float = Field(
        0.0, ge=-1.0, le=1.0, description="Сентимент от -1 (негатив) до +1 (позитив)"
    )
    directional_bias: DirectionalBias = Field(default_factory=DirectionalBias)
    correlation_check: CorrelationCheck = Field(default_factory=CorrelationCheck)


class AnalyzedItem(BaseModel):
    """NewsItem + его анализ — то, что отдаётся на фронт."""

    item: NewsItem
    analysis: Analysis


class CollectResult(BaseModel):
    """Ответ Time-Window агрегатора."""

    window_hours: float
    collected: int
    analyzed: int
    items: list[AnalyzedItem]
    sentiment_by_coin: dict[str, float]
    market: dict[str, Any] = Field(default_factory=dict, description="Срез рынка на момент сбора")
