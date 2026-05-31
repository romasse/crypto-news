"""Mock-источник: реалистичные новости за последние часы.

Позволяет крутить весь конвейер (сбор → AI → лента → графики) без внешних API.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import NewsItem
from .base import Source, build_item

# (минут назад, заголовок, тело)
_SEED: list[tuple[int, str, str]] = [
    (
        12,
        "BlackRock spot Bitcoin ETF sees record $1.2B daily inflow",
        "Институциональный спрос на BTC ускоряется: фонд BlackRock зафиксировал "
        "рекордный дневной приток средств, что усиливает бычий нарратив по биткоину.",
    ),
    (
        34,
        "Ethereum Dencun upgrade cuts L2 fees by 90%",
        "После апгрейда Dencun комиссии в сетях второго уровня Ethereum резко упали, "
        "что позитивно для экосистемы ETH и активности разработчиков.",
    ),
    (
        58,
        "Solana network experiences brief outage amid memecoin surge",
        "Сеть Solana столкнулась с кратковременным сбоем на фоне всплеска активности "
        "вокруг мемкоинов. Краткосрочно это негативный сигнал для SOL.",
    ),
    (
        77,
        "US CPI comes in hotter than expected, dollar index DXY rises",
        "Инфляция в США выше прогноза, индекс доллара DXY растёт. Рисковые активы, "
        "включая крипту, под давлением; корреляция с Nasdaq остаётся высокой.",
    ),
    (
        95,
        "Whale moves 5,000 BTC to Binance cold wallet",
        "Крупный кит перевёл 5 000 BTC на холодный кошелёк Binance. Ончейн-аналитики "
        "расходятся в трактовке: накопление либо подготовка к продаже.",
    ),
    (
        110,
        "Ripple secures new institutional partnership for cross-border payments",
        "Ripple объявил о новом институциональном партнёрстве для трансграничных "
        "платежей, что умеренно позитивно для XRP.",
    ),
]


class MockSource(Source):
    name = "mock"

    async def fetch(self, since: datetime) -> list[NewsItem]:
        now = datetime.now(timezone.utc)
        items: list[NewsItem] = []
        for minutes_ago, title, body in _SEED:
            published = now - timedelta(minutes=minutes_ago)
            if published < since:
                continue
            items.append(
                build_item(
                    source=self.name,
                    title=title,
                    url=None,  # моки без внешней ссылки — заголовок не кликабелен
                    body=body,
                    published_at=published,
                )
            )
        return items
